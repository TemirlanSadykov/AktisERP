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
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect, HttpResponseBadRequest
from django.db.models import F, Q, Count
from django.urls import reverse_lazy, reverse
from django.views.generic import FormView
from django.views.decorators.http import require_POST, require_GET
from decimal import Decimal, InvalidOperation
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum, Prefetch
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.functions import Coalesce

from ..utils import apply_client_scope
from ..decorators import keeper_required
from ..forms import *
from ..models import *
from ..scopes import _filter_by_client, _filter_by_warehouse, _filter_by_supplier
from ..scopes import _get_client_scope, _get_warehouse_scope, _get_supplier_scope

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
        qs = (
            super()
            .get_queryset()
            .filter(is_archived=False)
            .select_related("client")
        )

        # scope by client
        qs = apply_client_scope(qs, self.request)

        # ---- status filter (tabs) ----
        # ?status=new | in_progress | completed
        status_param = (self.request.GET.get("status") or "new").lower()
        status_map = {
            "new": ClientOrder.NEW,
            "in_progress": ClientOrder.IN_PROGRESS,
            "completed": ClientOrder.COMPLETED,
        }
        if status_param in status_map:
            qs = qs.filter(status=status_map[status_param])

        # ---- optional date range filter (launch) ----
        form = self.form_class(self.request.GET)
        if form.is_valid():
            start = form.cleaned_data.get("start_date")
            end = form.cleaned_data.get("end_date")
            if start and end:
                qs = qs.filter(launch__range=[start, end])
            elif start:
                qs = qs.filter(launch__gte=start)
            elif end:
                qs = qs.filter(launch__lte=end)

        # default sort by term asc
        qs = qs.order_by("-launch")
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        today = timezone.localdate()

        context["form"] = self.form_class(request.GET or None)

        # Compute days_left safely
        orders_with_days_left = []
        for order in context["orders"]:
            days_left = (order.term - today).days if getattr(order, "term", None) else None
            orders_with_days_left.append({"order": order, "days_left": days_left})
        context["orders_with_days_left"] = orders_with_days_left

        # Current status for active tab
        context["status_filter"] = (request.GET.get("status") or "new").lower()

        # Preserve all current GET params except 'page' for pagination links
        params = request.GET.copy()
        params.pop("page", None)
        context["qs"] = params.urlencode()

        context["ClientOrder"] = ClientOrder
        context["sidebar_type"] = "keeper"
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
class BomDetailView(DetailView):
    model = SizeQuantity
    template_name = 'keeper/orders/bom.html'
    context_object_name = 'size_quantity'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        size_quantity = self.object

        # get the related order from the SizeQuantity
        order = size_quantity.orders.first()
        context['order'] = order

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
class BomDeficitView(DetailView):
    model = Order
    template_name = 'keeper/orders/bom_deficit.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object

        # Days left
        today = timezone.now().date()
        term = order.client_order.term
        context['days_left'] = max((term - today).days, 0)

        # Prefetch size_quantities with their BOMs and items
        size_quantities = (
            order.size_quantities
            .prefetch_related(
                Prefetch(
                    'bill_of_materials',
                    queryset=BillOfMaterials.objects.select_related('item__category')
                )
            )
        )

        # All unique BOM item IDs
        all_bom_items = BillOfMaterials.objects.filter(
            sizequantity__in=size_quantities
        ).values_list('item_id', flat=True).distinct()

        # Available stock per item
        item_ct = ContentType.objects.get_for_model(Item)
        stock_data = (
            Stock.objects
            .filter(
                content_type=item_ct,
                object_id__in=all_bom_items,
                is_archived=False
            )
            .values('object_id')
            .annotate(total_qty=Sum('quantity'))
        )
        stock_lookup = {row['object_id']: row['total_qty'] or 0 for row in stock_data}

        # —— NEW: Pending (В ожидании) from MaterialReceipt ——
        # Only receipts that are NOT posted yet should count as “pending”.
        # We use COALESCE(confirmed_qty, reported_qty) per receipt.
        # Optionally scope by client if your order has a client.
        order_client = getattr(order.client_order, 'client', None)

        pending_qs = MaterialReceipt.objects.filter(
            item_id__in=all_bom_items,
            status__in=[MaterialReceipt.DRAFT, MaterialReceipt.CONFIRMED]
        )
        if order_client:
            pending_qs = pending_qs.filter(client=order_client)

        pending_data = (
            pending_qs
            .values('item_id')
            .annotate(pending_qty=Sum(Coalesce('confirmed_qty', 'reported_qty')))
        )
        pending_lookup = {row['item_id']: row['pending_qty'] or 0 for row in pending_data}
        # —— END NEW ——

        # Annotate each BOM with required, available, missing, pending
        for sq in size_quantities:
            for bom in sq.bill_of_materials.all():
                produced = sq.quantity or 0
                required_qty = (bom.quantity or 0) * produced
                available_qty = stock_lookup.get(bom.item_id, 0)
                missing_qty = max(required_qty - available_qty, 0)

                bom.required_qty = required_qty
                bom.available_qty = available_qty
                bom.missing_qty = missing_qty

                # NEW:
                bom.pending_qty = pending_lookup.get(bom.item_id, 0)

        context['size_quantities'] = size_quantities
        context['suppliers'] = Supplier.objects.filter(is_archived=False).only('id', 'name').order_by('name')
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
            'supplier_description': supplier.description
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
        rollbatch_id = self.kwargs.get('rollbatch_id')
        roll_type = self.request.GET.get('roll_type', 'whole')
        if roll_type == 'remainders':
            return Roll.objects.filter(
                is_used=False,
                roll_batch_id=rollbatch_id,
                original_roll__isnull=False
            ).order_by('length_t')
        else:
            return Roll.objects.filter(
                is_used=False,
                roll_batch_id=rollbatch_id,
                original_roll__isnull=True
            ).order_by('length_t')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        context['roll_type'] = self.request.GET.get('roll_type', 'whole')
        context['rollbatch_id'] = self.kwargs.get('rollbatch_id')

        first_roll = context['rolls'][0] if context['rolls'] else None
        if first_roll:
            context['rollbatch'] = first_roll.roll_batch
            context['color'] = first_roll.color.name
            context['fabric'] = first_roll.fabric.name
            context['width'] = first_roll.width
            context['supplier'] = first_roll.supplier.name
            context['client'] = first_roll.client.name if first_roll.client else "-"
        else:
            context['rollbatch'] = ''

        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollBulkCreateView(CreateView):
    model = Roll
    form_class = BulkRollForm
    template_name = "keeper/rolls/bulk_create.html"
    success_url = reverse_lazy("stock_list")  # fallback

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    @transaction.atomic
    def form_valid(self, form):
        color     = form.cleaned_data["color"]
        fabric    = form.cleaned_data["fabric"]
        supplier  = form.cleaned_data["supplier"]
        client    = form.cleaned_data["client"]
        width     = form.cleaned_data["width"]
        quantity  = form.cleaned_data["quantity"]
        category  = form.cleaned_data["category"]
        price     = form.cleaned_data["price"]
        sku       = form.cleaned_data["sku"]

        weights_raw = self.request.POST.getlist("weight")
        lengths_raw = self.request.POST.getlist("length")

        parse = lambda v: (Decimal(v) if (v or "").strip() else None)
        weights = [parse(w) for w in weights_raw]
        lengths = [parse(l) for l in lengths_raw]

        company = get_current_company()
        warehouse = Warehouse.objects.filter(is_archived=False).first()

        # ---- 1) Ensure/resolve RollBatch (Item)
        batch, _ = Item.objects.get_or_create(
            company=company,
            sku=sku,
            color=color,
            fabric=fabric,
            width=width,
            category=category,
            unit="м",
            defaults={
                "name": f"{color.name} {fabric.name} {width}м",
            }
        )

        # ---- 2) Pre-compute reported meters from provided lengths
        metres_in = Decimal("0")
        for i in range(min(quantity, len(lengths))):
            if lengths[i] is not None:
                metres_in += lengths[i]

        # ---- 3) Create MaterialReceipt FIRST (no Stock updates here)
        receipt = MaterialReceipt.objects.create(
            company=company,
            item=batch,
            supplier=supplier,
            warehouse=warehouse,
            client=client,
            cost=price,
            reported_qty=metres_in,  # sum of known lengths; can be adjusted on confirm
            status=MaterialReceipt.DRAFT,
            note="Автосоздано из массового приема рулонов",
        )

        # ---- 4) Bulk-create rolls linked to this receipt
        # Sequential numbering continues within same (color, fabric, supplier, client)
        start_idx = Roll.objects.filter(
            roll_batch = batch,
        ).count()

        new_rolls = []
        for i in range(quantity):
            length_val = lengths[i] if i < len(lengths) else None
            weight_val = weights[i] if i < len(weights) else None

            new_rolls.append(
                Roll(
                    company=company,
                    roll_batch=batch,
                    color=color,
                    fabric=fabric,
                    supplier=supplier,
                    client=client,
                    width=width,
                    name=start_idx + i + 1,  # 1..N numbering
                    length_t=length_val,     # your intake length field
                    weight=weight_val,
                    material_receipt=receipt # <-- explicit linkage
                )
            )

        if new_rolls:
            Roll.objects.bulk_create(new_rolls)

        # ---- 5) Redirect
        self.object = new_rolls[0] if new_rolls else None
        try:
            return redirect('material_receipt_list')
        except Exception:
            return HttpResponseRedirect(self.get_success_url())

