from datetime import timedelta, datetime
from decimal import Decimal
import json
from urllib.parse import urlencode
from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.db import transaction
from django.db.models import F, Window, Sum, Count, Q
from django.db.models import ExpressionWrapper, DecimalField
from django.db.models.functions import Lead
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView, DeleteView, UpdateView
from django.views.generic.edit import CreateView
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models.functions import Cast
from django.db.models import IntegerField
from datetime import timedelta
from django.db.models import F, Sum, ExpressionWrapper, DurationField, Value
from django.db.models.functions import Coalesce, TruncDate
from django.db.models import Prefetch
from django.db.models import Sum, IntegerField, Case, When

from django.db.models.functions import TruncMonth

from ..decorators import admin_required
from ..forms import *
from ..models import *
from datetime import datetime, timedelta
from django.utils import timezone

@login_required
@admin_required
def admin_page(request):
    # Retrieve start and end dates from GET parameters.
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # If dates are provided, try to parse them; otherwise default to one month ago until today.
    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            # Fallback to default if parsing fails.
            today = date.today()
            start_dt = today - timedelta(days=30)
            end_dt = today
            start_date = start_dt.strftime("%Y-%m-%d")
            end_date = end_dt.strftime("%Y-%m-%d")
    else:
        today = date.today()
        start_dt = today - timedelta(days=30)
        end_dt = today
        start_date = start_dt.strftime("%Y-%m-%d")
        end_date = end_dt.strftime("%Y-%m-%d")

    # Default summary data in case there is no data.
    summary_data = {
        'total_production': 0,
        'orders_count': 0,
        'cuts_count': 0,
        'total_payment': 0,
    }

    # Query and aggregate data for the provided (or default) date range.
    orders_in_range = Order.objects.filter(created_at__date__range=[start_dt, end_dt])
    order_stats = orders_in_range.aggregate(
        total_production=Coalesce(Sum('quantity'), Value(0)),
        orders_count=Coalesce(Count('id'), Value(0))
    )
    total_production = order_stats['total_production']
    orders_count = order_stats['orders_count']

    # Count cuts in the given date range.
    cuts_count = Cut.objects.filter(date__range=[start_dt, end_dt]).count()

    # Compute total payment from AssignedWork using a database expression.
    # Cast quantity to Decimal to avoid mixing types.
    payment_expr = ExpressionWrapper(
        Cast(F('quantity'), output_field=DecimalField(max_digits=10, decimal_places=2)) *
        Cast(F('work__operation__payment'), output_field=DecimalField(max_digits=10, decimal_places=2)),
        output_field=DecimalField(max_digits=10, decimal_places=2)
    )
    total_payment = AssignedWork.objects.filter(created_at__date__range=[start_dt, end_dt]) \
        .annotate(work_payment=payment_expr) \
        .aggregate(total_payment=Coalesce(Sum('work_payment'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)))['total_payment']

    summary_data = {
        'total_production': total_production,
        'orders_count': orders_count,
        'cuts_count': cuts_count,
        'total_payment': total_payment,
    }

    context = {
        'start_date': start_date,
        'end_date': end_date,
        'summary_data': summary_data,
    }
    return render(request, 'admin_page.html', context)

