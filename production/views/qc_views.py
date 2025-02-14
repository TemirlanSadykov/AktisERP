from collections import defaultdict

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from barcode import Code128
from barcode.writer import ImageWriter
from django.http import HttpResponse
from django.shortcuts import render
from io import BytesIO
from django.views.decorators.http import require_POST
from django.db.models import Q

from ..decorators import qc_required
from ..forms import *
from ..mixins import *
from ..models import *

CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@qc_required
def qc_page(request):
    context = {
            'sidebar_type': 'qc_page'
            }
    return render(request, 'qc_page.html', context)

@method_decorator([login_required, qc_required], name='dispatch')
class ClientOrderListQcView(RestrictBranchMixin, ListView):
    model = ClientOrder
    template_name = 'qc/client/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 10
    form_class = DateRangeForm 

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_archived=False)
        today = timezone.localdate()

        # Get the term filter from the request (default to 'upcoming')
        term_filter = self.request.GET.get('term', 'upcoming').lower()

        if term_filter == 'upcoming':
            queryset = queryset.filter(term__gte=today).order_by('term')
        elif term_filter == 'passed':
            queryset = queryset.filter(term__lt=today).order_by('-term')
        else:
            queryset = queryset.filter(term__gte=today).order_by('term')

        # Date range filtering
        form = self.form_class(self.request.GET)
        if form.is_valid():
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')
            if start_date and end_date:
                queryset = queryset.filter(launch__range=[start_date, end_date])
            elif start_date:
                queryset = queryset.filter(launch__gte=start_date)
            elif end_date:
                queryset = queryset.filter(launch__lte=end_date)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form_class(self.request.GET or None)
        today = timezone.localdate()

        # Calculate days_left for each order
        orders_with_days_left = []
        for order in context['orders']:
            days_left = (order.term - today).days
            orders_with_days_left.append({'order': order, 'days_left': days_left})
        context['orders_with_days_left'] = orders_with_days_left

        # Pass the term filter for template usage
        context['term_filter'] = self.request.GET.get('term', 'upcoming').lower()
        context['ClientOrder'] = ClientOrder
        context['sidebar_type'] = 'qc_page'
        return context
    