@method_decorator([login_required, keeper_required], name='dispatch')
class StockListView(ListView):
    model = Stock
    template_name = 'keeper/stocks/list.html'
    context_object_name = 'stocks'
    paginate_by = 10

    def get_queryset(self):
        qs = Stock.objects.filter(is_archived=False)
        stock_type = self.request.GET.get('type', '2')
        client_id = self.request.GET.get('client', '0')
        try:
            client_id = int(client_id)
        except ValueError:
            client_id = 0  

        if stock_type in ['0', '1', '2']:
            qs = qs.filter(type=int(stock_type))
        else:
            qs = qs.filter(type=2)

        # Filter by client if provided
        if client_id != 0:
            filtered_ids = []

            for stock in qs:
                content = stock.content_object
                if hasattr(content, 'client') and content.client_id == client_id:
                    filtered_ids.append(stock.id)
                elif isinstance(content, SizeQuantity):
                    orders = content.orders.select_related('client_order__client')
                    if any(order.client_order.client_id == client_id for order in orders):
                        filtered_ids.append(stock.id)
                elif hasattr(content, 'order'):
                    if hasattr(content.order, 'client_order') and content.order.client_order.client_id == client_id:
                        filtered_ids.append(stock.id)

            qs = qs.filter(id__in=filtered_ids)

        self.selected_type = stock_type
        self.selected_client = client_id
        return qs.order_by('id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        context['selected_type'] = self.request.GET.get('type', '2')
        context['selected_client'] = self.request.GET.get('client', '0')
        context['suppliers'] = Supplier.objects.filter(is_archived=False)
        context['categories'] = Category.objects.filter(is_archived=False)
        context['colors'] = Color.objects.filter(is_archived=False)
        context['fabrics'] = Fabric.objects.filter(is_archived=False)
        context['clients'] = Client.objects.filter(is_archived=False)
        context['warehouses'] = Warehouse.objects.filter(is_archived=False)

        for stock in context['stocks']:
            if stock.type == Stock.ROLLS:
                stock.unit_display = 'м'
            elif stock.type == Stock.FINISHED_GOODS:
                stock.unit_display = 'шт'
            else:
                stock.unit_display = getattr(stock.content_object, 'unit', '')

            if stock.type == Stock.ROLLS:
                stock.category_display = "Рулон"
            elif stock.type == Stock.FINISHED_GOODS:
                stock.category_display = "Готовая продукция"
            else:
                stock.category_display = getattr(stock.content_object, 'category', 'Сырье')

        return context
    
def _get_category_filter(request):
    """
    Read ?category= from querystring.
    Returns 'all' or an int category_id.
    """
    val = request.GET.get('category', 'all')
    try:
        return int(val)
    except (TypeError, ValueError):
        return 'all'


def _filter_by_category(qs, category_filter):
    """
    Filters Stock queryset by Category when the content_object has `category_id`.
    Works for heterogeneous GFK content by doing a compact Python-side filter.
    """
    if category_filter == 'all':
        return qs

    filtered_ids = []
    for stock in qs:
        obj = stock.content_object
        cid = getattr(obj, 'category_id', None)
        if cid == category_filter:
            filtered_ids.append(stock.id)

    return qs.filter(id__in=filtered_ids)

class BaseKeeperStockList(ListView):
    """
    Shared bits for the three pages. Subclasses must set STOCK_TYPE and TEMPLATE_NAME.
    """
    model = Stock
    context_object_name = 'stocks'
    paginate_by = 10
    STOCK_TYPE = None
    TEMPLATE_NAME = None

    @method_decorator([login_required, keeper_required], name='dispatch')
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        assert self.STOCK_TYPE in (Stock.RAW_MATERIALS, Stock.FINISHED_GOODS, Stock.ROLLS)
        qs = Stock.objects.filter(is_archived=False, type=self.STOCK_TYPE)

        # Scope by client (from sidebar session)
        client_scope = _get_client_scope(self.request)
        qs = _filter_by_client(qs, client_scope)

        # Category filter (from tabs)
        category_filter = _get_category_filter(self.request)
        qs = _filter_by_category(qs, category_filter)

        warehouse_scope = _get_warehouse_scope(self.request)
        qs = _filter_by_warehouse(qs, warehouse_scope)

        supplier_scope = _get_supplier_scope(self.request)
        qs = _filter_by_supplier(qs, supplier_scope)


        return qs.order_by('id')

    def get_template_names(self):
        return [self.TEMPLATE_NAME]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Sidebar + selects (yours)
        ctx['sidebar_type'] = 'keeper'
        ctx['clients'] = Client.objects.filter(is_archived=False)
        ctx['suppliers'] = Supplier.objects.filter(is_archived=False)
        ctx['colors'] = Color.objects.filter(is_archived=False)
        ctx['fabrics'] = Fabric.objects.filter(is_archived=False)
        ctx['warehouses'] = Warehouse.objects.filter(is_archived=False)
        if self.STOCK_TYPE == Stock.ROLLS:
            categories = Category.objects.filter(is_archived=False, is_fabric=True)
        else:
            categories = Category.objects.filter(is_archived=False, is_fabric=False)
        ctx['categories'] = categories
        # Current scope (yours)
        client_scope = _get_client_scope(self.request)
        ctx['selected_client_scope'] = client_scope  # 'all' | 'shared' | int

        # Category tabs state
        ctx['selected_category_id'] = _get_category_filter(self.request)
        ctx['categories_for_tabs'] = ctx['categories']  # alias for clarity in templates

        return ctx
# ---------- 3 focused pages ----------

class RollsStockListView(BaseKeeperStockList):
    """
    Materials → Fabrics (Rolls)
    """
    STOCK_TYPE = Stock.ROLLS        # usually 2
    TEMPLATE_NAME = 'keeper/stocks/rolls_list.html'


class RawMaterialsStockListView(BaseKeeperStockList):
    """
    Materials → Accessories / Other Raw Materials
    """
    STOCK_TYPE = Stock.RAW_MATERIALS          # usually 0
    TEMPLATE_NAME = 'keeper/stocks/raw_materials_list.html'


@method_decorator([login_required], name='dispatch')
class FinishedGoodsStockListView(ListView):
    """
    Finished Goods: completely separate page & template with its own display.
    Shows one row per SizeQuantity-backed Stock with model/variant/size columns.
    """
    model = Stock
    context_object_name = 'fg_stocks'
    template_name = 'keeper/stocks/finished_goods_list.html'
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Stock.objects
            .filter(is_archived=False, type=Stock.FINISHED_GOODS)
            .select_related()  # harmless; GFK stays lazy but keep for consistency
            .order_by('id')
        )

        # Client scoping (reuse your helper exactly as-is)
        client_scope = _get_client_scope(self.request)
        qs = _filter_by_client(qs, client_scope)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Sidebar filters (keep the same lists you already surface elsewhere)
        ctx['sidebar_type'] = 'keeper'
        ctx['clients'] = Client.objects.filter(is_archived=False)
        ctx['suppliers'] = Supplier.objects.filter(is_archived=False)
        ctx['colors'] = Color.objects.filter(is_archived=False)
        ctx['fabrics'] = Fabric.objects.filter(is_archived=False)
        ctx['warehouses'] = Warehouse.objects.filter(is_archived=False)

        # keep current client scope to highlight the sidebar selection
        ctx['selected_client_scope'] = _get_client_scope(self.request)

        # This page intentionally has NO category tabs or shared stock table.
        # Build lightweight presentation attrs for the template:
        rows = []
        for s in ctx['fg_stocks']:
            obj = s.content_object  # expected to be SizeQuantity-backed
            model_name = getattr(getattr(obj, 'model', None), 'name', None) or str(obj)
            color_name = getattr(getattr(obj, 'color', None), 'name', None)
            fabric_name = getattr(getattr(obj, 'fabric', None), 'name', None)
            size_label = getattr(obj, 'size', None) or getattr(obj, 'size_label', None)
            variant = " / ".join([v for v in (color_name, fabric_name) if v]) or "—"
            unit = "шт"  # finished goods pieces; adjust if you store per-obj unit

            rows.append({
                'id': s.id,
                'sq_id': getattr(obj, 'pk', None),
                'model_name': model_name,
                'variant': variant,
                'size': size_label or "—",
                'quantity': s.quantity,
                'unit': unit,
                'last_supplied_date': s.last_supplied_date,
                'last_cost': s.last_cost,
            })

        ctx['rows'] = rows
        return ctx