@login_required
@admin_required
def production_details_view(request):
    """
    Returns an HTML snippet (table) with client order details and their associated orders.
    """
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        client_orders_qs = ClientOrder.objects.filter(is_archived=False)
    else:
        client_orders_qs = ClientOrder.objects.filter(
            is_archived=False,
            launch__range=[start_dt, end_dt]
        )
    
    # Optimize the queryset: prefetch related orders and their many-to-many/foreign key relations.
    client_orders_qs = client_orders_qs.select_related('client').prefetch_related(
        Prefetch(
            'orders',
            queryset=Order.objects.all()
                .select_related('model')
                .prefetch_related('colors', 'fabrics', 'size_quantities')
        )
    )
    
    client_orders_data = []
    for co in client_orders_qs:
        orders_data = []
        for order in co.orders.all():
            # Join names for many-to-many fields; convert sizes to string if needed.
            color_names = ", ".join(color.name for color in order.colors.all())
            fabric_names = ", ".join(fabric.name for fabric in order.fabrics.all())
            unique_sizes = sorted({str(sq.size) for sq in order.size_quantities.all() if sq.size})
            sizes = ", ".join(unique_sizes)
            orders_data.append({
                'id': order.id,
                'model_name': order.model.name,
                'colors': color_names,
                'fabrics': fabric_names,
                'quantity': order.quantity,
                'sizes': sizes,
            })
        client_orders_data.append({
            'id': co.id,
            'client_name': co.client.name,
            'launch': co.launch,
            'term': co.term,
            'orders': orders_data,
        })
    
    context = {'client_orders': client_orders_data}
    return render(request, 'admin/partial_client_orders.html', context)

@login_required
@admin_required
def order_details_api(request, order_id):
    """
    API endpoint to return aggregated order details grouped by unique (color, fabric)
    pairs and then by size for a given order, with optional date filtering.

    For each unique (color, fabric) pair from the order's SizeQuantity records, we assume
    there is only one record per size. For each such record, we return:
      - total ordered (from SizeQuantity.quantity)
      - cut (aggregated from Passport.layers for passports linked to that SizeQuantity)
      - sew (aggregated from Passport.layers for passports that have any AssignedWork)
      - check (from SizeQuantity.checked)
      - packed (from SizeQuantity.packed)
    """

    order = get_object_or_404(Order, pk=order_id)

    # Get all SizeQuantity objects for the order (with related color and fabrics)
    size_quantities = order.size_quantities.select_related('color', 'fabrics').all()

    # Group SizeQuantity objects by unique (color, fabric) pair, and then by size.
    groups = {}  # key: (color, fabric)
    for sq in size_quantities:
        color_name = sq.color.name if sq.color else ""
        fabric_name = sq.fabrics.name if sq.fabrics else ""
        key = (color_name, fabric_name)
        if key not in groups:
            groups[key] = {}
        if sq.size:
            # Only keep the first record for each size.
            if sq.size not in groups[key]:
                groups[key][sq.size] = {
                    "id": sq.id,
                    "total": sq.quantity or 0,
                    "checked": sq.checked or 0,
                    "packed": sq.packed or 0,
                }

    group_list = []
    for (color_name, fabric_name), sizes_dict in groups.items():
        sizes_data = []
        for size_value, data_dict in sizes_dict.items():
            size_id = data_dict["id"]
            total_ordered = data_dict["total"]
            checked_total = data_dict["checked"]
            packed_total = data_dict["packed"]

            # Fetch passports associated with the given SizeQuantity record.
            passport_qs = Passport.objects.filter(
                cut__order=order,
                size_quantities__id=size_id
            ).distinct()

            # Aggregate cut_total: sum of layers for all these passports.
            passport_agg = passport_qs.aggregate(
                cut_total=Coalesce(Sum('layers'), 0, output_field=IntegerField())
            )
            cut_total = passport_agg['cut_total']

            # For sew_total, get passport IDs that have any assigned work.
            assigned_passport_ids = AssignedWork.objects.filter(
                work__passport_size__passport__in=passport_qs
            ).values_list('work__passport_size__passport_id', flat=True).distinct()
            sew_agg = passport_qs.filter(id__in=assigned_passport_ids).aggregate(
                sew_total=Coalesce(Sum('layers'), 0, output_field=IntegerField())
            )
            sew_total = sew_agg['sew_total']

            sizes_data.append({
                "size": size_value,
                "total": total_ordered,
                "cut": cut_total,
                "sew": sew_total,
                "check": checked_total,
                "packed": packed_total,
            })
        group_list.append({
            "color": color_name,
            "fabric": fabric_name,
            "sizes": sizes_data,
        })

    response_data = {
        "groups": group_list,
        "model_name": order.model.name,
    }
    return JsonResponse(response_data)

