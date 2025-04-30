from collections import defaultdict
import json
import openpyxl # type: ignore

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.db import transaction
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView 
from django.views import View
from django.db.models import Q
from django.db.models import IntegerField
from decimal import Decimal
from django.db.models.functions import Cast
from django.db.models import Prefetch
from django.db.models import Prefetch, Sum, Value, DecimalField
from django.db.models.functions import Coalesce, Cast

from ..decorators import sub_tech_required
from ..forms import *
from ..models import *


CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@sub_tech_required
def sub_tech_page(request):
    context = {
               'sidebar_type': 'sub_tech'
               }
    return render(request, 'sub_tech_page.html', context)

@method_decorator([login_required, sub_tech_required], name='dispatch')
class ClientOrderListSubView(ListView):
    model = ClientOrder
    template_name = 'sub_tech/client/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 10
    form_class = DateRangeForm 

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_archived=False)
        today = timezone.localdate()

        # Read the term filter from GET. Defaults to 'upcoming' if not provided.
        term_filter = self.request.GET.get('term', 'upcoming').lower()

        if term_filter == 'upcoming':
            # Upcoming orders: term is today or later; sort ascending (soonest first)
            queryset = queryset.filter(term__gte=today).order_by('term')
        elif term_filter == 'passed':
            # Passed orders: term is before today; sort descending (most recent first)
            queryset = queryset.filter(term__lt=today).order_by('-term')
        else:
            # Default to upcoming if unknown value is provided
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
        orders_with_days_left = []

        # Calculate days_left for display. (Negative values for passed orders.)
        for order in context['orders']:
            days_left = (order.term - today).days
            orders_with_days_left.append({'order': order, 'days_left': days_left})
        context['orders_with_days_left'] = orders_with_days_left

        # Pass the current term filter for use in the template
        context['term_filter'] = self.request.GET.get('term', 'upcoming').lower()
        context['ClientOrder'] = ClientOrder
        context['sidebar_type'] = 'sub_tech'
        return context
    
    