@login_required
@require_GET
def stock_item_json(request, stock_id):
    try:
        stock = Stock.objects.get(pk=stock_id, is_archived=False)
    except Stock.DoesNotExist:
        return JsonResponse({"success": False, "message": "Stock not found."}, status=404)

    # Resolve item from content_object or nested .item
    content = stock.content_object
    item = content if isinstance(content, Item) else (getattr(content, 'item', None) if isinstance(getattr(content, 'item', None), Item) else None)
    if not item:
        return JsonResponse({"success": False, "message": "Item not found for this stock."}, status=404)

    is_roll = (stock.type == Stock.ROLLS)

    return JsonResponse({
        "success": True,
        "stock": {
            "id": stock.id,
            "last_cost": str(stock.last_cost) if stock.last_cost is not None else "",
            "quantity": str(stock.quantity) if stock.quantity is not None else "",
            "warehouse_id": stock.warehouse_id,
        },
        "item_id": item.id,
        "is_roll": is_roll,
        "fields": {
            "name": item.name or "",
            "sku": item.sku or "",
            "description": item.description or "",
            "unit": item.unit or "",
            "category_id": item.category_id,
            "supplier_id": stock.last_supplier.id if stock.last_supplier else "",
            "client_id": stock.client.id if stock.client else "",
            # roll-specific
            "color_id": item.color_id,
            "fabric_id": item.fabric_id,
            "width": str(item.width) if item.width is not None else "",
        }
    }, status=200)


