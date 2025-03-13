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
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.db.models import Count

from ..decorators import packer_required
from ..forms import *
from ..models import *

CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@packer_required
def packer_page(request):
    context = {
        'sidebar_type': 'packer'
        }
    return render(request, 'packer_page.html' , context)

@method_decorator([login_required, packer_required], name='dispatch')
class ClientOrderListPackerView(ListView):
    model = ClientOrder
    template_name = 'packer/client/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 10
    form_class = DateRangeForm 

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_archived=False)
        today = timezone.localdate()

        # Get the term filter from the request, defaulting to 'upcoming'
        term_filter = self.request.GET.get('term', 'upcoming').lower()

        if term_filter == 'upcoming':
            queryset = queryset.filter(term__gte=today).order_by('term')
        elif term_filter == 'passed':
            queryset = queryset.filter(term__lt=today).order_by('-term')
        else:
            queryset = queryset.filter(term__gte=today).order_by('term')

        # Apply optional date range filtering
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

        # Pass the current term filter to the template
        context['term_filter'] = self.request.GET.get('term', 'upcoming').lower()
        context['ClientOrder'] = ClientOrder
        context['sidebar_type'] = 'packer'
        return context
    
@method_decorator([login_required, packer_required], name='dispatch')
class ClientOrderDetailPackerView(DetailView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'packer/client/orders/detail.html'
    context_object_name = 'client_order'

    def get_context_data(self, **kwargs):
        context = super(ClientOrderDetailPackerView, self).get_context_data(**kwargs)
        client_order = context['client_order']
        context['orders'] = client_order.orders.all()
        today = timezone.localdate()
        if client_order.term >= today:
            days_left = (client_order.term - today).days
        else:
            days_left = 0
        context['days_left'] = days_left
        context['sidebar_type'] = 'packer'
        return context

@method_decorator([login_required, packer_required], name='dispatch')
class OrderListPackerView(ListView):
    model = Order
    template_name = 'packer/orders/list.html'
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
        context['sidebar_type'] = 'packer'
        return context

@method_decorator([login_required, packer_required], name='dispatch')
class OrderDetailPackerView(DetailView):
    model = Order
    template_name = 'packer/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']

        # ----- Build pivot data for "Required Quantities" table -----
        required_qs = order.size_quantities.all().order_by('size')
        pivot_data = {}          # keys: (color, fabric), value: {size: required quantity}
        pivot_data_checked = {}  # keys: (color, fabric), value: {size: checked count}
        all_sizes_set = set()

        # Pre-calculate the checked counts for each SizeQuantity in this order.
        # We join ProductionPiece through passport_size -> passport -> cut -> order.
        checked_counts_qs = ProductionPiece.objects.filter(
            passport_size__passport__cut__order=order,
            stage=ProductionPiece.StageChoices.PACKED
        ).values('passport_size__size_quantity').annotate(checked_count=Count('id'))

        # Create a lookup dictionary: {SizeQuantity_id: checked_count}
        checked_counts_dict = {
            item['passport_size__size_quantity']: item['checked_count']
            for item in checked_counts_qs
        }

        # Build our pivot data structures.
        for sq in required_qs:
            all_sizes_set.add(sq.size)
            key = (sq.color, sq.fabrics)  # tuple key based on color and fabric

            if key not in pivot_data:
                pivot_data[key] = {}
                pivot_data_checked[key] = {}

            pivot_data[key][sq.size] = sq.quantity
            # Use the pre-computed count, defaulting to 0 if none found.
            pivot_data_checked[key][sq.size] = checked_counts_dict.get(sq.id, 0)

        # Sort sizes (if sizes are numeric strings, sort numerically).
        try:
            all_sizes = sorted(all_sizes_set, key=lambda s: int(s))
        except ValueError:
            all_sizes = sorted(all_sizes_set)

        context.update({
            'pivot_data': pivot_data,             # required quantities pivot
            'pivot_data_checked': pivot_data_checked,  # checked counts pivot
            'all_sizes': all_sizes,               # list of sizes for header row
            'days_left': (order.client_order.term - timezone.now().date()).days
                          if order.client_order.term >= timezone.now().date() else 0,
            'sidebar_type': 'packer'
        })
        return context
    
@method_decorator([login_required, packer_required], name='dispatch')
class CutDetailPackerView(DetailView):
    model = Cut
    template_name = 'packer/cuts/detail.html'
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
            'sidebar_type': 'packer'
        })

        return context
    
@method_decorator([login_required, packer_required], name='dispatch')
class PassportDetailPackerView(DetailView):
    model = Passport
    template_name = 'packer/passports/detail.html'
    context_object_name = 'passport'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        passport = context['passport']
        context['passport_sizes'] = passport.passport_sizes.all().order_by('size_quantity__size')
        context['sidebar_type'] = 'packer'
        return context