@login_required
@admin_required
def order_filter_view(request):
    """
    Returns an HTML snippet (a list with checkboxes) of orders that are associated with
    AssignedWork records within the specified date range.
    """
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return render(request, 'admin/partial_order_filter.html', {'orders': []})

    assigned_works = AssignedWork.objects.filter(
        created_at__date__range=[start_dt, end_dt]
    ).select_related('work__passport_size__passport__cut__order')

    # Extract unique order IDs from the assigned works
    order_ids = assigned_works.values_list('work__passport_size__passport__cut__order__id', flat=True).distinct()
    orders = Order.objects.filter(id__in=order_ids)

    return render(request, 'admin/partial_order_filter.html', {'orders': orders})

@login_required
@admin_required
def payment_details_view(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        # If dates are missing or invalid, return an empty table.
        return render(request, 'admin/partial_payment_details.html', {'employee_data': []})

    # Filter AssignedWork records within the date range, prefetch related objects.
    assigned_works = AssignedWork.objects.filter(
        created_at__date__range=[start_dt, end_dt]
    ).select_related('employee', 'work__operation', 'work__passport_size__passport__cut__order')

    # Optionally filter by order_ids if provided.
    order_ids = request.GET.getlist('order_ids')
    if order_ids:
        assigned_works = assigned_works.filter(
            work__passport_size__passport__cut__order__id__in=order_ids
        )

    # Aggregate data grouped by employee using the ORM.
    aggregates = assigned_works.values('employee').annotate(
        total_units=Coalesce(Sum('quantity'), Value(0), output_field=IntegerField()),
        total_seconds=Coalesce(
            Sum(ExpressionWrapper(
                F('quantity') * F('work__operation__preferred_completion_time'),
                output_field=IntegerField()
            )),
            Value(0), output_field=IntegerField()
        ),
        total_payment=Coalesce(
            Sum(ExpressionWrapper(
                Cast(F('quantity'), output_field=DecimalField(max_digits=10, decimal_places=2)) *
                F('work__operation__payment'),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )),
            Value(0), output_field=DecimalField()
        )
    )
    # Build a dictionary mapping employee ID to their aggregated values.
    employee_aggregates = {item['employee']: item for item in aggregates}

    # Retrieve all employees (even those with no work) ordered by their employee_id cast as an integer.
    all_employees = UserProfile.objects.exclude(type__in=[0, 1]).order_by(Cast('employee_id', IntegerField()))

    employee_data_list = []
    for emp in all_employees:
        agg = employee_aggregates.get(emp.id, {})
        employee_data_list.append({
            'id': emp.id,
            'employee_id': emp.employee_id,
            'full_name': f"{emp.user.first_name} {emp.user.last_name}",
            'units_produced': agg.get('total_units', 0),
            'seconds_worked': int(agg.get('total_seconds', 0)),
            'payment': int(agg.get('total_payment', 0)),
        })

    context = {'employee_data': employee_data_list}
    return render(request, 'admin/partial_payment_details.html', context)

@login_required
@admin_required
def employees_payment_details(request, employee_id):
    # 1) Get the employee
    employee = get_object_or_404(UserProfile, pk=employee_id)

    # 2) Parse the date range from query parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            start_dt = None
            end_dt = None
    else:
        start_dt = end_dt = None

    # 3) Fetch AssignedWork for the employee in that date range
    if start_dt and end_dt:
        assigned_works = AssignedWork.objects.filter(
            employee=employee,
            created_at__date__range=[start_dt, end_dt]
        )
    else:
        assigned_works = AssignedWork.objects.filter(employee=employee)

    # 4) Extract unique orders from the assigned works
    orders = assigned_works.values_list(
        "work__passport_size__passport__cut__order__id",
        "work__passport_size__passport__cut__order__model__name"
    ).distinct()
    orders_dict = {order_id: model_name for order_id, model_name in orders}

    # Use select_related to optimize subsequent accesses
    assigned_works = assigned_works.select_related(
        'work',
        'work__operation',
        'work__passport_size__passport__cut__order'
    )

    # 5) Group operations and calculate summary details using DB aggregation
    # Annotate actual_time as a duration (handling nulls)
    assigned_works = assigned_works.annotate(
        actual_time=Coalesce(
            ExpressionWrapper(F('end_time') - F('start_time'), output_field=DurationField()),
            Value(timedelta(seconds=0))
        )
    )
    # Group by operation fields and sum quantities and actual_time
    ops_summary = assigned_works.values(
        'work__operation__name',
        'work__operation__preferred_completion_time',
        'work__operation__payment'
    ).annotate(
        quantity=Sum('quantity'),
        total_time=Sum('actual_time')
    )

    # Build operation summary from aggregated data
    operation_summary = {}
    total_units = 0
    total_weighted_efficiency = 0
    for op in ops_summary:
        op_name = op['work__operation__name']
        preferred_completion_time = op['work__operation__preferred_completion_time']
        payment = op['work__operation__payment']
        quantity = op['quantity']
        # total_time is a timedelta; convert it to seconds
        total_time_seconds = op['total_time'].total_seconds() if op['total_time'] else 0
        avg_time_per_unit = total_time_seconds / quantity if quantity else 0
        # Calculate efficiency; if avg_time_per_unit is 0, assume perfect efficiency (100%)
        efficiency = (preferred_completion_time / avg_time_per_unit) * 100 if avg_time_per_unit else 100

        operation_summary[op_name] = {
            'operation': op_name,
            'quantity': quantity,
            'total_time': total_time_seconds,
            'preferred_completion_time': preferred_completion_time,
            'payment': payment,
            'efficiency': efficiency,
        }
        total_units += quantity
        total_weighted_efficiency += (efficiency * quantity)

    # Calculate operation distribution across orders (this part remains in Python)
    operation_distribution = {}
    for work in assigned_works:
        op_name = work.work.operation.name
        order_id = work.work.passport_size.passport.cut.order.id
        key = (op_name, order_id)
        operation_distribution[key] = operation_distribution.get(key, 0) + work.quantity

    # 6) Build the list of operation details based on the summary
    operations_details = []
    total_time = 0
    total_payment = 0
    for op_data in operation_summary.values():
        total_time_spent = op_data['preferred_completion_time'] * op_data['quantity']
        total_payment_spent = op_data['payment'] * op_data['quantity']
        operations_details.append({
            'operation': op_data['operation'],
            'quantity': op_data['quantity'],
            'total_time_spent': total_time_spent,
            'total_payment_spent': total_payment_spent,
            'average_time_per_unit': (op_data['total_time'] / op_data['quantity']) if op_data['quantity'] else 0,
            'preferred_completion_time': op_data['preferred_completion_time'],
            'payment': op_data['payment']
        })
        total_time += total_time_spent
        total_payment += total_payment_spent

    overall_efficiency = total_weighted_efficiency / total_units if total_units else 100

    # 7) Summarize units produced by day using DB aggregation
    units_by_day_qs = assigned_works.filter(start_time__isnull=False) \
        .annotate(day=TruncDate('start_time')) \
        .values('day') \
        .annotate(total_units=Sum('quantity')) \
        .order_by('day')
    units_by_day = {entry['day']: entry['total_units'] for entry in units_by_day_qs}

    # 9) Convert operation distribution to list format
    operation_distribution_list = [
        {'operation': op, 'order': order, 'quantity': qty}
        for (op, order), qty in operation_distribution.items()
    ]

    response_data = {
        'id': employee.id,
        'full_name': f"{employee.user.first_name} {employee.user.last_name}",
        'employee_id': employee.employee_id,
        'efficiency': overall_efficiency,
        'operations': operations_details,
        'orders': [
            {'id': order_id, 'model_name': model_name}
            for order_id, model_name in orders_dict.items()
        ],
        'operation_distribution': operation_distribution_list,
        'total_time': total_time,
        'total_payment': total_payment,
        # Optionally include other fields if needed
    }

    return JsonResponse(response_data)

@method_decorator([login_required, admin_required], name='dispatch')
class OrderCalendarView(ListView):
    model = ClientOrder
    template_name = 'admin/calendar/calendar.html'
    context_object_name = 'orders'

    def get_queryset(self):
        current_month = timezone.now().month
        current_year = timezone.now().year
        queryset = super().get_queryset()
        return queryset.annotate(month=TruncMonth('term')).filter(month__month=current_month, month__year=current_year).values('id', 'order_number', 'term')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['events_url'] = reverse('order_calendar_events')
        return context
    

class OrderCalendarEventsView(View):
    def get(self, request, *args, **kwargs):
        current_month = timezone.now().month
        current_year = timezone.now().year
        client_orders = ClientOrder.objects.annotate(month=TruncMonth('term')).filter(
            month__month=current_month, month__year=current_year, is_archived=False
        ).select_related('client').prefetch_related('orders__model')

        events = []
        for client_order in client_orders:
            model_names = ', '.join(
                [order.model.name for order in client_order.orders.all()]
            )

            description = f"Client: {client_order.client.name}, Models: {model_names}"
            
            events.append({
                'id': client_order.id,
                'title': client_order.order_number,
                'start': client_order.term.isoformat(),
                'end': client_order.term.isoformat(),
                'description': description,
                'url': reverse('client_order_detail', kwargs={'pk': client_order.id})
            })
        
        return JsonResponse(events, safe=False)

@method_decorator([login_required, admin_required], name='dispatch')
class CutDetailAdminView(DetailView):
    model = Cut
    template_name = 'admin/cuts/detail.html'
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
            'sidebar_type': 'admin'
        })

        return context

