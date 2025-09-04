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
from django.views.decorators.http import require_POST, require_GET
from decimal import Decimal, InvalidOperation
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum, Prefetch
from django.core.exceptions import ObjectDoesNotExist

from ..utils import apply_client_scope
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
        qs = super().get_queryset().filter(is_archived=False).select_related("client")

        qs = apply_client_scope(qs, self.request)

        today = timezone.localdate()
        term_filter = self.request.GET.get("term", "upcoming").lower()

        if term_filter == "upcoming":
            qs = qs.filter(term__gte=today).order_by("term")
        elif term_filter == "passed":
            qs = qs.filter(term__lt=today).order_by("-term")
        else:
            qs = qs.filter(term__gte=today).order_by("term")

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

        return qs

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

        # Get all unique item IDs from the BOMs
        all_bom_items = BillOfMaterials.objects.filter(
            sizequantity__in=size_quantities
        ).values_list('item_id', flat=True).distinct()

        # Get total stock for all those items
        item_type = ContentType.objects.get_for_model(Item)
        stock_data = (
            Stock.objects
            .filter(
                content_type=item_type,
                object_id__in=all_bom_items,
                is_archived=False
            )
            .values('object_id')
            .annotate(total_qty=Sum('quantity'))
        )

        # item_id -> available stock quantity
        stock_lookup = {entry['object_id']: entry['total_qty'] or 0 for entry in stock_data}

        # Annotate each BOM with required, available, missing
        for sq in size_quantities:
            for bom in sq.bill_of_materials.all():
                produced = sq.quantity or 0
                required_qty = bom.quantity * produced
                available_qty = stock_lookup.get(bom.item_id, 0)
                missing_qty = max(required_qty - available_qty, 0)

                bom.required_qty = required_qty
                bom.available_qty = available_qty
                bom.missing_qty = missing_qty

        context['size_quantities'] = size_quantities
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
    success_url = reverse_lazy("stock_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context
    
    def form_valid(self, form):
        color     = form.cleaned_data["color"]
        fabric    = form.cleaned_data["fabric"]
        supplier  = form.cleaned_data["supplier"]
        client    = form.cleaned_data["client"]
        width     = form.cleaned_data["width"]
        quantity  = form.cleaned_data["quantity"]
        price     = form.cleaned_data["price"]

        weights_raw = self.request.POST.getlist("weight")
        lengths_raw = self.request.POST.getlist("length")

        parse = lambda v: (Decimal(v) if v.strip() else None)
        weights = [parse(w) for w in weights_raw]
        lengths = [parse(l) for l in lengths_raw]

        company   = get_current_company()
        warehouse = Warehouse.objects.filter(is_archived=False).first()

        # 1. RollBatch
        batch, _ = Item.objects.get_or_create(
            color=color, fabric=fabric, supplier=supplier,
            client=client, width=width, company=company,
            defaults={
                "name": f"{color.name} {fabric.name} {width}м для {client.name} от {supplier.name}",
            }
        )

        # 2. bulk-create rolls
        start_idx = Roll.objects.filter(
            color=color,
            fabric=fabric,
            supplier=supplier,
            client=client
        ).count()
        new_rolls = []
        metres_in = Decimal("0")

        for i in range(quantity):
            length_val = lengths[i] if i < len(lengths) else None
            weight_val = weights[i] if i < len(weights) else None
            new_rolls.append(
                Roll(
                    roll_batch=batch,
                    color=color, fabric=fabric,
                    supplier=supplier, client=client,
                    width=width,
                    name=start_idx + i + 1,
                    length_t=length_val,
                    weight=weight_val,
                    company=company,
                )
            )
            if length_val:
                metres_in += length_val

        Roll.objects.bulk_create(new_rolls)
        if price is not None:
            CostRecord.objects.create(
                company=company,
                content_type=ContentType.objects.get_for_model(Item),
                object_id=batch.id,
                cost=price
            )
        # 4. Stock row per SKU (RollBatch)
        ct = ContentType.objects.get_for_model(Item)
        stock, _ = Stock.objects.get_or_create(
            content_type=ct, object_id=batch.id,
            type=Stock.ROLLS,
            warehouse=warehouse, company=company,
            defaults={"quantity": Decimal("0")},
        )
        if metres_in:
            updates = {
                "quantity": F("quantity") + metres_in,
                "last_supplied_date": timezone.now(),
            }
            if price is not None:
                updates["last_cost"] = price

            Stock.objects.filter(pk=stock.pk).update(**updates)

            StockMovement.objects.create(
                stock=stock, movement_type="IN",
                quantity=metres_in,
                from_warehouse=None, to_warehouse=warehouse,
                note="Прием рулонов",
            )

        self.object = new_rolls[0] if new_rolls else None
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
        context['fabrics'] = Fabrics.objects.filter(is_archived=False)
        context['clients'] = Client.objects.filter(is_archived=False)
        context['warehouses'] = Warehouse.objects.filter(is_archived=False)

        for stock in context['stocks']:
            if stock.type == Stock.ROLLS:
                stock.unit_display = 'м'
            elif stock.type == Stock.FINSHED_GOODS:
                stock.unit_display = 'шт'
            else:
                stock.unit_display = getattr(stock.content_object, 'unit', '')

            if stock.type == Stock.ROLLS:
                stock.category_display = "Рулон"
            elif stock.type == Stock.FINSHED_GOODS:
                stock.category_display = "Готовая продукция"
            else:
                stock.category_display = getattr(stock.content_object, 'category', 'Сырье')

        return context
    
    
# ---------- Helpers ----------
def _get_client_scope(request):
    """
    Reads the client scope you set via the sidebar form.
    Expected values you post: 'all', 'shared', or a client_id (as str/int).
    """
    val = request.session.get('current_client_id', 'all')
    # normalize:
    if val in ('all', 'shared'):
        return val
    try:
        return int(val)
    except (TypeError, ValueError):
        return 'all'

def _filter_by_client(qs, client_scope):
    """
    Filters the Stock queryset by client.
    Because Stock.content_object is heterogeneous (GFK), we keep a compact
    Python-side filter that mirrors your current logic—but scoped and fast.
    """
    if client_scope == 'all':
        return qs
    filtered_ids = []

    for stock in qs:
        content = stock.content_object
        # Direct .client
        if client_scope == 'shared':
            # unassigned / shared (no client on item)
            if hasattr(content, 'client') and getattr(content, 'client_id', None) is None:
                filtered_ids.append(stock.id)
            elif isinstance(content, SizeQuantity):
                # "shared" for FG if orders have no client?
                # If your domain defines shared FG differently, adjust here.
                has_any_client = False
                for order in content.orders.select_related('client_order__client'):
                    if getattr(order.client_order, 'client_id', None) is not None:
                        has_any_client = True
                        break
                if not has_any_client:
                    filtered_ids.append(stock.id)
            elif hasattr(content, 'order'):
                # If there is an order but no client on client_order, consider it shared
                client_id = getattr(getattr(content.order, 'client_order', None), 'client_id', None)
                if client_id is None:
                    filtered_ids.append(stock.id)

        elif isinstance(client_scope, int):
            # specific client id
            if hasattr(content, 'client') and getattr(content, 'client_id', None) == client_scope:
                filtered_ids.append(stock.id)
            elif isinstance(content, SizeQuantity):
                orders = content.orders.select_related('client_order__client')
                if any(o.client_order.client_id == client_scope for o in orders):
                    filtered_ids.append(stock.id)
            elif hasattr(content, 'order'):
                co = getattr(content.order, 'client_order', None)
                if getattr(co, 'client_id', None) == client_scope:
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
        assert self.STOCK_TYPE in (Stock.RAW_MATERIALS, Stock.FINSHED_GOODS, Stock.ROLLS)
        qs = Stock.objects.filter(is_archived=False, type=self.STOCK_TYPE)

        # Scope by client (from sidebar session)
        client_scope = _get_client_scope(self.request)
        qs = _filter_by_client(qs, client_scope)

        # Stable ordering
        return qs.order_by('id')

    def get_template_names(self):
        return [self.TEMPLATE_NAME]

    def _compute_labels(self, stock):
        # Unit label
        if stock.type == Stock.ROLLS:
            stock.unit_display = 'м'
        elif stock.type == Stock.FINSHED_GOODS:
            stock.unit_display = 'шт'
        else:
            stock.unit_display = getattr(stock.content_object, 'unit', '')

        # Category label
        if stock.type == Stock.ROLLS:
            stock.category_display = "Рулон"
        elif stock.type == Stock.FINSHED_GOODS:
            stock.category_display = "Готовая продукция"
        else:
            stock.category_display = getattr(stock.content_object, 'category', 'Сырье')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Sidebar + selects
        ctx['sidebar_type'] = 'keeper'
        ctx['clients'] = Client.objects.filter(is_archived=False)
        ctx['suppliers'] = Supplier.objects.filter(is_archived=False)
        ctx['categories'] = Category.objects.filter(is_archived=False)
        ctx['colors'] = Color.objects.filter(is_archived=False)
        ctx['fabrics'] = Fabrics.objects.filter(is_archived=False)
        ctx['warehouses'] = Warehouse.objects.filter(is_archived=False)

        # Current scope (for template logic if needed)
        client_scope = _get_client_scope(self.request)
        ctx['selected_client_scope'] = client_scope  # 'all' | 'shared' | int

        # Add computed labels
        for s in ctx['stocks']:
            self._compute_labels(s)

        return ctx


# ---------- 3 focused pages ----------

class FabricsStockListView(BaseKeeperStockList):
    """
    Materials → Fabrics (Rolls)
    """
    STOCK_TYPE = Stock.ROLLS        # usually 2
    TEMPLATE_NAME = 'keeper/stocks/fabrics_list.html'


class RawMaterialsStockListView(BaseKeeperStockList):
    """
    Materials → Accessories / Other Raw Materials
    """
    STOCK_TYPE = Stock.RAW_MATERIALS          # usually 0
    TEMPLATE_NAME = 'keeper/stocks/raw_materials_list.html'


class FinishedGoodsStockListView(BaseKeeperStockList):
    """
    Finished Goods (SizeQuantity-based)
    """
    STOCK_TYPE = Stock.FINSHED_GOODS  # usually 1
    TEMPLATE_NAME = 'keeper/stocks/finished_goods_list.html'

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
            "supplier_id": item.supplier_id,
            "client_id": item.client_id,
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
    item.supplier = get_fk(Supplier, "supplier_id")
    item.client   = get_fk(Client, "client_id")

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
        item.fabric = get_fk(Fabrics, "fabric_id")
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
            'suppliers': Supplier.objects.filter(is_archived=False),
            'clients': Client.objects.filter(is_archived=False),
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
        price_str = request.POST.get(f'row-{row}_price')

        if item_id and qty_str:
            price = None
            if price_str:
                try:
                    price = Decimal(price_str)
                except (InvalidOperation, TypeError):
                    price = None
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
                    stock.last_supplied_date = timezone.now()
                    if price is not None:
                        stock.last_cost = price
                    stock.save()
                else:
                    stock = Stock.objects.create(
                        content_type=ct,
                        object_id=item.id,
                        type=Stock.RAW_MATERIALS,
                        quantity=qty,
                        warehouse=warehouse,
                        is_archived=False,
                        company=company,
                        last_supplied_date=timezone.now(),
                        last_cost=price if price is not None else None,
                    )

                # Log the movement of exactly the added quantity
                StockMovement.objects.create(
                    stock=stock,
                    movement_type='IN',
                    quantity=qty,
                    from_warehouse=None,
                    to_warehouse=warehouse,
                    note='Прием сырья',
                )
                if price is not None:
                    CostRecord.objects.create(
                        company=company,
                        content_type=ct,
                        object_id=item.id,
                        cost=price,
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
            type=Stock.FINSHED_GOODS,
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

@method_decorator([login_required, keeper_required], name='dispatch')
class StockMovementListView(ListView):
    model = StockMovement
    template_name = 'keeper/stocks/stock_movement.html'
    context_object_name = 'movements'
    paginate_by = 20

    def get_queryset(self):
        return (
            StockMovement.objects
            .select_related('stock__content_type', 'from_warehouse', 'to_warehouse')
            .order_by('-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context
    
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
            type=Stock.FINSHED_GOODS,
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
            .select_related('size_quantity__model', 'size_quantity__color', 'size_quantity__fabrics')
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
                type=Stock.FINSHED_GOODS,
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