@method_decorator([login_required, qc_required], name='dispatch')
class ClientOrderDetailQcView(DetailView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'qc/client/orders/detail.html'
    context_object_name = 'client_order'

    def get_context_data(self, **kwargs):
        context = super(ClientOrderDetailQcView, self).get_context_data(**kwargs)
        client_order = context['client_order']
        context['orders'] = client_order.orders.all()
        today = timezone.localdate()
        if client_order.term >= today:
            days_left = (client_order.term - today).days
        else:
            days_left = 0
        context['days_left'] = days_left
        context['sidebar_type'] = 'qc_page'
        return context

@method_decorator([login_required, qc_required], name='dispatch')
class OrderListQcView(RestrictOrderBranchMixin, ListView):
    model = Order
    template_name = 'qc/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 10

    def get_queryset(self):
        status = self.request.GET.get('status', None)
        search_query = self.request.GET.get('search', None)
        queryset = super().get_queryset().order_by('client_order__term')

        queryset = queryset.filter(client_order__is_archived=False)

        if status:
            try:
                status = int(status)
                if status in dict(self.model.TYPE_CHOICES):
                    queryset = queryset.filter(status=status)
            except ValueError:
                pass

        if search_query:
            queryset = queryset.filter(
                Q(model__name__icontains=search_query) |
                Q(color__icontains=search_query) |
                Q(fabrics__icontains=search_query)
            )
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        orders_with_days_left = []

        for order in context['orders']:
            days_left = (order.client_order.term - today).days
            orders_with_days_left.append({
                'order': order,
                'days_left': days_left
            })

        orders_with_days_left_sorted = sorted(orders_with_days_left, key=lambda x: x['days_left'])
        context['Order'] = Order
        context['selected_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('search', '')
        context['orders_with_days_left'] = orders_with_days_left_sorted
        context['sidebar_type'] = 'qc_page'
        return context

@method_decorator([login_required, qc_required], name='dispatch')
class OrderDetailQcView(DetailView):
    model = Order
    template_name = 'qc/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']

        # ----- Build pivot data for "Required Quantities" table -----
        # We'll use order.size_quantities.all() (assumed to include both color and fabric)
        required_qs = order.size_quantities.all().order_by('size')
        pivot_data = {}  # keys: (color, fabric), value: {size: quantity}
        all_sizes_set = set()
        for sq in required_qs:
            # Collect the size (header) value.
            all_sizes_set.add(sq.size)
            # Use a tuple (color, fabric) as the key.
            key = (sq.color, sq.fabrics)  # Adjust field names if needed.
            if key not in pivot_data:
                pivot_data[key] = {}
            pivot_data[key][sq.size] = sq.quantity

        # Sort sizes. (If sizes are numeric strings, convert to int for sorting.)
        try:
            all_sizes = sorted(all_sizes_set, key=lambda s: int(s))
        except ValueError:
            all_sizes = sorted(all_sizes_set)

        # ----- Other context data (pass along your existing context) -----
        associated_cuts = order.cuts.all().order_by('number')
        passports = Passport.objects.filter(cut__in=associated_cuts).order_by('cut__number', 'number')
        size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'checked_quantity': 0, 'passport_size_id': None, 'stage': None, 'extra': None}))
        total_per_size = defaultdict(int)
        total_checked_per_size = defaultdict(int)
        for passport in passports:
            passport_number = passport.id
            for passport_size in passport.passport_sizes.all():
                size = passport_size.size_quantity.size
                extra_key = f"{size}-{passport_size.extra}" if passport_size.extra else size
                size_data[extra_key][passport_number]['quantity'] += passport_size.quantity
                size_data[extra_key][passport_number]['passport_size_id'] = passport_size.id
                size_data[extra_key][passport_number]['stage'] = passport_size.stage
                size_data[extra_key][passport_number]['extra'] = passport_size.extra

                # Calculate checked pieces
                checked_pieces = ProductionPiece.objects.filter(
                    passport_size=passport_size,
                    stage__in=[ProductionPiece.StageChoices.CHECKED, ProductionPiece.StageChoices.PACKED]
                ).count()
                size_data[extra_key][passport_number]['checked_quantity'] += checked_pieces
                total_per_size[size] += passport_size.quantity
                total_checked_per_size[size] += checked_pieces

        required_missing = {sq.size: {'required': sq.quantity, 'missing': sq.quantity - total_per_size.get(sq.size, 0), 'checked': total_checked_per_size.get(sq.size, 0)}
                            for sq in order.size_quantities.all().order_by('size')}
        for size in total_per_size:
            if size not in required_missing:
                required_missing[size] = {'required': 0, 'missing': -total_per_size[size], 'checked': total_checked_per_size[size]}

        def sort_key(x):
            parts = x.split('-')
            try:
                return int(parts[0]), x
            except ValueError:
                return float('inf'), x
        sorted_size_data_keys = sorted(size_data.keys(), key=sort_key)

        context.update({
            'pivot_data': pivot_data,  # Our new pivoted required data
            'all_sizes': all_sizes,    # List of sizes for the header row
            # (Include your other context items as before.)
            'size_data': {k: dict(size_data[k]) for k in sorted_size_data_keys},
            'total_per_size': dict(total_per_size),
            'required_missing': required_missing,
            'days_left': (order.client_order.term - timezone.now().date()).days if order.client_order.term >= timezone.now().date() else 0,
            'associated_passports': passports,
            'associated_cuts': associated_cuts,
            'sidebar_type': 'qc_page'
        })
        return context  
    
@method_decorator([login_required, qc_required], name='dispatch')
class CutDetailQcView(DetailView):
    model = Cut
    template_name = 'qc/cuts/detail.html'
    context_object_name = 'cut'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cut_pk = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_pk)

        # Get all passports related to the cut
        passports = cut.passports.all()

        # Prepare the total quantities for each size in the cut
        total_quantity_per_size = defaultdict(int)
        for size_quantity in cut.size_quantities.all():
            total_quantity_per_size[f'{size_quantity.size} - {size_quantity.color}'] = size_quantity.quantity

        # Total quantity of layers (sum layers for all passports)
        total_layers = sum(passport.layers for passport in passports if passport.layers)

        context.update({
            'passports': passports,
            'total_quantity_per_size': dict(total_quantity_per_size),
            'total_layers': total_layers,
            'sidebar_type': 'qc_page'
        })

        return context
    