@method_decorator([login_required, sub_tech_required], name='dispatch')
class ClientOrderDetailSubView(DetailView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'sub_tech/client/orders/detail.html'
    context_object_name = 'client_order'

    def get_context_data(self, **kwargs):
        context = super(ClientOrderDetailSubView, self).get_context_data(**kwargs)
        client_order = context['client_order']
        context['orders'] = client_order.orders.all()
        today = timezone.localdate()
        if client_order.term >= today:
            days_left = (client_order.term - today).days
        else:
            days_left = 0
        context['days_left'] = days_left
        context['sidebar_type'] = 'sub_tech'
        return context
    
@method_decorator([login_required, sub_tech_required], name='dispatch')
class OrderDetailSubView(DetailView):
    model = Order
    template_name = 'sub_tech/orders/detail.html'
    context_object_name = 'order'

    def get_queryset(self):
        return Order.objects.prefetch_related(
            # Prefetch order's size quantities with related color/fabrics.
            Prefetch(
                'size_quantities',
                queryset=SizeQuantity.objects.select_related('color', 'fabrics').order_by('size')
            ),
            # Prefetch cuts, annotate total_layers from passports, and prefetch their related objects.
            Prefetch(
                'cuts',
                queryset=Cut.objects.order_by('number')
                .annotate(total_layers=Coalesce(Sum('passports__layers'), Value(0), output_field=IntegerField()))
                .prefetch_related(
                    'size_quantities',
                    Prefetch(
                        'passports',
                        queryset=Passport.objects.prefetch_related(
                            Prefetch(
                                'size_quantities',
                                queryset=SizeQuantity.objects.select_related('color', 'fabrics')
                            )
                        )
                    )
                )
            ),
            'client_order'  # For days_left calculation.
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']

        # Build pivot data for "Required Quantities" table.
        pivot_data = {}
        all_sizes_set = set()
        for sq in order.size_quantities.all():
            all_sizes_set.add(sq.size)
            key = (sq.color, sq.fabrics)  # relies on __str__ of these models.
            pivot_data.setdefault(key, {})[sq.size] = sq.quantity

        try:
            all_sizes = sorted(all_sizes_set, key=lambda s: int(s))
        except (ValueError, TypeError):
            all_sizes = sorted(all_sizes_set)

        # Associated cuts are already prefetched.
        associated_cuts = order.cuts.all()

        # Calculate days left until the term.
        today = timezone.now().date()
        days_left = (order.client_order.term - today).days if order.client_order.term >= today else 0

        # --- Build detailed cut data ---
        cut_details = []
        for cut in associated_cuts:
            # Get unique sizes used in this cut.
            cut_sizes = list(cut.size_quantities.values_list('size', flat=True).distinct())
            try:
                cut_sizes_sorted = sorted(cut_sizes, key=lambda s: int(s))
            except (ValueError, TypeError):
                cut_sizes_sorted = sorted(cut_sizes)
            
            # Build passport data and aggregate colors from all passports.
            passport_list = []
            aggregated_colors = set()
            for passport in cut.passports.all():
                colors = {psq.color.name for psq in passport.size_quantities.all() if psq.color}
                fabrics = {psq.fabrics.name for psq in passport.size_quantities.all() if psq.fabrics}
                aggregated_colors.update(colors)
                passport_list.append({
                    'passport_id': passport.id,
                    'passport_number': passport.number,
                    'colors': ", ".join(sorted(colors)),
                    'fabrics': ", ".join(sorted(fabrics)),
                })
            aggregated_colors_str = ", ".join(sorted(aggregated_colors))
            
            # Use the annotated total_layers.
            total_layers = cut.total_layers

            cut_details.append({
                'cut_id': cut.id,
                'cut_number': cut.number,
                'cut_date': cut.date,
                'cut_sizes': cut_sizes_sorted,
                'aggregated_colors': aggregated_colors_str,
                'total_layers': total_layers,
                'passports': passport_list,
            })

        context.update({
            'pivot_data': pivot_data,   # Pivoted required quantities.
            'all_sizes': all_sizes,     # Sorted list of sizes for header.
            'days_left': days_left,
            'associated_cuts': associated_cuts,
            'cut_details': cut_details, # Detailed cut info including aggregated colors, sizes, and total layers.
            'sidebar_type': 'sub_tech'
        })
        return context

@login_required
@sub_tech_required
def assign_operations_by_cut_sub(request, cut_id):
    cut = get_object_or_404(Cut, pk=cut_id)
    model_operations = ModelOperation.objects.filter(
        model=cut.order.model
    ).select_related('operation').order_by('order')
    operations = [model_op.operation for model_op in model_operations]

    # Get all passports for this cut, ordered by number (or creation order)
    passports = cut.passports.all().order_by('number')
    
    # For each passport, get its passport sizes ordered by size.
    passport_sizes_by_passport = {}
    for passport in passports:
        sizes = passport.passport_sizes.all().order_by('size_quantity__size')
        passport_sizes_by_passport[passport.id] = sizes

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        import json
        from django.db import transaction
        data = json.loads(request.body)
        operation_id = data.get('operation_id')
        passport_size_id = data.get('passport_size_id')
        value = data.get('value')

        try:
            with transaction.atomic():
                passport_size = PassportSize.objects.get(id=passport_size_id)
                total_quantity = passport_size.quantity

                entries = value.split(',')
                for entry in entries:
                    if '(' in entry and ')' in entry:
                        employee_id_input, quantity = entry.split('(')
                        employee_id_input = employee_id_input.strip()
                        quantity = int(quantity.strip(' )'))
                    else:
                        employee_id_input = entry.strip()
                        quantity = total_quantity

                    employee_profile = UserProfile.objects.filter(
                        employee_id=employee_id_input,
                        type=UserProfile.EMPLOYEE,
                        
                    ).first()
                    if not employee_profile:
                        raise Exception(f"Employee not found.")

                    work, created = Work.objects.get_or_create(
                        operation_id=operation_id,
                        passport_size=passport_size,
                    )
                    AssignedWork.objects.create(
                        work=work,
                        employee=employee_profile,
                        quantity=quantity
                    )
                return JsonResponse({'status': 'success'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    # Build a dictionary of already assigned works, keyed by (operation_id, passport_size_id)
    work_by_op_and_size = {}
    for aw in AssignedWork.objects.filter(work__passport_size__passport__in=passports).select_related('employee', 'work__operation', 'work__passport_size'):
        key = (aw.work.operation_id, aw.work.passport_size_id)
        work_by_op_and_size.setdefault(key, []).append(aw)

    return render(request, 'sub_tech/passports/assign_operations_by_cut.html', {
        'cut': cut,
        'operations': operations,
        'passports': passports,
        'passport_sizes_by_passport': passport_sizes_by_passport,
        'work_by_op_and_size': work_by_op_and_size,
        'sidebar_type': 'sub_tech'
    })