@method_decorator([login_required, admin_required], name='dispatch')
class OrderUpdateView(UpdateView):
    model = Order
    form_class = OrderForm
    template_name = 'admin/orders/edit.html'
    def get_success_url(self):
        return reverse('order_detail', kwargs={'pk': self.object.pk})

@method_decorator([login_required, admin_required], name='dispatch')
class OrderDeleteView(DeleteView):
    model = Order
    template_name = 'admin/orders/delete.html'
    def get_success_url(self):
        return reverse('client_order_detail', kwargs={'pk': self.object.client_order.pk})
    
@login_required
@admin_required
def select_orders_view(request):
    """
    1) Displays a form with start_date and end_date (GET).
    2) On GET with valid date range, fetches Orders that have Cuts within that date range.
    3) Allows user to select which Orders to analyze (POST).
    4) Submits to another view (or can compute inline) to get employee calculations.
    """
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # Convert strings to date objects (if provided)
    orders = []
    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

            # Get all Cuts in [start_dt, end_dt]
            cuts_in_range = Cut.objects.filter(date__range=[start_dt, end_dt])

            # From those Cuts, get their Orders
            orders_in_range = Order.objects.filter(cuts__in=cuts_in_range).distinct().order_by('model__name')

            orders = orders_in_range

        except ValueError:
            # If date parsing fails, just ignore or handle error
            pass

    if request.method == 'POST':
        # The user has chosen specific order IDs to analyze
        selected_orders_ids = request.POST.getlist('order_ids')

        # Option A: Do the calculations right here and render a new template:
        # results = calculate_employee_data(selected_orders_ids)
        # return render(request, 'employee_calculation.html', {
        #     'results': results
        # })

        # Option B: Redirect to another view that does the calculation:
        return redirect('employee_calculation', order_ids=",".join(selected_orders_ids))

    context = {
        'orders': orders,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'admin/select_orders.html', context)


