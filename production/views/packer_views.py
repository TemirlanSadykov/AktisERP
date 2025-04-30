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
from decimal import Decimal

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

        # Build pivot data for "Required Quantities" table using SizeQuantity records.
        required_qs = order.size_quantities.all().order_by('size')
        pivot_data = {}          # keys: (color, fabric), value: {size: required quantity}
        pivot_data_checked = {}  # keys: (color, fabric), value: {size: checked count}
        all_sizes_set = set()

        for sq in required_qs:
            all_sizes_set.add(sq.size)
            key = (sq.color, sq.fabrics)  # tuple key based on color and fabric
            if key not in pivot_data:
                pivot_data[key] = {}
                pivot_data_checked[key] = {}

            pivot_data[key][sq.size] = sq.quantity
            # Use the 'checked' field from SizeQuantity, defaulting to 0 if not set.
            pivot_data_checked[key][sq.size] = sq.packed if sq.packed is not None else 0

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

@login_required
@packer_required
def manual_pack_page(request):
    client_orders = ClientOrder.objects.filter(is_archived=False)
    context = {
        'sidebar_type': 'packer',
        'client_orders': client_orders,
    }
    return render(request, 'packer/scans/manual.html', context)

@login_required
@packer_required
def get_order_table_data_packer(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
        required_qs = order.size_quantities.all().order_by('color__name', 'fabrics__name', 'size')
        
        pivot_data = {}
        all_sizes_set = set()
        sq_ids = {}
        production_complete_map = {}
        
        for sq in required_qs:
            all_sizes_set.add(sq.size)
            key = f"{sq.color} {sq.fabrics}"
            
            # Build the pivot mapping: key → {size: required quantity}
            if key not in pivot_data:
                pivot_data[key] = {}
            pivot_data[key][sq.size] = sq.quantity
            
            # Build the mapping for SizeQuantity IDs
            if key not in sq_ids:
                sq_ids[key] = {}
            sq_ids[key][sq.size] = sq.id
            
            # Build the mapping for production_complete status.
            if key not in production_complete_map:
                production_complete_map[key] = {}
            production_complete_map[key][sq.size] = sq.production_complete
        
        # Sort sizes (if numeric, sort by integer value)
        try:
            all_sizes = sorted(all_sizes_set, key=lambda s: int(s))
        except ValueError:
            all_sizes = sorted(all_sizes_set)
        
        # Build packed_counts mapping: key → {size: packed value}
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
            'sq_ids': sq_ids,  # Mapping of each size quantity's id.
            'production_complete': production_complete_map,  # New: mapping for prod complete.
        }
        return JsonResponse(data)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

