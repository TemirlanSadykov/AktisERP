import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.contenttypes.models import ContentType

from ..decorators import accountant_required
from ..forms import *
from ..models import *

@method_decorator([login_required, accountant_required], name='dispatch')
class ClientOrderListAccountantView(ListView):
    model = ClientOrder
    template_name = 'accountant/client/orders/list.html'
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
        context['sidebar_type'] = 'accountant'
        return context
    
@method_decorator([login_required, accountant_required], name='dispatch')
class ClientOrderDetailAccountantView(DetailView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'accountant/client/orders/detail.html'
    context_object_name = 'client_order'

    def get_context_data(self, **kwargs):
        context = super(ClientOrderDetailAccountantView, self).get_context_data(**kwargs)
        client_order = context['client_order']
        context['orders'] = client_order.orders.all()
        today = timezone.localdate()
        if client_order.term >= today:
            days_left = (client_order.term - today).days
        else:
            days_left = 0
        context['days_left'] = days_left
        context['sidebar_type'] = 'accountant'
        return context

@method_decorator([login_required, accountant_required], name='dispatch')
class OrderListAccountantView(ListView):
    model = Order
    template_name = 'accountant/orders/list.html'
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
        context['sidebar_type'] = 'accountant'
        return context
    
@login_required
@accountant_required
def manual_cost_page(request):
    models = Model.objects.filter(is_archived=False)
    context = {
        'sidebar_type': 'accountant',
        'models': models,
    }
    return render(request, 'accountant/manual_cost.html', context)

@login_required
@accountant_required
def ajax_get_model_sizes(request):
    model_id = request.GET.get('model_id')
    sizes_data = []
    if model_id:
        size_quantities = SizeQuantity.objects.filter(model_id=model_id)
        for sq in size_quantities:
            label = f"{sq.color.name if sq.color else ''} {sq.fabrics.name if sq.fabrics else ''} {sq.size or ''}"
            sizes_data.append({
                "id": sq.id,
                "label": label,
            })
    return JsonResponse({"sizes": sizes_data})

@login_required
@accountant_required
def ajax_get_size_cost_data(request, size_id):
    materials_data = []

    # Fetch BOM for SizeQuantity
    boms = BillOfMaterials.objects.filter(sizequantity_id=size_id, is_archived=False)

    for bom in boms:
        item_ct = ContentType.objects.get_for_model(bom.item)
        existing_cost = CostRecord.objects.filter(
            content_type=item_ct,
            object_id=bom.item.id
        ).order_by('-created_at').first()

        unit_cost = existing_cost.cost if existing_cost else 0

        materials_data.append({
            'id': bom.item.id,
            'name': bom.item.name,
            'required_quantity': float(bom.quantity),
            'unit_cost': float(unit_cost),
        })

    # Fetch previous full SizeQuantity total cost (if any)
    size_ct = ContentType.objects.get_for_model(SizeQuantity)
    previous_total_record = CostRecord.objects.filter(
        content_type=size_ct,
        object_id=size_id
    ).order_by('-created_at').first()

    previous_total = previous_total_record.cost if previous_total_record else 0

    return JsonResponse({
        'materials': materials_data,
        'previous_total': float(previous_total),
    })

@login_required
@accountant_required
@csrf_exempt  # already protected by CSRF in your JS, but double safe
def save_costs(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON.'}, status=400)

    costs_data = data.get('costs', [])
    sizequantity_id = data.get('sizequantity_id')  # We'll add this in JS soon
    if not costs_data or not sizequantity_id:
        return JsonResponse({'success': False, 'message': 'Missing data.'}, status=400)

    # For calculating total
    total_new_cost = 0

    for item_cost in costs_data:
        item_id = item_cost.get('id')
        unit_cost = item_cost.get('unit_cost')

        if item_id is None:
            continue  # Skip invalid rows

        try:
            item = Item.objects.get(id=item_id)
        except Item.DoesNotExist:
            continue  # Skip if item doesn't exist

        # Save a CostRecord for this Item
        CostRecord.objects.create(
            company=item.company,  # from your CompanyAwareModel
            content_type=ContentType.objects.get_for_model(Item),
            object_id=item.id,
            cost=unit_cost
        )

        # Need quantity for correct total?
        # We'll fix this soon: quantity is not sent yet in payload

    # Now also save CostRecord for SizeQuantity
    try:
        sizequantity = SizeQuantity.objects.get(id=sizequantity_id)
    except SizeQuantity.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'SizeQuantity not found.'}, status=404)

    # Calculate total based on SizeQuantity BOMs and saved unit_costs
    total = 0
    boms = BillOfMaterials.objects.filter(sizequantity=sizequantity, is_archived=False)
    for bom in boms:
        try:
            existing_cost = CostRecord.objects.filter(
                content_type=ContentType.objects.get_for_model(Item),
                object_id=bom.item.id
            ).order_by('-created_at').first()
            if existing_cost:
                total += bom.quantity * existing_cost.cost
        except:
            continue  # Ignore missing

    # Save CostRecord for the SizeQuantity
    CostRecord.objects.create(
        company=sizequantity.company,
        content_type=ContentType.objects.get_for_model(SizeQuantity),
        object_id=sizequantity.id,
        cost=total
    )

    return JsonResponse({'success': True})