@login_required
@admin_required
def employee_calculation_view(request, order_ids):
    """
    Receives selected Orders (by ID), then calculates employees' work details based on:
      - total units produced
      - total seconds worked = sum of (quantity * operation.preferred_completion_time)
    Renders (or returns JSON for) employee data.
    """
    # Convert order_ids (comma-separated) into a list of integers
    order_ids_list = [int(id_str) for id_str in order_ids.split(',') if id_str.isdigit()]

    # Filter AssignedWork by the selected orders
    # (AssignedWork -> Work -> PassportSize -> Passport -> Cut -> Order)
    assigned_works = AssignedWork.objects.filter(
        work__passport_size__passport__cut__order__in=order_ids_list,
    )

    # We'll store data in a dict keyed by employee object
    # Example structure:
    # {
    #   employee_obj: {
    #       'units_produced': int,
    #       'seconds_worked': float,
    #       'operations': { operation_name: total_quantity_for_that_operation, ... },
    #   },
    #   ...
    # }
    employee_data_map = {}

    for aw in assigned_works.select_related('employee', 'work__operation'):
        emp = aw.employee
        operation = aw.work.operation
        operation_name = operation.name if operation else "Unknown Operation"
        
        # Get preferred completion time in seconds (fallback to 0 if None)
        preferred_time = operation.preferred_completion_time or 0
        payment_per_operation = operation.payment or 0
        
        if emp not in employee_data_map:
            employee_data_map[emp] = {
                'units_produced': 0,
                'seconds_worked': 0.0,
                'payment': 0,
                'operations': {}
            }

        # Increase units produced
        employee_data_map[emp]['units_produced'] += aw.quantity

        # Accumulate seconds worked = quantity * operation's preferred_completion_time
        employee_data_map[emp]['seconds_worked'] += aw.quantity * preferred_time
        employee_data_map[emp]['payment'] += aw.quantity * payment_per_operation

        # Track operation-level stats (optional)
        if operation_name not in employee_data_map[emp]['operations']:
            employee_data_map[emp]['operations'][operation_name] = 0
        employee_data_map[emp]['operations'][operation_name] += aw.quantity

    # Convert the dictionary into a list for easy template iteration
    employee_data_list = []
    for emp, data in employee_data_map.items():
        # Build a dictionary that matches what the template expects
        employee_data_list.append({
            'id': emp.id,  # For the modal's onclick fetchEmployeeDetails({{ employee.id }})
            'name': emp.user.username,  # This is the first column in your snippet
            'employee_id': emp.employee_id,
            'full_name': f"{emp.user.first_name} {emp.user.last_name}",
            'units_produced': data['units_produced'],
            'seconds_worked': int(data['seconds_worked']),  # Round or cast to int if desired
            'payment': int(data['payment']),
            'operations': data['operations'],
        })

    # Sort by units produced, descending (optional)
    employee_data_list.sort(key=lambda e: e['units_produced'], reverse=True)

    context = {
        # Your snippet does {% for employee in employee_data %}
        'employee_data': employee_data_list,
    }
    return render(request, 'admin/employee_calculation.html', context)