@require_POST
@login_required
@packer_required
def update_piece_packer(request, piece_id):
    try:
        piece = ProductionPiece.objects.get(id=piece_id)
        
        # Check conditions for packing
        if piece.stage == ProductionPiece.StageChoices.PACKED:
            return JsonResponse({'success': False, 'message': 'Единица уже упакована.'}, status=409)
        elif piece.stage == ProductionPiece.StageChoices.DEFECT:
            return JsonResponse({'success': False, 'message': 'Единица бракована.'}, status=409)
        elif piece.stage == ProductionPiece.StageChoices.NOT_CHECKED:
            return JsonResponse({'success': False, 'message': 'Единица еще не проверена.'}, status=409)

        # Update piece status to PACKED
        piece.stage = ProductionPiece.StageChoices.PACKED
        piece.save()

        # Prepare response data
        size = f"{piece.passport_size.size_quantity.size}-{piece.passport_size.extra}" if piece.passport_size.extra else piece.passport_size.size_quantity.size
        cut = piece.passport_size.passport.cut.number
        model = piece.passport_size.passport.cut.order.model.name
        color = piece.passport_size.size_quantity.color.name if piece.passport_size.size_quantity.color else "-"
        fabrics = piece.passport_size.size_quantity.fabrics.name if piece.passport_size.size_quantity.fabrics else "-"
        passport_id = piece.passport_size.passport.id
        passport_number = piece.passport_size.passport.number
        
        # Forming the response with piece details
        data = {
            'success': True,
            'message': 'Piece status updated to Packed.',
            'piece_id': piece.id,
            'order_id': piece.passport_size.passport.cut.order.id,
            'piece_number': piece.piece_number,
            'passport_id': passport_id,
            'passport_number': passport_number,
            'cut': cut,
            'model': model,
            'color': color,
            'fabrics': fabrics,
            'size': size,
            'stage': piece.get_stage_display()
        }
        return JsonResponse(data)

    except ProductionPiece.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Piece not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
@login_required
@packer_required
def get_order_table_data_packer(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
        # Get the size quantities for the order.
        # Each size quantity is assumed to have attributes:
        # size, color, fabrics, quantity, packed, and packed.
        required_qs = order.size_quantities.all().order_by('color__name', 'fabrics__name', 'size')
        
        # Build pivot data: key is "Color Fabrics" and value is a dict mapping size to required quantity.
        pivot_data = {}
        all_sizes_set = set()
        for sq in required_qs:
            all_sizes_set.add(sq.size)
            key = f"{sq.color} {sq.fabrics}"
            if key not in pivot_data:
                pivot_data[key] = {}
            pivot_data[key][sq.size] = sq.quantity
        
        # Sort sizes (if numeric, sort by integer value)
        try:
            all_sizes = sorted(all_sizes_set, key=lambda s: int(s))
        except ValueError:
            all_sizes = sorted(all_sizes_set)
        
        # For each size quantity, if the packed field is still null,
        # count the production pieces (PACKED) and update it.
        for sq in required_qs:
            if sq.packed is None:
                count = ProductionPiece.objects.filter(
                    passport_size__size_quantity=sq,
                    passport_size__passport__cut__order=order,
                    stage=ProductionPiece.StageChoices.PACKED
                ).count()
                sq.packed = count
                sq.save(update_fields=['packed'])
        
        # Build packed_counts from the size quantities.
        # This dictionary uses the same key ("Color Fabrics") and maps each size to its packed value.
        packed_counts = {}
        for sq in required_qs:
            key = f"{sq.color} {sq.fabrics}"
            if key not in packed_counts:
                packed_counts[key] = {}
            packed_counts[key][sq.size] = sq.packed if sq.packed is not None else 0
        data = {
            'order_id': order.id,
            'order_name': order.model.name,  # Using model name for display.
            'all_sizes': all_sizes,
            'pivot_data': pivot_data,
            'packed_counts': packed_counts,
        }
        return JsonResponse(data)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

@login_required
@packer_required
def scan_packer_page(request):
    context = {
            'sidebar_type': 'packer'
            }
    return render(request, 'packer/scans/detail.html', context)

@login_required
@packer_required
def manual_pack_page(request):
    client_orders = ClientOrder.objects.filter(is_archived=False)
    context = {
        'sidebar_type': 'packer',
        'client_orders': client_orders,
    }
    return render(request, 'packer/scans/manual.html', context)

@require_POST
@login_required
@packer_required
def update_packed_quantity(request):
    """
    Expects JSON with:
      - order_id: ID of the order
      - combo: a string in the format "ColorName FabricsName"
      - size: the size to update (as stored in SizeQuantity.size)
      - quantity: the desired number of production pieces to mark as packed.
      
    This view directly assigns the provided quantity to the SizeQuantity.packed field.
    """
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        combo = data.get('combo')  # e.g. "Red Cotton"
        size = data.get('size')
        quantity = int(data.get('quantity', 0))
        
        # Split combo into color and fabric. Expects format "ColorName FabricsName".
        parts = combo.split(" ", 1)
        color_name, fabric_name = parts[0].strip(), parts[1].strip()
        
        # Retrieve the order.
        order = Order.objects.get(id=order_id)
        
        # Get the SizeQuantity record associated with the order.
        sq = order.size_quantities.get(
            size=size.strip(),
            color__name=color_name,
            fabrics__name=fabric_name
        )
        
        # Directly assign the provided quantity to the packed field.
        sq.packed = quantity
        sq.save(update_fields=['packed'])
        
        return JsonResponse({'success': True, 'updated_packed': quantity})
    
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
