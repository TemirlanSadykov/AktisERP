from collections import defaultdict

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.db.models import F, Q, Count
from django.urls import reverse_lazy, reverse
from django.views.generic import FormView
from django.views.decorators.http import require_POST
from decimal import Decimal, InvalidOperation

from ..decorators import keeper_required
from ..forms import *
from ..models import *

CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@keeper_required
def keeper_page(request):
    context = {
        'sidebar_type': 'keeper'
        }
    return render(request, 'keeper_page.html' , context)

@method_decorator([login_required, keeper_required], name='dispatch')
class ClientOrderListKeeperView(ListView):
    model = ClientOrder
    template_name = 'keeper/client/orders/list.html'
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
        context['sidebar_type'] = 'keeper'
        return context
    
@method_decorator([login_required, keeper_required], name='dispatch')
class ClientOrderDetailKeeperView(DetailView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'keeper/client/orders/detail.html'
    context_object_name = 'client_order'

    def get_context_data(self, **kwargs):
        context = super(ClientOrderDetailKeeperView, self).get_context_data(**kwargs)
        client_order = context['client_order']
        context['orders'] = client_order.orders.all()
        today = timezone.localdate()
        if client_order.term >= today:
            days_left = (client_order.term - today).days
        else:
            days_left = 0
        context['days_left'] = days_left
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class OrderDetailKeeperView(DetailView):
    model = Order
    template_name = 'keeper/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']

        # days left
        today = timezone.now().date()
        term = order.client_order.term
        context['days_left'] = max((term - today).days, 0)

        # bring in all size‐quantities + their BOM entries
        context['size_quantities'] = (
            order.size_quantities
                 .prefetch_related('bill_of_materials__item__category')
                 .all()
        )

        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierListView(ListView):
    model = Supplier
    template_name = 'keeper/suppliers/list.html'
    context_object_name = 'suppliers'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Supplier.objects.filter(is_archived=False).order_by('name')