@method_decorator([login_required, qc_required], name='dispatch')
class PassportDetailQcView(DetailView):
    model = Passport
    template_name = 'qc/passports/detail.html'
    context_object_name = 'passport'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        passport = context['passport']
        context['passport_sizes'] = passport.passport_sizes.all().order_by('size_quantity__size')
        context['sidebar_type'] = 'qc_page'
        return context

@login_required
@qc_required
def get_piece_info(request, barcode):
    try:
        # Split the barcode and extract the piece ID
        parts = barcode.split('-')
        if len(parts) != 3:
            return JsonResponse({'error': 'Invalid barcode format'}, status=400)

        piece_id = parts[2]  # Assuming the last part is the piece ID
        piece = ProductionPiece.objects.get(id=piece_id)  # Fetch the piece using the extracted ID

        size = f"{piece.passport_size.size_quantity.size}-{piece.passport_size.extra}" if piece.passport_size.extra else piece.passport_size.size_quantity.size
        date = piece.passport_size.passport.cut.date
        cut = piece.passport_size.passport.cut.number
        model = piece.passport_size.passport.cut.order.model.name
        color = piece.passport_size.passport.roll.color.name if piece.passport_size.passport.roll else piece.passport_size.passport.cut.order.colors.first().name
        fabrics = piece.passport_size.passport.roll.fabrics.name if piece.passport_size.passport.roll else piece.passport_size.passport.cut.order.fabrics.first().name
        size = piece.passport_size.size_quantity.size
        passport_id = piece.passport_size.passport.id
        passport_number = piece.passport_size.passport.number
        data = {
            'piece_id': piece.id,
            'piece_number': piece.piece_number,
            'passport_id': passport_id,
            'passport_number': passport_number,
            'date': date,
            'cut': cut,
            'model': model,
            'color': color,
            'fabrics': fabrics,
            'size': size,
            'stage': piece.get_stage_display(),
        }
        return JsonResponse(data)
    except ProductionPiece.DoesNotExist:
        return JsonResponse({'error': 'Piece not found'}, status=404)

    except ValueError:
        return JsonResponse({'error': 'Error processing barcode'}, status=500)
    
@require_POST
@login_required
@qc_required
def update_piece_qc(request, piece_id):
    data = json.loads(request.body)
    status = data.get('status')

    valid_statuses = {
        'Checked': ProductionPiece.StageChoices.CHECKED,
        'Defect': ProductionPiece.StageChoices.DEFECT
    }
    
    if status not in valid_statuses:
        return JsonResponse({'success': False, 'message': 'Invalid status provided.'}, status=400)

    piece = ProductionPiece.objects.get(id=piece_id)

    piece.stage = valid_statuses[status]
    print(piece)
    piece.save()
    message = f'Piece status updated to {status}.'

    return JsonResponse({'success': True, 'message': message})

@method_decorator([login_required, qc_required], name='dispatch')
class DefectDetailView(DetailView):
    model = Error 
    template_name = 'qc/defects/detail.html'  
    context_object_name = 'error'

@method_decorator([login_required, qc_required], name='dispatch')
class DefectDeleteView(DeleteView):
    model = Error

    def get_success_url(self):
        order_pk = self.kwargs['order_pk']
        return reverse_lazy('order_detail_qc', kwargs={'pk': order_pk})
    
@login_required
@qc_required
def mark_as_qc(request, passport_size_id):
    try:
        passport_size = PassportSize.objects.get(id=passport_size_id)
        with transaction.atomic():
            if passport_size.stage == PassportSize.QC:
                passport_size.stage = PassportSize.SEWING
            else:
                passport_size.stage = PassportSize.QC
            passport_size.save()

        return JsonResponse({'success': True})

    except PassportSize.DoesNotExist:
        return JsonResponse({'error': 'PassportSize not found'}, status=404)
    
@login_required
@qc_required
def mark_as_packing(request, passport_size_id):
    try:
        passport_size = PassportSize.objects.get(id=passport_size_id)
        with transaction.atomic():
            if passport_size.stage == PassportSize.PACKING:
                passport_size.stage = PassportSize.QC
            else:
                passport_size.stage = PassportSize.PACKING
            passport_size.save()

        return JsonResponse({'success': True})

    except PassportSize.DoesNotExist:
        return JsonResponse({'error': 'PassportSize not found'}, status=404)
 
@login_required
@qc_required
def scan_qc_page(request):
    context = {
            'sidebar_type': 'qc_page'
            }
    return render(request, 'qc/scans/detail.html', context)