@require_POST
@login_required
@packer_required
def update_packed_quantity_manually(request):
    """
    Expects JSON with:
      - order_id: ID of the order
      - size_quantity_id: ID of the SizeQuantity record to update
      - quantity: the desired number of production pieces to mark as packed.
      
    This view directly assigns the provided quantity to the SizeQuantity.packed field.
    """
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        size_quantity_id = data.get('size_quantity_id')
        quantity_value = data.get('quantity')
        quantity = None
        # Convert None or empty string to 0.
        if quantity_value is not None:
            quantity = int(quantity_value)
        
        if not order_id or not size_quantity_id:
            return JsonResponse({'success': False, 'message': 'Missing required parameters.'}, status=400)
        
        # Retrieve the order.
        order = Order.objects.get(id=order_id)
        
        # Ensure the SizeQuantity record is among those associated with the order.
        sq = order.size_quantities.get(id=size_quantity_id)
        
        # Directly assign the provided quantity to the packed field.
        sq.packed = quantity
        sq.save(update_fields=['packed'])
        
        return JsonResponse({'success': True, 'updated_packed': quantity})
    
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Order not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
@packer_required
@require_POST
def complete_production(request):
    try:
        data = json.loads(request.body)
        sq_id = data.get('size_quantity_id')
        if not sq_id:
            return JsonResponse({'success': False, 'message': 'Missing size_quantity_id.'})
        
        sq_obj = SizeQuantity.objects.get(pk=sq_id)
        sq_obj.production_complete = True
        sq_obj.save()

        packed_quantity = sq_obj.packed or 0
        packed_quantity = Decimal(packed_quantity)

        # Get warehouse
        warehouse = Warehouse.objects.filter(is_archived=False).first()
        if not warehouse:
            return JsonResponse({'success': False, 'message': 'No available warehouse.'})

        # Create finished goods stock
        content_type = ContentType.objects.get_for_model(sq_obj)
        stock = Stock.objects.create(
            content_type=content_type,
            object_id=sq_obj.pk,
            quantity=packed_quantity,
            warehouse=warehouse,
            is_archived=False,
            type=Stock.FINSHED_GOODS
        )

        StockMovement.objects.create(
            stock=stock,
            movement_type='IN',
            quantity=packed_quantity,
            from_warehouse=None,
            to_warehouse=warehouse,
            note="Прием готовой продукции"
        )

        # Subtract raw materials used in BOM
        for bom in sq_obj.bill_of_materials.select_related('item').all():
            total_needed = bom.quantity * packed_quantity

            # Find raw material stock
            raw_stock = Stock.objects.filter(
                content_type=ContentType.objects.get_for_model(bom.item),
                object_id=bom.item.pk,
                type__in=[Stock.RAW_MATERIALS, Stock.ROLLS],
                warehouse=warehouse,
                is_archived=False
            ).first()

            if not raw_stock:
                return JsonResponse({'success': False, 'message': f"No stock for raw material: {bom.item.name}"})

            raw_stock.quantity -= total_needed
            raw_stock.save()

            StockMovement.objects.create(
                stock=raw_stock,
                movement_type='OUT',
                quantity=total_needed,
                from_warehouse=warehouse,
                to_warehouse=None,
                note=f"Расход для производства {sq_obj}"
            )

        return JsonResponse({'success': True})

    except SizeQuantity.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Size quantity not found.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})




@login_required
@packer_required
def scan_packer_page(request):
    context = {
            'sidebar_type': 'packer'
            }
    return render(request, 'packer/scans/detail.html', context)

@require_POST
@login_required
@packer_required
def update_packed_by_sku(request, sku):
    try:
        import json
        body = json.loads(request.body.decode('utf-8')) if request.body else {}
        confirm_switch = body.get('confirm_switch', False)

        # Find the SizeQuantity object matching the scanned SKU.
        sq = SizeQuantity.objects.filter(sku=sku).first()
        if not sq:
            return JsonResponse({'success': False, 'message': 'SKU not found.'}, status=404)
        
        # Get the order that contains this SizeQuantity.
        order = Order.objects.filter(size_quantities=sq).first()
        if not order:
            return JsonResponse({'success': False, 'message': 'Order not found for this SKU.'}, status=404)

        # Check for current order in the session.
        current_order_id = request.session.get('current_order_id')
        if current_order_id is None:
            # No order set yet, so initialize it.
            request.session['current_order_id'] = order.id
        elif current_order_id != order.id and not confirm_switch:
            # The scanned SKU belongs to a different order and the user has not confirmed a switch.
            data = {
                'success': False,
                'switch_order': True,
                'message': f"Are you sure you want to start packaging {order.model.name} order?",
                'order_id': order.id,
                'model_name': order.model.name,
            }
            return JsonResponse(data, status=200)
        elif current_order_id != order.id and confirm_switch:
            # User confirmed switching orders.
            request.session['current_order_id'] = order.id

        # Now process the update: increment the packed count.
        if sq.packed is None:
            sq.packed = 1
        else:
            sq.packed += 1
        sq.save(update_fields=['packed'])
        
        # Determine if the required quantity is now reached.
        reached_required = False
        if sq.quantity is not None and sq.packed == sq.quantity:
            reached_required = True

        # Build the list of size quantities for this order.
        size_qty_data = []
        for qty in order.size_quantities.all():
            size_qty_data.append({
                'sku': qty.sku,
                'color': str(qty.color),
                'fabrics': str(qty.fabrics),
                'size': qty.size,
                'quantity': qty.quantity,
                'packed': qty.packed if qty.packed is not None else 0,
                'id': qty.id,
                'production_complete': qty.production_complete
            })
        
        data = {
            'success': True,
            'message': 'Packed count updated for SKU.',
            'order_id': order.id,
            'model_name': order.model.name,
            'size_quantities': size_qty_data,
            'scanned_sku': sq.sku,
            'reached_required': reached_required,  # New flag
        }
        return JsonResponse(data)
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)