@method_decorator([login_required, keeper_required], name='dispatch')
class ArchivedSupplierListView(ListView):
    template_name = 'keeper/suppliers/list.html'
    context_object_name = 'suppliers'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Supplier.objects.filter(is_archived=True).order_by('name')


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierCreateView(CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'keeper/suppliers/create.html'
    success_url = reverse_lazy('supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierDetailView(DetailView):
    model = Supplier
    template_name = 'keeper/suppliers/detail.html'
    context_object_name = 'supplier'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierUpdateView(UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'keeper/suppliers/edit.html'

    def get_success_url(self):
        return reverse('supplier_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierDeleteView(DeleteView):
    model = Supplier
    template_name = 'keeper/suppliers/delete.html'
    success_url = reverse_lazy('supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierArchiveView(UpdateView):
    model = Supplier
    template_name = 'keeper/suppliers/delete.html'
    success_url = reverse_lazy('supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        supplier = self.get_object()
        supplier.is_archived = True
        supplier.save()
        return HttpResponseRedirect(self.success_url)


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierUnArchiveView(UpdateView):
    model = Supplier
    template_name = 'keeper/suppliers/delete.html'
    success_url = reverse_lazy('supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        supplier = self.get_object()
        supplier.is_archived = False
        supplier.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, keeper_required], name='dispatch')
class RollListView(ListView):
    model = Roll
    template_name = 'keeper/rolls/list.html'
    context_object_name = 'rolls'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Roll.objects.all().order_by('name')

@method_decorator([login_required, keeper_required], name='dispatch')
class RollCreateView(CreateView):
    model = Roll
    form_class = RollForm
    template_name = 'keeper/rolls/create.html'
    success_url = reverse_lazy('roll_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollDetailView(DetailView):
    model = Roll
    template_name = 'keeper/rolls/detail.html'
    context_object_name = 'roll'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollUpdateView(UpdateView):
    model = Roll
    form_class = RollForm
    template_name = 'keeper/rolls/edit.html'

    def get_success_url(self):
        return reverse('roll_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollDeleteView(DeleteView):
    model = Roll
    template_name = 'keeper/rolls/delete.html'
    success_url = reverse_lazy('roll_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context
    
@require_POST
@login_required
def add_supplier_api(request):
    form = SupplierForm(request.POST)
    if form.is_valid():
        supplier = form.save()
        data = {
            'success': True,
            'supplier_id': supplier.id,
            'supplier_name': supplier.name,
        }
        return JsonResponse(data)
    else:
        # Return form errors as JSON (status code 400)
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)

@method_decorator([login_required, keeper_required], name='dispatch')
class ColorFabricListView(ListView):
    template_name = 'keeper/rolls/color_fabric_list.html'
    context_object_name = 'combinations'
    
    def get_queryset(self):
        qs = Roll.objects.filter(is_used=False)
        # Filter by supplier if provided via GET parameter
        supplier = self.request.GET.get('supplier')
        if supplier:
            qs = qs.filter(supplier=supplier)
        # Group by color, fabric, and supplier and annotate quantities
        return qs.values(
            'color',
            'fabric',
            'supplier',
            supplier_name=F('supplier__name'),
            color_name=F('color__name'),
            fabric_name=F('fabric__name')
        ).annotate(
            whole_count=Count('id', filter=Q(original_roll__isnull=True)),
            remainder_count=Count('id', filter=Q(original_roll__isnull=False))
        ).order_by('supplier__name', 'color__name', 'fabric__name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        context['selected_supplier'] = self.request.GET.get('supplier', '')
        # Build a list of distinct suppliers (for tabs)
        context['suppliers'] = Roll.objects.filter(is_used=False).values(
            'supplier',
            supplier_name=F('supplier__name')
        ).distinct().order_by('supplier__name')
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollsByCombinationListView(ListView):
    model = Roll
    template_name = 'keeper/rolls/combination_detail.html'
    context_object_name = 'rolls'
    paginate_by = 10
    
    def get_queryset(self):
        color_id = self.kwargs.get('color_id')
        fabric_id = self.kwargs.get('fabric_id')
        supplier_id = self.kwargs.get('supplier_id')
        roll_type = self.request.GET.get('roll_type', 'whole')
        # Use conditional filtering based on roll_type
        if roll_type == 'remainders':
            qs = Roll.objects.filter(
                is_used=False,
                color_id=color_id,
                fabric_id=fabric_id,
                supplier_id=supplier_id,
                original_roll__isnull=False
            )
        else:
            qs = Roll.objects.filter(
                is_used=False,
                color_id=color_id,
                fabric_id=fabric_id,
                supplier_id=supplier_id,
                original_roll__isnull=True
            )
        return qs.order_by('length_t')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        context['roll_type'] = self.request.GET.get('roll_type', 'whole')
        # Pass along the identifiers for use in URL building
        context['color_id'] = self.kwargs.get('color_id')
        context['fabric_id'] = self.kwargs.get('fabric_id')
        context['supplier_id'] = self.kwargs.get('supplier_id')
        first_roll = self.get_queryset().first()
        if first_roll:
            context['color'] = first_roll.color.name
            context['fabric'] = first_roll.fabric.name
            context['supplier'] = first_roll.supplier.name
        else:
            context['color'] = ''
            context['fabric'] = ''
            context['supplier'] = ''
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollBulkCreateView(CreateView):
    model = Roll
    form_class = BulkRollForm
    template_name = 'keeper/rolls/bulk_create.html'
    success_url = reverse_lazy('roll_combinations')

    def form_valid(self, form):
        color = form.cleaned_data['color']
        fabric = form.cleaned_data['fabric']
        supplier = form.cleaned_data['supplier']
        width = form.cleaned_data['width']
        quantity = form.cleaned_data['quantity']
        
        weights = self.request.POST.getlist('weight')
        lengths = self.request.POST.getlist('length')
        cleaned_weights = []
        cleaned_lengths = []

        for w in weights:
            try:
                # Convert empty string to None (or set a default like 0)
                cleaned_weights.append(Decimal(w) if w.strip() else None)
            except InvalidOperation:
                cleaned_weights.append(None)  # or handle error as needed

        for l in lengths:
            try:
                cleaned_lengths.append(Decimal(l) if l.strip() else None)
            except InvalidOperation:
                cleaned_lengths.append(None)

        existing_count = Roll.objects.filter(color=color, fabric=fabric, supplier=supplier).count()
        current_company = get_current_company()  # should be valid
        
        new_rolls = []
        for i in range(quantity):
            roll_name = str(existing_count + i + 1)
            weight_value = cleaned_weights[i] if i < len(cleaned_weights) else None
            length_value = cleaned_lengths[i] if i < len(cleaned_lengths) else None
            new_rolls.append(Roll(
                color=color,
                fabric=fabric,
                supplier=supplier,
                width=width,
                weight=weight_value,
                length_t=length_value,
                name=roll_name,
                is_used=False,
                company=current_company,
            ))
        Roll.objects.bulk_create(new_rolls)
        
        # Set self.object to one of the created rolls (if any)
        if new_rolls:
            self.object = new_rolls[0]
        
        return HttpResponseRedirect(self.get_success_url())
      
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class StockListView(ListView):
    model = Stock
    template_name = 'keeper/stocks/list.html'
    context_object_name = 'stocks'
    paginate_by = 10

    def get_queryset(self):
        qs = Stock.objects.filter(is_archived=False)
        # Read the type from GET parameters; default is 'all' meaning no filtering.
        stock_type = self.request.GET.get('type', 'all')
        if stock_type in ['0', '1']:
            qs = qs.filter(type=int(stock_type))
        return qs.order_by('id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        # Pass the currently selected type; defaults to 'all'
        context['selected_type'] = self.request.GET.get('type', 'all')
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class ArchivedStockListView(ListView):
    template_name = 'keeper/stocks/list.html'
    context_object_name = 'stocks'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Stock.objects.filter(is_archived=True).order_by('id')


@login_required
@keeper_required
def stock_bulk_create(request):
    # GET: render form with categories & items_by_category
    if request.method == 'GET':
        categories = Category.objects.filter(is_archived=False).order_by('name')
        items = Item.objects.filter(is_archived=False).order_by('name')
        items_by_category = defaultdict(list)
        for it in items:
            items_by_category[it.category_id].append(it)

        return render(request, 'keeper/stocks/bulk_create.html', {
            'categories':        categories,
            'items_by_category': dict(items_by_category),
            'sidebar_type':      'keeper',
        })

    # POST: parse each row and update or create stock
    warehouse = Warehouse.objects.filter(is_archived=False).first()
    company   = get_current_company()
    ct        = ContentType.objects.get_for_model(Item)

    row = 0
    while f'row-{row}_item' in request.POST:
        item_id = request.POST.get(f'row-{row}_item')
        qty_str = request.POST.get(f'row-{row}_quantity')
        unit    = request.POST.get(f'row-{row}_unit')

        if item_id and qty_str:
            try:
                qty = Decimal(qty_str)
            except (InvalidOperation, TypeError):
                qty = None

            if qty is not None:
                item = get_object_or_404(Item, pk=item_id)

                # Try to find existing stock record
                stock_qs = Stock.objects.filter(
                    content_type=ct,
                    object_id=item.id,
                    type=Stock.RAW_MATERIALS,
                    warehouse=warehouse,
                    is_archived=False,
                    company=company
                )
                if stock_qs.exists():
                    stock = stock_qs.first()
                    stock.quantity += qty
                    stock.save()
                else:
                    stock = Stock.objects.create(
                        content_type=ct,
                        object_id=item.id,
                        type=Stock.RAW_MATERIALS,
                        quantity=qty,
                        unit=unit,
                        warehouse=warehouse,
                        is_archived=False,
                        company=company,
                    )

                # Log the movement of exactly the added quantity
                StockMovement.objects.create(
                    stock=stock,
                    movement_type='IN',
                    quantity=qty,
                    from_warehouse=None,
                    to_warehouse=warehouse,
                    note='Bulk create',
                )
        row += 1

    return redirect('stock_list')

@method_decorator([login_required, keeper_required], name='dispatch')
class StockDetailView(DetailView):
    model = Stock
    template_name = 'keeper/stocks/detail.html'
    context_object_name = 'stock'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class StockUpdateView(UpdateView):
    model = Stock
    form_class = StockForm
    template_name = 'keeper/stocks/edit.html'

    def get_success_url(self):
        return reverse('stock_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class StockDeleteView(DeleteView):
    model = Stock
    template_name = 'keeper/stocks/delete.html'
    success_url = reverse_lazy('stock_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class StockArchiveView(UpdateView):
    model = Stock
    template_name = 'keeper/stocks/archive.html'
    success_url = reverse_lazy('stock_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        stock = self.get_object()
        stock.is_archived = True
        stock.save()
        return HttpResponseRedirect(self.success_url)


@method_decorator([login_required, keeper_required], name='dispatch')
class StockUnArchiveView(UpdateView):
    model = Stock
    template_name = 'keeper/stocks/archive.html'
    success_url = reverse_lazy('stock_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        stock = self.get_object()
        stock.is_archived = False
        stock.save()
        return HttpResponseRedirect(self.success_url)
    
@require_POST
@login_required
def add_warehouse_api(request):
    form = WarehouseForm(request.POST)
    if form.is_valid():
        warehouse = form.save()
        data = {
            'success': True,
            'warehouse_id': warehouse.id,
            'warehouse_name': warehouse.name,
        }
        return JsonResponse(data)
    else:
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


@method_decorator([login_required, keeper_required], name='dispatch')
class WarehouseListView(ListView):
    model = Warehouse
    template_name = 'keeper/warehouses/list.html'
    context_object_name = 'warehouses'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Warehouse.objects.filter(is_archived=False).order_by('name')


@method_decorator([login_required, keeper_required], name='dispatch')
class ArchivedWarehouseListView(ListView):
    template_name = 'keeper/warehouses/list.html'
    context_object_name = 'warehouses'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Warehouse.objects.filter(is_archived=True).order_by('name')


@method_decorator([login_required, keeper_required], name='dispatch')
class WarehouseCreateView(CreateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'keeper/warehouses/create.html'
    success_url = reverse_lazy('warehouse_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class WarehouseDetailView(DetailView):
    model = Warehouse
    template_name = 'keeper/warehouses/detail.html'
    context_object_name = 'warehouse'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class WarehouseUpdateView(UpdateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'keeper/warehouses/edit.html'

    def get_success_url(self):
        return reverse('warehouse_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class WarehouseDeleteView(DeleteView):
    model = Warehouse
    template_name = 'keeper/warehouses/delete.html'
    success_url = reverse_lazy('warehouse_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class WarehouseArchiveView(UpdateView):
    model = Warehouse
    template_name = 'keeper/warehouses/delete.html'
    success_url = reverse_lazy('warehouse_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        warehouse = self.get_object()
        warehouse.is_archived = True
        warehouse.save()
        return HttpResponseRedirect(self.success_url)


@method_decorator([login_required, keeper_required], name='dispatch')
class WarehouseUnArchiveView(UpdateView):
    model = Warehouse
    template_name = 'keeper/warehouses/delete.html'
    success_url = reverse_lazy('warehouse_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        warehouse = self.get_object()
        warehouse.is_archived = False
        warehouse.save()
        return HttpResponseRedirect(self.success_url)
    

@method_decorator([login_required, keeper_required], name='dispatch')
class CategoryListView(ListView):
    model = Category
    template_name = 'keeper/categories/list.html'
    context_object_name = 'categories'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Category.objects.filter(is_archived=False).order_by('name')


@method_decorator([login_required, keeper_required], name='dispatch')
class ArchivedCategoryListView(ListView):
    template_name = 'keeper/categories/list.html'
    context_object_name = 'categories'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Category.objects.filter(is_archived=True).order_by('name')


@method_decorator([login_required, keeper_required], name='dispatch')
class CategoryCreateView(CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'keeper/categories/create.html'
    success_url = reverse_lazy('category_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class CategoryDetailView(DetailView):
    model = Category
    template_name = 'keeper/categories/detail.html'
    context_object_name = 'category'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class CategoryUpdateView(UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'keeper/categories/edit.html'

    def get_success_url(self):
        return reverse('category_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class CategoryDeleteView(DeleteView):
    model = Category
    template_name = 'keeper/categories/delete.html'
    success_url = reverse_lazy('category_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class CategoryArchiveView(UpdateView):
    model = Category
    template_name = 'keeper/categories/delete.html'
    success_url = reverse_lazy('category_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        category = self.get_object()
        category.is_archived = True
        category.save()
        return HttpResponseRedirect(self.success_url)


@method_decorator([login_required, keeper_required], name='dispatch')
class CategoryUnArchiveView(UpdateView):
    model = Category
    template_name = 'keeper/categories/delete.html'
    success_url = reverse_lazy('category_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        category = self.get_object()
        category.is_archived = False
        category.save()
        return HttpResponseRedirect(self.success_url)




@method_decorator([login_required, keeper_required], name='dispatch')
class ItemListView(ListView):
    model = Item
    template_name = 'keeper/items/list.html'
    context_object_name = 'items'
    paginate_by = 10

    def get_queryset(self):
        qs = Item.objects.filter(is_archived=False)
        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category_id=category)
        return qs.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type']     = 'keeper'
        context['selected_category']= self.request.GET.get('category', '')

        # build list of categories that actually have items
        context['categories'] = (
            Category.objects
                    .filter(is_archived=False)
                    .annotate(item_count=Count('items'))
                    .distinct()
                    .order_by('name')
        )
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class ArchivedItemListView(ListView):
    template_name = 'keeper/items/list.html'
    context_object_name = 'items'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Item.objects.filter(is_archived=True).order_by('name')


@method_decorator([login_required, keeper_required], name='dispatch')
class ItemCreateView(CreateView):
    model = Item
    form_class = ItemForm
    template_name = 'keeper/items/create.html'
    success_url = reverse_lazy('item_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class ItemDetailView(DetailView):
    model = Item
    template_name = 'keeper/items/detail.html'
    context_object_name = 'item'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class ItemUpdateView(UpdateView):
    model = Item
    form_class = ItemForm
    template_name = 'keeper/items/edit.html'

    def get_success_url(self):
        return reverse('item_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class ItemDeleteView(DeleteView):
    model = Item
    template_name = 'keeper/items/delete.html'
    success_url = reverse_lazy('item_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class ItemArchiveView(UpdateView):
    model = Item
    template_name = 'keeper/items/delete.html'
    success_url = reverse_lazy('item_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        item = self.get_object()
        item.is_archived = True
        item.save()
        return HttpResponseRedirect(self.success_url)


@method_decorator([login_required, keeper_required], name='dispatch')
class ItemUnArchiveView(UpdateView):
    model = Item
    template_name = 'keeper/items/delete.html'
    success_url = reverse_lazy('item_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        item = self.get_object()
        item.is_archived = False
        item.save()
        return HttpResponseRedirect(self.success_url)