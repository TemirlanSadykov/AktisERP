from datetime import timedelta, datetime
from decimal import Decimal
import json
import openpyxl
import pandas as pd
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

from django.db.models.functions import TruncMonth

import itertools

from ..decorators import admin_required
from ..forms import *
from ..models import *
from datetime import datetime, timedelta
from django.utils import timezone

@login_required
@admin_required
def admin_page(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # Default summary data
    summary_data = {
        'total_production': 0,  # Sum of order quantities
        'orders_count': 0,      # Count of orders
        'cuts_count': 0,        # Count of cuts
        'total_payment': 0,     # Sum of payment amounts from AssignedWork
    }

    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

            # Use orders created within the given date range
            orders_in_range = Order.objects.filter(created_at__date__range=[start_dt, end_dt])
            total_production = orders_in_range.aggregate(total=Sum('quantity'))['total'] or 0
            orders_count = orders_in_range.count()
            cuts_count = Cut.objects.filter(date__range=[start_dt, end_dt]).count()

            payment_expr = ExpressionWrapper(
                F('quantity') * F('work__operation__payment'),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
            total_payment = AssignedWork.objects.filter(created_at__date__range=[start_dt, end_dt]).annotate(
                work_payment=payment_expr
            ).aggregate(total_payment=Sum('work_payment'))['total_payment'] or 0

            summary_data = {
                'total_production': total_production,
                'orders_count': orders_count,
                'cuts_count': cuts_count,
                'total_payment': total_payment,
            }
        except ValueError:
            # If the provided dates are invalid, leave summary_data as zeros.
            pass
    else:
        # No date range provided—use the current state based on active client orders.
        today = date.today()
        # Get client orders where today is between launch_date and term_date.
        active_client_orders = ClientOrder.objects.filter(launch__lte=today, term__gte=today)
        # Get all orders that belong to these active client orders.
        orders_in_range = Order.objects.filter(client_order__in=active_client_orders)
        total_production = orders_in_range.aggregate(total=Sum('quantity'))['total'] or 0
        orders_count = orders_in_range.count()
        # Count cuts for orders that belong to active client orders.
        cuts_count = Cut.objects.filter(order__client_order__in=active_client_orders).count()

        payment_expr = ExpressionWrapper(
            F('quantity') * F('work__operation__payment'),
            output_field=DecimalField(max_digits=10, decimal_places=2)
        )
        total_payment = AssignedWork.objects.filter(
            work__passport_size__passport__cut__order__client_order__in=active_client_orders
        ).annotate(work_payment=payment_expr).aggregate(total_payment=Sum('work_payment'))['total_payment'] or 0

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
        client_orders = ClientOrder.objects.filter(is_archived=False)
    else:
        client_orders = ClientOrder.objects.filter(
            is_archived=False,
            launch__range=[start_dt, end_dt]
        )
    
    client_orders_data = []
    for co in client_orders:
        orders_data = []
        for order in co.orders.all():
            # Join names for many-to-many fields
            color_names = ", ".join([color.name for color in order.colors.all()])
            fabric_names = ", ".join([fabric.name for fabric in order.fabrics.all()])
            unique_sizes = sorted({sq.size for sq in order.size_quantities.all() if sq.size})
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
      - cut (aggregated from CutSize.quantity)
      - sew (aggregated from AssignedWork.quantity)
      - check (count of ProductionPiece records in the CHECKED stage)
      - packed (count of ProductionPiece records in the PACKED stage)

    Production aggregations are filtered using the specific SizeQuantity ID.
    """
    order = get_object_or_404(Order, pk=order_id)
    
    # Get all SizeQuantity objects associated with the order.
    size_quantities = order.size_quantities.all()

    # Group the SizeQuantity objects by unique (color, fabric) pair.
    # Within each group, assume there is only one record per size.
    groups = {}  # key: (color, fabric)
    for sq in size_quantities:
        color_name = sq.color.name if sq.color else ""
        fabric_name = sq.fabrics.name if sq.fabrics else ""
        key = (color_name, fabric_name)
        if key not in groups:
            groups[key] = {}
        # Group by size; we only store one record per size.
        if sq.size:
            if sq.size not in groups[key]:
                groups[key][sq.size] = {"id": sq.id, "total": sq.quantity or 0}
            # If a duplicate is encountered for the same size, it is ignored.
    
    group_list = []
    # For each unique (color, fabric) group...
    for (color_name, fabric_name), sizes_dict in groups.items():
        sizes_data = []
        # Loop through each size in the group.
        for size_value, data_dict in sizes_dict.items():
            size_id = data_dict["id"]
            total_ordered = data_dict["total"]
            
            # Aggregate "Cut" quantity using the specific SizeQuantity ID.
            passport_qs = Passport.objects.filter(
                cut__order=order,
                size_quantities__id=size_id
            )

            passport_qs = passport_qs.filter()
            cut_total = passport_qs.aggregate(total=Sum('layers'))['total'] or 0

            # Aggregate "Sew" quantity from AssignedWork using the SizeQuantity ID.
            sew_total = 0
            for passport in passport_qs:
                assigned = AssignedWork.objects.filter(work__passport_size__passport=passport)
                if assigned.exists():
                    # If there is any assigned work for this passport, add the passport's full quantity.
                    sew_total += passport.layers
            
            # Count "Check" quantity from ProductionPiece records in the CHECKED stage.
            check_qs = ProductionPiece.objects.filter(
                passport_size__passport__in=passport_qs,
                stage__in=[ProductionPiece.StageChoices.CHECKED, ProductionPiece.StageChoices.PACKED]
            )
            check_total = check_qs.count()

            # Count "Packed" quantity from ProductionPiece records in the PACKED stage using the same passports.
            packed_qs = ProductionPiece.objects.filter(
                passport_size__passport__in=passport_qs,
                stage=ProductionPiece.StageChoices.PACKED
            )
            packed_total = packed_qs.count()
            
            sizes_data.append({
                "size": size_value,
                "total": total_ordered,
                "cut": cut_total,
                "sew": sew_total,
                "check": check_total,
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
def payment_details_view(request):
    """
    Returns an HTML snippet (table) with employee payment details
    for all AssignedWork records created within the date range.
    """
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        # If dates are missing or invalid, return an empty table
        return render(request, 'admin/partial_payment_details.html', {'employee_data': []})

    # Filter AssignedWork records within the date range
    assigned_works = AssignedWork.objects.filter(
        created_at__date__range=[start_dt, end_dt]
    ).select_related('employee', 'work__operation')

    # Aggregate employee data
    employee_data_map = {}
    for aw in assigned_works:
        emp = aw.employee
        # Use operation details for timing and payment values
        operation = aw.work.operation
        preferred_time = operation.preferred_completion_time or 0
        payment_per_operation = operation.payment or 0

        if emp not in employee_data_map:
            employee_data_map[emp] = {
                'units_produced': 0,
                'seconds_worked': 0,
                'payment': 0,
            }
        employee_data_map[emp]['units_produced'] += aw.quantity
        employee_data_map[emp]['seconds_worked'] += aw.quantity * preferred_time
        employee_data_map[emp]['payment'] += aw.quantity * payment_per_operation

    # Convert to a list for easier iteration in the template
    employee_data_list = []
    for emp, data in employee_data_map.items():
        employee_data_list.append({
            'id': emp.id,
            'employee_id': emp.employee_id,
            'full_name': f"{emp.user.first_name} {emp.user.last_name}",
            'units_produced': data['units_produced'],
            'seconds_worked': int(data['seconds_worked']),
            'payment': int(data['payment']),
        })

    # Optionally, sort by units produced descending
    employee_data_list.sort(key=lambda e: e['units_produced'], reverse=True)

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

    # 5) Group operations and calculate summary details
    operation_summary = {}
    total_units = 0
    total_weighted_efficiency = 0
    operation_distribution = {}

    for work in assigned_works:
        operation_name = work.work.operation.name
        order_id = work.work.passport_size.passport.cut.order.id
        preferred_completion_time = work.work.operation.preferred_completion_time
        payment = work.work.operation.payment
        actual_time = 0
        if work.start_time and work.end_time:
            actual_time = (work.end_time - work.start_time).total_seconds()

        # Initialize or update the summary for this operation
        if operation_name not in operation_summary:
            operation_summary[operation_name] = {
                'operation': operation_name,
                'quantity': work.quantity,
                'total_time': actual_time,
                'preferred_completion_time': preferred_completion_time,
                'payment': payment,
            }
        else:
            operation_summary[operation_name]['quantity'] += work.quantity
            operation_summary[operation_name]['total_time'] += actual_time

        # Operation distribution across orders
        key = (operation_name, order_id)
        operation_distribution[key] = operation_distribution.get(key, 0) + work.quantity

    # 6) Build the list of operation details
    operations_details = []
    total_time = 0
    total_payment = 0
    for op_data in operation_summary.values():
        total_time_spent = op_data['preferred_completion_time'] * op_data['quantity']
        total_payment_spent = op_data['payment'] * op_data['quantity']
        avg_time_per_unit = (op_data['total_time'] / op_data['quantity']) if op_data['quantity'] else 0
        efficiency = (op_data['preferred_completion_time'] / avg_time_per_unit) * 100 if avg_time_per_unit else 100

        total_units += op_data['quantity']
        total_weighted_efficiency += (efficiency * op_data['quantity'])
        total_time += total_time_spent
        total_payment += total_payment_spent

        operations_details.append({
            'operation': op_data['operation'],
            'quantity': op_data['quantity'],
            'total_time_spent': total_time_spent,
            'total_payment_spent': total_payment_spent,
            'average_time_per_unit': avg_time_per_unit,
            'preferred_completion_time': op_data['preferred_completion_time'],
            'payment': op_data['payment']
        })

    overall_efficiency = total_weighted_efficiency / total_units if total_units else 100

    # 7) Summarize units produced by day (if needed)
    units_by_day = {}
    for work in assigned_works:
        if work.start_time:
            day = work.start_time.date()
            units_by_day[day] = units_by_day.get(day, 0) + work.quantity
    # units_over_time = [{'date': date, 'units': units} for date, units in sorted(units_by_day.items())]

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
        # Optionally include other fields (e.g., total_defects) if needed
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