@login_required
@require_POST
@transaction.atomic
def item_update(request, pk):
    import json
    from decimal import Decimal, InvalidOperation

    try:
        item = Item.objects.select_for_update().get(pk=pk, is_archived=False)
    except Item.DoesNotExist:
        return JsonResponse({"success": False, "message": "Item not found."}, status=404)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({"success": False, "message": "Invalid JSON."}, status=400)

    is_roll = bool(payload.get("is_roll", False))
    f = payload.get("fields", {})

    # ---- Item fields ----
    item.name = (f.get("name") or "").strip()
    item.sku = (f.get("sku") or "").strip() or None
    item.description = (f.get("description") or "").strip() or None
    item.unit = (f.get("unit") or "").strip() or None

    def get_fk(model, key):
        val = f.get(key)
        if val in ("", None):
            return None
        try:
            return model.objects.get(pk=int(val))
        except (ValueError, ObjectDoesNotExist):
            return None

    item.category = get_fk(Category, "category_id")

    width_submitted = "width" in f
    width_decimal = None
    if width_submitted:
        w_raw = (f.get("width") or "").strip()
        if w_raw == "":
            width_decimal = None
        else:
            try:
                width_decimal = Decimal(w_raw)
            except InvalidOperation:
                return JsonResponse({"success": False, "message": "Invalid width."}, status=400)

    if is_roll:
        item.color  = get_fk(Color, "color_id")
        item.fabric = get_fk(Fabric, "fabric_id")
        item.width  = width_decimal
    else:
        item.color = None
        item.fabric = None
        item.width = None if width_submitted else item.width

    item.save()

    # ---- Propagate to child Rolls (only for provided fields) ----
    rolls_qs = Roll.objects.select_for_update().filter(roll_batch=item)
    if rolls_qs.exists():
        updates = {}

        def get_id(key):
            val = f.get(key)
            if val in ("", None):
                return None
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        if "fabric_id" in f:
            fabric_id = get_id("fabric_id")
            if fabric_id is None:
                return JsonResponse({"success": False, "message": "Fabric is required for rolls."}, status=400)
            updates["fabric_id"] = fabric_id

        if "color_id" in f:
            color_id = get_id("color_id")
            if color_id is None:
                return JsonResponse({"success": False, "message": "Color is required for rolls."}, status=400)
            updates["color_id"] = color_id

        if "supplier_id" in f:
            supplier_id = get_id("supplier_id")
            if supplier_id is None:
                return JsonResponse({"success": False, "message": "Supplier is required for rolls."}, status=400)
            updates["supplier_id"] = supplier_id

        if "client_id" in f:
            updates["client_id"] = get_id("client_id")

        if width_submitted:
            updates["width"] = width_decimal

        if updates:
            rolls_qs.update(**updates)

    # ---- Update the specific Stock row if provided ----
    stock_payload = payload.get("stock")
    if stock_payload:
        try:
            stock = Stock.objects.select_for_update().get(pk=int(stock_payload.get("id")))
        except (Stock.DoesNotExist, TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Stock not found."}, status=404)

        # Safety: ensure this stock belongs to this item (directly or via .item)
        content = stock.content_object
        content_item = content if isinstance(content, Item) else getattr(content, "item", None)
        if not isinstance(content_item, Item) or content_item.pk != item.pk:
            return JsonResponse({"success": False, "message": "Stock does not belong to this item."}, status=400)

        if "last_cost" in stock_payload:
            lc_raw = (stock_payload.get("last_cost") or "").strip()
            if lc_raw == "":
                stock.last_cost = None
            else:
                try:
                    stock.last_cost = Decimal(lc_raw)
                except InvalidOperation:
                    return JsonResponse({"success": False, "message": "Invalid last_cost."}, status=400)

        if "quantity" in stock_payload:
            q_raw = (stock_payload.get("quantity") or "").strip()
            if q_raw == "":
                return JsonResponse({"success": False, "message": "Quantity is required."}, status=400)
            try:
                stock.quantity = Decimal(q_raw)
            except InvalidOperation:
                return JsonResponse({"success": False, "message": "Invalid quantity."}, status=400)

        if "warehouse_id" in stock_payload:
            wid = stock_payload.get("warehouse_id")
            if wid in ("", None):
                stock.warehouse = None
            else:
                try:
                    stock.warehouse = Warehouse.objects.get(pk=int(wid))
                except (Warehouse.DoesNotExist, TypeError, ValueError):
                    return JsonResponse({"success": False, "message": "Invalid warehouse."}, status=400)

        stock.save()

    return JsonResponse({"success": True, "message": "Item and stock updated."}, status=200)

@login_required
@require_POST
@keeper_required
def stock_delete(request, pk):
    """
    Deletes only the Stock entry. Does NOT delete Item/Roll/Product behind content_object.
    """
    try:
        stock = Stock.objects.get(pk=pk)
    except Stock.DoesNotExist:
        # If you prefer JSON:
        # return JsonResponse({"success": False, "message": "Stock not found."}, status=404)
        return redirect(request.META.get('HTTP_REFERER', reverse('stock_list')))

    stock.delete()
    # If you’re using messages, you could add a success message here.
    return redirect(request.META.get('HTTP_REFERER', reverse('stock_list')))

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
        categories = Category.objects.filter(is_archived=False, is_fabric=False).order_by('name')
        items = Item.objects.filter(is_archived=False).order_by('name')
        items_by_category = defaultdict(list)
        for it in items:
            items_by_category[it.category_id].append(it)

        return render(request, 'keeper/stocks/bulk_create.html', {
            'categories':        categories,
            'items_by_category': dict(items_by_category),
            'suppliers':         Supplier.objects.filter(is_archived=False),
            'clients':           Client.objects.filter(is_archived=False),
            'warehouses':        Warehouse.objects.filter(is_archived=False).order_by('name'),
            'sidebar_type':      'keeper',
        })

    # POST: create MaterialReceipt rows (no stock updates here)
    company = get_current_company()

    # Optional header-level selections
    supplier_id  = request.POST.get('supplier')   # expect <select name="supplier">
    client_id    = request.POST.get('client')     # expect <select name="client">
    warehouse_id = request.POST.get('warehouse')  # expect <select name="warehouse">

    supplier  = Supplier.objects.filter(pk=supplier_id).first() if supplier_id else None
    client    = Client.objects.filter(pk=client_id).first() if client_id else None

    if warehouse_id:
        warehouse = Warehouse.objects.filter(pk=warehouse_id, is_archived=False).first()
    else:
        warehouse = Warehouse.objects.filter(is_archived=False).first()

    # Iterate dynamic rows
    row = 0
    created = 0

    with transaction.atomic():
        while f'row-{row}_item' in request.POST:
            item_id   = request.POST.get(f'row-{row}_item')
            qty_str   = request.POST.get(f'row-{row}_quantity')
            price_str = request.POST.get(f'row-{row}_price')
            note      = request.POST.get(f'row-{row}_note')  # optional if you add it in UI

            # Allow per-row overrides (if your template includes these)
            row_supplier_id  = request.POST.get(f'row-{row}_supplier')
            row_client_id    = request.POST.get(f'row-{row}_client')
            row_warehouse_id = request.POST.get(f'row-{row}_warehouse')

            row_supplier  = Supplier.objects.filter(pk=row_supplier_id).first() if row_supplier_id else supplier
            row_client    = Client.objects.filter(pk=row_client_id).first() if row_client_id else client
            row_warehouse = (Warehouse.objects.filter(pk=row_warehouse_id, is_archived=False).first()
                             if row_warehouse_id else warehouse)

            if item_id and qty_str:
                # Parse cost/qty
                cost = None
                if price_str:
                    try:
                        cost = Decimal(price_str)
                    except (InvalidOperation, TypeError):
                        cost = None

                try:
                    reported_qty = Decimal(qty_str)
                except (InvalidOperation, TypeError):
                    reported_qty = None

                if reported_qty is not None:
                    item = get_object_or_404(Item, pk=item_id)

                    # Create MaterialReceipt in DRAFT (inventory updates happen on "post")
                    MaterialReceipt.objects.create(
                        company=company,
                        item=item,
                        supplier=row_supplier,
                        client=row_client,
                        warehouse=row_warehouse,
                        cost=cost,  # cost per unit (optional)
                        reported_qty=reported_qty,
                        confirmed_qty=None,     # can be filled later during verification
                        status=MaterialReceipt.DRAFT,
                        posted_at=None,
                        note=note or 'Bulk receipt entry',
                    )
                    created += 1

            row += 1

    # You can send them to a receipts list if you have it; keeping existing redirect for now.
    return redirect('material_receipt_list')

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
    
@login_required
@keeper_required
@require_POST
def shipment_complete(request):
    try:
        data = json.loads(request.body)
        sq_id = data.get('size_quantity_id')
        quantity = data.get('quantity')

        if not sq_id or quantity is None:
            return JsonResponse({'success': False, 'message': 'Missing required fields.'})

        # Get the SizeQuantity object
        sq_obj = SizeQuantity.objects.get(pk=sq_id)
        ship_quantity = Decimal(str(quantity))

        # Get the Stock record for this SizeQuantity (assumes 1:1 mapping)
        content_type = ContentType.objects.get_for_model(sq_obj)
        stock = Stock.objects.filter(
            content_type=content_type,
            object_id=sq_obj.pk,
            type=Stock.FINISHED_GOODS,
            is_archived=False
        ).first()

        if not stock:
            return JsonResponse({'success': False, 'message': 'No stock available for this item.'})

        # Subtract the quantity
        stock.quantity -= ship_quantity
        stock.save()

        # Record StockMovement
        StockMovement.objects.create(
            stock=stock,
            movement_type='OUT',
            quantity=ship_quantity,
            from_warehouse=stock.warehouse,
            to_warehouse=None,
            note="Отправка"
        )

        # Update shipment status and shipped count
        sq_obj.shipped = ship_quantity
        sq_obj.shipment_complete = True
        sq_obj.save()

        return JsonResponse({'success': True})

    except SizeQuantity.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Size quantity not found.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

class _ContentTypeMovementBase(ListView):
    """
    Abstract: lists StockMovement filtered by stock.content_type (and optionally stock.type).
    Subclasses must set:
      - CONTENT_MODEL   -> the Django model used for ContentType filtering (Item / SizeQuantity)
      - STOCK_TYPE_FLAG -> one of Stock.RAW_MATERIALS / Stock.FINISHED_GOODS (optional but safer)
      - PAGE_TITLE      -> string for header
    """
    model = StockMovement
    template_name = 'keeper/stocks/stock_movement.html'
    context_object_name = 'movements'
    paginate_by = 20

    # subclass hooks
    CONTENT_MODEL = None
    STOCK_TYPE_FLAG = None
    PAGE_TITLE = 'Stock Movements'

    @classmethod
    def get_content_type(cls):
        # for_concrete_model=False keeps proxy/abstract specifics correct if you use them
        return ContentType.objects.get_for_model(cls.CONTENT_MODEL, for_concrete_model=False)

    def get_queryset(self):
        assert self.CONTENT_MODEL is not None, "Set CONTENT_MODEL on subclass"
        qs = (
            StockMovement.objects
            .select_related(
                'stock__content_type',
                'from_warehouse',
                'to_warehouse',
            )
            .filter(stock__content_type=self.get_content_type())
            .order_by('-created_at')
        )
        # Also gate by Stock.type if you want the extra safety
        if self.STOCK_TYPE_FLAG is not None:
            qs = qs.filter(stock__type=self.STOCK_TYPE_FLAG)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['sidebar_type'] = 'keeper'
        ctx['page_title'] = self.PAGE_TITLE
        ctx['active_tab'] = getattr(self, 'ACTIVE_TAB', None)
        return ctx


@method_decorator([login_required, keeper_required], name='dispatch')
class RawMaterialMovementListView(_ContentTypeMovementBase):
    """
    Movements where stock.content_object is an Item (raw materials).
    """
    CONTENT_MODEL = Item
    STOCK_TYPE_FLAGS = [Stock.RAW_MATERIALS, Stock.ROLLS]
    PAGE_TITLE = 'Raw Materials Movements'
    ACTIVE_TAB = 'raw'


@method_decorator([login_required, keeper_required], name='dispatch')
class FinishedGoodsMovementListView(_ContentTypeMovementBase):
    """
    Movements where stock.content_object is a SizeQuantity (finished goods).
    """
    CONTENT_MODEL = SizeQuantity
    STOCK_TYPE_FLAG = Stock.FINISHED_GOODS
    PAGE_TITLE = 'Finished Goods Movements'
    ACTIVE_TAB = 'fg'

    
@login_required
@keeper_required
@require_POST
def complete_shipment(request):
    try:
        data = json.loads(request.body)
        sq_id = data.get('size_quantity_id')
        if not sq_id:
            return JsonResponse({'success': False, 'message': 'Missing size_quantity_id.'})

        sq_obj = SizeQuantity.objects.get(pk=sq_id)

        # Get warehouse
        warehouse = Warehouse.objects.filter(is_archived=False).first()
        if not warehouse:
            return JsonResponse({'success': False, 'message': 'No available warehouse.'})

        content_type = ContentType.objects.get_for_model(sq_obj)

        # Find the finished goods stock
        stock = Stock.objects.filter(
            content_type=content_type,
            object_id=sq_obj.pk,
            warehouse=warehouse,
            type=Stock.FINISHED_GOODS,
            is_archived=False
        ).first()

        if not stock:
            return JsonResponse({'success': False, 'message': 'Finished goods stock not found.'})

        stock_quantity = stock.quantity or Decimal(0)

        if stock_quantity <= 0:
            return JsonResponse({'success': False, 'message': 'Nothing to ship. Stock quantity is zero.'})

        with transaction.atomic():
            # Reduce the stock to zero
            stock.quantity = 0
            stock.save(update_fields=['quantity'])

            # Create stock movement OUT
            StockMovement.objects.create(
                stock=stock,
                movement_type='OUT',
                quantity=stock_quantity,
                from_warehouse=warehouse,
                to_warehouse=None,
                note="Отправка"
            )

            # Update SizeQuantity
            sq_obj.shipped = stock_quantity
            sq_obj.shipment_complete = True
            sq_obj.save(update_fields=['shipped', 'shipment_complete'])

        return JsonResponse({'success': True})

    except SizeQuantity.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Size quantity not found.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@method_decorator([login_required, keeper_required], name='dispatch')
class ReceiptListView(ListView):
    model = ProductionReceipt
    template_name = 'keeper/receipts/list.html'
    context_object_name = 'receipts'
    paginate_by = 10

    def get_queryset(self):
        return (
            ProductionReceipt.objects
            .filter(status=ProductionReceipt.DRAFT)
            .select_related('size_quantity__model', 'size_quantity__color', 'size_quantity__fabric')
            .order_by('id')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context
    
@login_required
@require_POST
@keeper_required
def post_receipt(request, receipt_id):
    try:
        with transaction.atomic():
            data = json.loads(request.body)
            confirmed_qty = Decimal(data.get("confirmed_qty", 0))

            if confirmed_qty <= 0:
                return JsonResponse({'success': False, 'message': 'Invalid quantity'}, status=400)

            receipt = ProductionReceipt.objects.select_for_update().get(pk=receipt_id)

            if receipt.status == ProductionReceipt.CONFIRMED:
                return JsonResponse({'success': False, 'message': 'Already posted.'})

            # Update receipt
            receipt.confirmed_qty = confirmed_qty
            receipt.status = ProductionReceipt.CONFIRMED
            receipt.posted_at = timezone.now()
            receipt.save(update_fields=["confirmed_qty", "status", "posted_at"])

            # Create or fetch warehouse
            warehouse = Warehouse.objects.filter(is_archived=False).first()
            if not warehouse:
                warehouse = Warehouse.objects.create(name="Default", is_archived=False)

            # Create stock
            sq = receipt.size_quantity
            content_type = ContentType.objects.get_for_model(sq)

            stock, created = Stock.objects.get_or_create(
                content_type=content_type,
                object_id=sq.pk,
                warehouse=warehouse,
                type=Stock.FINISHED_GOODS,
                defaults={
                    'quantity': confirmed_qty,
                    'is_archived': False,
                    'company': sq.company,
                    'last_supplied_date': timezone.now()
                }
            )

            if not created:
                # If it already existed, increment its quantity
                stock.quantity += confirmed_qty
                stock.last_supplied_date = timezone.now()
                stock.save(update_fields=['quantity'])

            StockMovement.objects.create(
                stock=stock,
                movement_type="IN",
                quantity=confirmed_qty,
                production_receipt=receipt,
                to_warehouse=warehouse,
                note=f"Прием готовой продукции: {sq}"
            )

        return JsonResponse({'success': True})

    except ProductionReceipt.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Receipt not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
@require_POST
@login_required
@keeper_required
def delete_receipt(request, receipt_id):
    try:
        receipt = ProductionReceipt.objects.get(pk=receipt_id)
        receipt.delete()
        return JsonResponse({'success': True})
    except ProductionReceipt.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Receipt not found.'}, status=404)
    
@require_POST
@login_required
@keeper_required
def complete_purchase(request):
    order_id     = request.POST.get("order_id")
    item_id      = request.POST.get("item_id")
    supplier_id  = request.POST.get("supplier_id")
    qty          = request.POST.get("quantity")
    cost         = request.POST.get("cost")

    order     = get_object_or_404(Order, pk=order_id)
    item      = get_object_or_404(Item, pk=item_id)
    supplier  = get_object_or_404(Supplier, pk=supplier_id)
    warehouse = Warehouse.objects.filter(is_archived=False).first()
    client = order.client_order.client

    receipt = MaterialReceipt(
        item=item,
        supplier=supplier,
        warehouse=warehouse,
        cost=cost,
        client=client,
        reported_qty=qty,
        status=MaterialReceipt.DRAFT,
    )
    receipt.save()

    return redirect("bom_deficit", pk=order_id)

@method_decorator([login_required, keeper_required], name='dispatch')
class MaterialReceiptListView(ListView):
    model = MaterialReceipt
    template_name = 'keeper/receipts/materials_list.html'
    context_object_name = 'receipts'
    paginate_by = 10

    def get_queryset(self):
        return (
            MaterialReceipt.objects
            .filter(status=MaterialReceipt.DRAFT)
            .select_related('item', 'supplier', 'client', 'warehouse')
            .annotate(roll_count=Count('rolls'))
            .order_by('id')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@login_required
@require_POST
@keeper_required
def post_material_receipt(request, receipt_id):
    try:
        with transaction.atomic():
            data = json.loads(request.body or "{}")
            try:
                confirmed_qty = Decimal(str(data.get("confirmed_qty", "0")))
            except Exception:
                return HttpResponseBadRequest("Invalid confirmed_qty")

            if confirmed_qty <= 0:
                return JsonResponse({'success': False, 'message': 'Invalid quantity'}, status=400)

            receipt = MaterialReceipt.objects.select_for_update().get(pk=receipt_id)

            # Already posted? (MaterialReceipt supports POSTED)
            if receipt.status == MaterialReceipt.POSTED:
                return JsonResponse({'success': False, 'message': 'Already posted.'})

            # Determine stock type: rolls if item has width, else raw materials
            item = receipt.item
            is_rolls = bool(getattr(item, "width", None))
            stock_type = getattr(Stock, "ROLLS", None) if is_rolls else getattr(Stock, "RAW_MATERIALS", None)
            if stock_type is None:
                return JsonResponse({'success': False, 'message': 'Unknown stock type mapping.'}, status=500)

            # Update receipt to POSTED
            receipt.confirmed_qty = confirmed_qty
            receipt.status = MaterialReceipt.POSTED
            receipt.posted_at = timezone.now()
            receipt.save(update_fields=["confirmed_qty", "status", "posted_at"])

            # Ensure there is a warehouse
            warehouse = Warehouse.objects.filter(is_archived=False).first()
            if not warehouse:
                warehouse = Warehouse.objects.create(name="Default", is_archived=False)

            # Create / update Stock for the ITEM
            content_type = ContentType.objects.get_for_model(item)
            supplier = getattr(receipt, "supplier", None)   # if MaterialReceipt has supplier FK
            client   = getattr(receipt, "client", None)     # if MaterialReceipt has client FK

            stock, created = Stock.objects.get_or_create(
                content_type=content_type,
                object_id=item.pk,
                warehouse=warehouse,
                type=stock_type,
                client=client,
                defaults={
                    'quantity': confirmed_qty,
                    'is_archived': False,
                    'company': receipt.company,  # CompanyAwareModel
                    'last_supplied_date': timezone.now(),
                    'last_cost': Decimal(str(data.get("cost"))),
                    'last_supplier': supplier,
                }
            )

            if not created:
                stock.quantity += confirmed_qty
                stock.last_supplied_date = timezone.now()
                stock.last_supplier = supplier
                stock.last_cost = Decimal(str(data.get("cost")))  # update cost if provided
                stock.save(update_fields=[
                    'quantity',
                    'last_supplied_date',
                    'last_supplier',
                    'client',
                    'last_cost',
                ])

            StockMovement.objects.create(
                stock=stock,
                movement_type="IN",
                quantity=confirmed_qty,
                material_receipt=receipt,
                to_warehouse=warehouse,
                note=f"Поступление материалов: {item}"
            )

        return JsonResponse({'success': True})

    except MaterialReceipt.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Receipt not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@require_POST
@login_required
@keeper_required
def delete_material_receipt(request, receipt_id):
    try:
        receipt = MaterialReceipt.objects.get(pk=receipt_id)
        receipt.delete()
        return JsonResponse({'success': True})
    except MaterialReceipt.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Receipt not found.'}, status=404)

@login_required
@keeper_required
@require_GET
def material_receipt_rolls_view(request, receipt_id):
    """
    GET /api/material_receipt_rolls/?receipt_id=123
    Returns the rolls for a materials receipt as JSON:
    {
      "success": true,
      "rolls": [
        {"id": 1, "color": "Red", "fabric": "Cotton", "width": "1.60", "name": 12, "length_t": "100.00"},
        ...
      ]
    }
    """
    if not receipt_id:
        return JsonResponse({"success": False, "message": "Missing 'receipt_id'."}, status=400)

    try:
        # Ensure receipt exists (and optionally belongs to user's tenant)
        rec_qs = MaterialReceipt.objects.filter(id=receipt_id)
        receipt = rec_qs.select_related(None).only('id').first()
        if not receipt:
            return JsonResponse({"success": False, "message": "Receipt not found."}, status=404)

        rolls_qs = Roll.objects.filter(material_receipt_id=receipt_id) \
                               .select_related('color', 'fabric') \
                               .only('id', 'name', 'width', 'length_t', 'color__name', 'fabric__name')

        data = []
        for r in rolls_qs:
            data.append({
                "id": r.id,
                "color": getattr(r.color, 'name', None),
                "fabric": getattr(r.fabric, 'name', None),
                "width": None if r.width is None else str(r.width),
                "name": r.name,
                "length_t": None if r.length_t is None else str(r.length_t),
            })

        return JsonResponse({"success": True, "rolls": data})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)

@login_required
@keeper_required
@require_POST
@transaction.atomic
def save_material_receipt_rolls_view(request):
    """
    POST /api/material_receipt_rolls/save/
    Body:
      {
        "receipt_id": 123,
        "rolls": [{"id": 1, "length_t": 98.5}, ...],
        "cost": 12.34               # optional; per-unit cost (m)
      }

    Behavior:
      - Validates receipt (and not already posted)
      - Saves provided rolls' length_t (only for rolls belonging to the receipt)
      - If incoming length_t == 0 => deletes that roll
      - Sums length_t across ALL remaining rolls of this receipt to get confirmed_qty
      - Marks receipt POSTED, sets posted_at, confirmed_qty
      - Increments/creates Stock for the Item (type=ROLLS), updates last_* fields
      - Adds StockMovement IN
    """
    try:
        payload = json.loads(request.body.decode('utf-8') or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON."}, status=400)

    receipt_id = payload.get('receipt_id')
    rolls_payload = payload.get('rolls', [])

    if not receipt_id:
        return JsonResponse({"success": False, "message": "Missing 'receipt_id'."}, status=400)

    # Lock the receipt row for the transaction
    try:
        receipt = MaterialReceipt.objects.select_for_update().get(id=receipt_id)
    except MaterialReceipt.DoesNotExist:
        return JsonResponse({"success": False, "message": "Receipt not found."}, status=404)

    # Already posted?
    if getattr(receipt, "status", None) == getattr(MaterialReceipt, "POSTED", None):
        return JsonResponse({"success": False, "message": "Already posted."}, status=400)

    if not isinstance(rolls_payload, list) or len(rolls_payload) == 0:
        return JsonResponse({"success": False, "message": "'rolls' must be a non-empty list."}, status=400)

    # Prepare map: incoming by id
    try:
        roll_ids = [int(r['id']) for r in rolls_payload if isinstance(r, dict) and 'id' in r]
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "message": "Invalid roll id(s)."}, status=400)

    payload_by_id = {int(r['id']): r for r in rolls_payload if 'id' in r}

    # Fetch only rolls belonging to this receipt
    rolls_qs = Roll.objects.select_for_update().filter(id__in=roll_ids, material_receipt_id=receipt_id)

    updated = 0
    deleted = 0

    # Save or delete each roll per payload
    for roll in rolls_qs:
        incoming = payload_by_id.get(roll.id, {})
        if 'length_t' not in incoming:
            continue

        val = incoming['length_t']

        # Treat explicit 0 (numeric or "0"/"0.0") as delete
        if val is not None:
            try:
                dec_val = Decimal(str(val))
            except (InvalidOperation, ValueError):
                return JsonResponse({"success": False, "message": f"Invalid length_t for roll id {roll.id}."}, status=400)

            if dec_val == 0:
                # Delete the roll
                roll.delete()
                deleted += 1
                continue
            elif dec_val < 0:
                return JsonResponse({"success": False, "message": f"length_t must be >= 0 for roll id {roll.id}."}, status=400)
            else:
                roll.length_t = dec_val
                roll.save(update_fields=['length_t'])
                updated += 1
        else:
            # None or empty -> set to NULL (does not delete)
            roll.length_t = None
            roll.save(update_fields=['length_t'])
            updated += 1

    # Recalculate confirmed quantity across ALL remaining rolls for this receipt
    confirmed_qty = Roll.objects.filter(material_receipt_id=receipt_id).aggregate(
        total=Coalesce(Sum('length_t'), Decimal('0'))
    )['total']

    if confirmed_qty <= 0:
        return JsonResponse({"success": False, "message": "Confirmed quantity must be > 0."}, status=400)

    # Determine stock type = ROLLS (force rolls)
    stock_type = getattr(Stock, "ROLLS", None)
    if stock_type is None:
        return JsonResponse({"success": False, "message": "Unknown stock type mapping for rolls."}, status=500)

    # Ensure a warehouse
    warehouse = Warehouse.objects.filter(is_archived=False).first()
    if not warehouse:
        warehouse = Warehouse.objects.create(name="Default", is_archived=False)

    # Stock is for the ITEM behind the receipt
    item = receipt.item
    if item is None:
        return JsonResponse({"success": False, "message": "Receipt has no item."}, status=400)

    content_type = ContentType.objects.get_for_model(item)

    supplier = getattr(receipt, "supplier", None)
    client = getattr(receipt, "client", None)
    last_cost = receipt.cost

    # Create/update stock
    stock, created = Stock.objects.select_for_update().get_or_create(
        content_type=content_type,
        object_id=item.pk,
        warehouse=warehouse,
        type=stock_type,
        client=client,
        defaults={
            'quantity': confirmed_qty,
            'is_archived': False,
            'company': receipt.company,  # if CompanyAwareModel
            'last_supplied_date': timezone.now(),
            'last_cost': last_cost if last_cost is not None else Decimal('0'),
            'last_supplier': supplier,
        }
    )

    if not created:
        stock.quantity = (stock.quantity or Decimal('0')) + confirmed_qty
        stock.last_supplied_date = timezone.now()
        stock.last_supplier = supplier
        if last_cost is not None:
            stock.last_cost = last_cost
        stock.save(update_fields=[
            'quantity',
            'last_supplied_date',
            'last_supplier',
            'last_cost',
        ])

    # Stock movement IN
    StockMovement.objects.create(
        stock=stock,
        movement_type="IN",
        quantity=confirmed_qty,
        to_warehouse=warehouse,
        note=f"Поступление рулонов: {item}"
    )

    # Update receipt -> POSTED
    receipt.confirmed_qty = confirmed_qty
    receipt.status = getattr(MaterialReceipt, "POSTED", receipt.status)
    receipt.posted_at = timezone.now()
    receipt.save(update_fields=["confirmed_qty", "status", "posted_at"])

    return JsonResponse({
        "success": True,
        "updated_rolls": updated,
        "deleted_rolls": deleted,
        "confirmed_qty": str(confirmed_qty),
        "stock_id": stock.id,
        "posted": True
    })