@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeListView(ListView):
    model = UserProfile
    template_name = 'admin/employees/list.html'
    context_object_name = 'employees'
    paginate_by = 10

    def get_queryset(self):
        return UserProfile.objects.filter(
            is_archived=False
        ).exclude(user__username='admin').annotate(
            employee_id_int=Cast('employee_id', IntegerField())
        ).order_by('employee_id_int')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['upload_form'] = UploadFileForm()
        
        return context
    
@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeCreateView(CreateView):
    template_name = 'admin/employees/create.html'
    form_class = UserWithProfileForm
    success_url = reverse_lazy('employee_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        return context

@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeDetailView(DetailView):
    model = UserProfile
    template_name = 'admin/employees/detail.html'
    context_object_name = 'employee'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        return context

@login_required
@admin_required
def employee_edit(request, pk):
    user_profile = get_object_or_404(UserProfile, pk=pk)
    user = user_profile.user

    if request.method == 'POST':
        user_form = UserEditForm(request.POST, instance=user)
        if user_form.is_valid():
            user_form.save()
            messages.success(request, 'Employee details updated successfully.')
            return redirect('employee_list')
    else:
        user_form = UserEditForm(instance=user)

    context = {'user_form': user_form, 'user_profile': user_profile}
    return render(request, 'admin/employees/edit.html', context)

@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeDeleteView(DeleteView):
    model = UserProfile
    template_name = 'admin/employees/delete.html'
    success_url = reverse_lazy('employee_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        return context
    
@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeArchiveView(UpdateView):
    model = UserProfile
    template_name = 'admin/employees/list.html'
    success_url = reverse_lazy('employee_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        return context
    
    def post(self, request, *args, **kwargs):
        employee = self.get_object()
        employee.is_archived = True
        employee.save()
        return HttpResponseRedirect(self.success_url)
   
@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeUnArchiveView(UpdateView):
    model = UserProfile
    template_name = 'admin/employees/list.html'
    success_url = reverse_lazy('employee_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        return context
    
    def post(self, request, *args, **kwargs):
        employee = self.get_object()
        employee.is_archived = False
        employee.save()
        return HttpResponseRedirect(self.success_url)
     
@method_decorator([login_required, admin_required], name='dispatch')
class ArchivedEmployeeListView(ListView):
    template_name = 'admin/employees/list.html'
    context_object_name = 'employees'
    paginate_by = 10
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        return context

    def get_queryset(self):
        return UserProfile.objects.filter(
            is_archived=True
            ).order_by('employee_id')
    

@login_required
@admin_required
@require_POST
def employee_upload(request):
    form = UploadFileForm(request.POST, request.FILES)
    if form.is_valid():
        excel_file = request.FILES['excel_file']
        try:
            workbook = openpyxl.load_workbook(excel_file)
            sheet = workbook.active
            # Get the current company from thread-local storage.
            current_company = get_current_company()
            if current_company is None:
                messages.error(request, 'No company found in context.')
                return redirect(reverse_lazy('employee_list'))

            with transaction.atomic():
                # Iterate rows skipping the header (starting at row 2)
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    first_name, last_name, employee_id, emp_type, password = row
                    
                    # Generate username using current company ID and employee ID.
                    username = f"{current_company.id}-{employee_id}"
                    
                    try:
                        # Because of your custom manager, this lookup is already company-aware.
                        profile = UserProfile.objects.get(employee_id=employee_id)
                    except UserProfile.DoesNotExist:
                        # Create a new user and UserProfile.
                        user = User.objects.create(
                            username=username,
                            first_name=first_name,
                            last_name=last_name
                        )
                        user.set_password(password)
                        user.save()
                        print(user)
                        # The save method on CompanyAwareModel will assign the current company.
                        profile = UserProfile.objects.create(
                            user=user,
                            employee_id=employee_id,
                            type=int(emp_type) if emp_type is not None else UserProfile.EMPLOYEE
                        )
                    else:
                        # Update existing user and profile.
                        user = profile.user
                        user.first_name = first_name
                        user.last_name = last_name
                        user.username = username
                        user.set_password(password)
                        user.save()
                        
                        profile.type = int(emp_type) if emp_type is not None else UserProfile.EMPLOYEE
                        profile.save()

            messages.success(request, 'Employees uploaded successfully.')
            return redirect(reverse_lazy('employee_list'))
        except Exception as e:
            messages.error(request, f'Error processing the file: {e}')
            return redirect(reverse_lazy('employee_list'))
        finally:
            workbook.close()
    else:
        messages.error(request, 'Invalid file format.')
        return redirect(reverse_lazy('employee_list'))
