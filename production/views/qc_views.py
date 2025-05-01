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
from django.http import HttpResponse
from django.shortcuts import render
from io import BytesIO
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.db.models import Count

from ..decorators import qc_required
from ..forms import *
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
class ClientOrderListQcView(ListView):
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
class OrderListQcView(ListView):
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

        # Build pivot data for "Required Quantities" table using SizeQuantity records.
        required_qs = order.size_quantities.all().order_by('size')
        pivot_data = {}          # keys: (color, fabric), value: {size: required quantity}
        pivot_data_checked = {}  # keys: (color, fabric), value: {size: checked count}
        all_sizes_set = set()

        for sq in required_qs:
            all_sizes_set.add(sq.size)
            key = (sq.color, sq.fabrics)  # group by color and fabric
            if key not in pivot_data:
                pivot_data[key] = {}
                pivot_data_checked[key] = {}
            pivot_data[key][sq.size] = sq.quantity
            # Use the 'checked' field from SizeQuantity; default to 0 if missing.
            pivot_data_checked[key][sq.size] = sq.checked if sq.checked is not None else 0

        # Sort sizes (if sizes are numeric strings, sort numerically).
        try:
            all_sizes = sorted(all_sizes_set, key=lambda s: int(s))
        except ValueError:
            all_sizes = sorted(all_sizes_set)

        context.update({
            'pivot_data': pivot_data,                # required quantities pivot
            'pivot_data_checked': pivot_data_checked,  # checked counts pivot
            'all_sizes': all_sizes,                    # list of sizes for header row
            'days_left': (order.client_order.term - timezone.now().date()).days
                          if order.client_order.term >= timezone.now().date() else 0,
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

# ------------------------------
# Updated get_piece_info view
# ------------------------------
@login_required
@qc_required
def get_piece_info(request, barcode):
    try:
        # Use the scanned barcode as the SKU for PassportSize.
        passport_size = PassportSize.objects.filter(sku=barcode).first()
        
        # Retrieve details from passport_size and its related objects.
        cut = passport_size.passport.cut.number
        model = passport_size.passport.cut.order.model.name
        color = passport_size.size_quantity.color.name if passport_size.size_quantity.color else "-"
        fabrics = passport_size.size_quantity.fabrics.name if passport_size.size_quantity.fabrics else "-"
        size = passport_size.size_quantity.size
        passport_number = passport_size.passport.number
        order = passport_size.passport.cut.order
        order_id = order.id
        order_name = order.model.name

        data = {
            'piece_id': passport_size.id,
            'passport_number': passport_number,
            'cut': cut,
            'model': model,
            'color': color,
            'fabrics': fabrics,
            'size': size,
            'order_id': order_id,
            'order_name': order_name,
        }
        return JsonResponse(data)
    except PassportSize.DoesNotExist:
        return JsonResponse({'error': 'PassportSize not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_POST
@login_required
@qc_required
def update_piece_qc(request, piece_id):
    data = json.loads(request.body)
    status = data.get('status')

    valid_statuses = {
        'Checked': 'Checked',
        'Defect': 'Defect'
    }

    if status not in valid_statuses:
        return JsonResponse({'success': False, 'message': 'Invalid status provided.'}, status=400)

    try:
        passport_size = PassportSize.objects.select_related(
            'size_quantity__color',
            'size_quantity__fabrics'
        ).get(id=piece_id)
    except PassportSize.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'PassportSize not found.'}, status=404)

    if status == 'Checked':
        size_quantity = passport_size.size_quantity
        size_quantity.checked = (size_quantity.checked or 0) + 1
        size_quantity.save(update_fields=['checked'])

        combo = f"{size_quantity.color} {size_quantity.fabrics}"
        return JsonResponse({
            'success': True,
            'message': 'Единица обновлена до статуса Проверено.',
            'combo': combo,
            'size': size_quantity.size,
            'checked': size_quantity.checked
        })

    return JsonResponse({
        'success': True,
        'message': 'Единица отмечена как брак.'
    })

# ------------------------------
# New API view: get_order_table_data
# ------------------------------
@login_required
@qc_required
def get_order_table_data_qc(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
        # Get the size quantities for the order.
        # Each size quantity is assumed to have attributes:
        # size, color, fabrics, quantity, checked, and packed.
        required_qs = order.size_quantities.all().order_by('color__name', 'fabrics__name', 'size')
        
        # Build pivot data: key is "Color Fabrics" and value is a dict mapping size to required quantity.
        pivot_data = {}
        all_sizes_set = set()
        for sq in required_qs:
            all_sizes_set.add(sq.size)
            key = f"{sq.color} {sq.fabrics}"
            if key not in pivot_data:
                pivot_data[key] = {}
            pivot_data[key][sq.size] = sq.factual
        
        # Sort sizes (if numeric, sort by integer value)
        try:
            all_sizes = sorted(all_sizes_set, key=lambda s: int(s))
        except ValueError:
            all_sizes = sorted(all_sizes_set)
                
        # Build checked_counts from the size quantities.
        # This dictionary uses the same key ("Color Fabrics") and maps each size to its checked value.
        checked_counts = {}
        for sq in required_qs:
            key = f"{sq.color} {sq.fabrics}"
            if key not in checked_counts:
                checked_counts[key] = {}
            checked_counts[key][sq.size] = sq.checked if sq.checked is not None else 0
        
        data = {
            'order_id': order.id,
            'order_name': order.model.name,  # Using model name for display.
            'all_sizes': all_sizes,
            'pivot_data': pivot_data,
            'checked_counts': checked_counts,
        }
        return JsonResponse(data)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)
     
@login_required
@qc_required
def scan_qc_page(request):
    context = {
            'sidebar_type': 'qc_page'
            }
    return render(request, 'qc/scans/detail.html', context)

@login_required
@qc_required
def manual_check_page(request):
    client_orders = ClientOrder.objects.filter(is_archived=False)
    context = {
        'sidebar_type': 'qc_page',
        'client_orders': client_orders,
    }
    return render(request, 'qc/scans/manual.html', context)

@login_required
def ajax_get_orders(request):
    client_order_id = request.GET.get('client_order_id')
    orders_data = []
    if client_order_id:
        orders = Order.objects.filter(client_order_id=client_order_id)
        for order in orders:
            # Get the model name.
            model_name = order.model.name if hasattr(order.model, 'name') else str(order.model)
            
            # Collect unique color & fabric combinations from size_quantities.
            unique_combos = set()
            for sq in order.size_quantities.all():
                if sq.color and sq.fabrics:
                    # The __str__ methods on Color and Fabrics will be used.
                    unique_combos.add(f"{sq.color} {sq.fabrics}")
            
            combos_str = ", ".join(sorted(unique_combos))
            
            # Build the label including model, combos, and order quantity.
            label = f"{model_name} - {combos_str} - Кол: {order.quantity}"
            orders_data.append({"id": order.id, "label": label})
    return JsonResponse({"orders": orders_data})

@require_POST
@login_required
@qc_required
def update_checked_quantity(request):
    """
    Expects JSON with:
      - order_id: ID of the order
      - combo: a string in the format "ColorName FabricsName"
      - size: the size to update (as stored in SizeQuantity.size)
      - quantity: the desired number of production pieces to mark as CHECKED.
      
    This view directly assigns the provided quantity to the SizeQuantity.checked field.
    """
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        combo = data.get('combo')  # e.g. "Red Cotton"
        size = data.get('size')
        quantity_value = data.get('quantity')
        quantity = None
        # Convert None or empty string to 0.
        if quantity_value is not None:
            quantity = int(quantity_value)
        
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
        
        # Directly assign the provided quantity to the checked field.
        sq.checked = quantity
        sq.save(update_fields=['checked'])
        
        return JsonResponse({'success': True, 'updated_checked': quantity})
    
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
