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
from ..mixins import *
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
    """
    Returns an HTML snippet (table) with employee payment details
    for all AssignedWork records created within the date range.
    If order_ids are provided in the GET params, filters assigned works to include only those orders.
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
    ).select_related('employee', 'work__operation', 'work__passport_size__passport__cut__order')  # assuming an 'order' relation

    # Optionally filter by order_ids if provided (multiple order_ids can be passed)
    order_ids = request.GET.getlist('order_ids')
    if order_ids:
        assigned_works = assigned_works.filter(work__passport_size__passport__cut__order__id__in=order_ids)

    # Aggregate employee data
    employee_data_map = {}
    for aw in assigned_works:
        emp = aw.employee
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

    # 8) Calculate total defects for the employee
    total_defects = ErrorResponsibility.objects.filter(employee=employee).count()

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

@login_required
@admin_required
def dashboard_page(request):
    form = DateRangeForm(request.GET or None)
    client_data = []
    employee_data = []
    production_data = {}
    orders_data = []
    inventory_data = []
    client_orders_data = []

    if form.is_valid():
        start_date = timezone.make_aware(datetime.combine(form.cleaned_data['start_date'], datetime.min.time()))
        end_date = timezone.make_aware(datetime.combine(form.cleaned_data['end_date'], datetime.max.time()))
        client_data = get_client_data(start_date, end_date)
        employee_data = get_employee_data(start_date, end_date)
        production_data = get_production_data(start_date, end_date)
        orders_data = get_orders_data(start_date, end_date)
        inventory_data = get_inventory_data(start_date, end_date)
        client_orders_data = get_client_orders_data(start_date, end_date)
    else:
        # Default to the last 30 days if no valid dates are provided
        
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        client_data = get_client_data(start_date, end_date)
        employee_data = get_employee_data(start_date, end_date)
        production_data = get_production_data(start_date, end_date)
        orders_data = get_orders_data(start_date, end_date)
        inventory_data = get_inventory_data(start_date, end_date)
        client_orders_data = get_client_orders_data(start_date, end_date)      

    context = {
        'form': form,
        'client_data': client_data,
        'employee_data': employee_data,
        'production_data': production_data,
        'orders_data': orders_data,
        'inventory_data': inventory_data,
        'client_orders_data': client_orders_data
    }
    return render(request, 'dashboard.html', context)



class DateRangeForm(forms.Form):
    start_date = forms.DateField(
        widget=forms.TextInput(attrs={'type': 'date'}),
        required=True,
        label='Start Date'
    )
    end_date = forms.DateField(
        widget=forms.TextInput(attrs={'type': 'date'}),
        required=True,
        label='End Date'
    )
    
def get_client_orders_data(start_date, end_date):
    client_orders_data = ClientOrder.objects.filter(
        created_at__range=[start_date, end_date]
    ).select_related('client').values(
        'id', 'order_number', 'client__name', 'status', 'term'
    ).order_by('status')
    
    return list(client_orders_data)

def get_inventory_data(start_date, end_date):
    rolls_data = Roll.objects.annotate(
        available_meters=F('meters') - F('used_meters'),
        color_name=F('color__name'),  # Get the color name
        fabrics_name=F('fabrics__name')  # Get the fabrics name
    ).values(
        'id', 'name', 'color_name', 'fabrics_name', 'meters', 'used_meters', 'available_meters'
    )

    return list(rolls_data)

def get_orders_data(start_date, end_date):
    orders_data = Order.objects.filter(
        cuts__date__range=[start_date, end_date]
    ).distinct().select_related('model').annotate(
        model_name=F('model__name'),
        assortment_name=F('model__assortment__name'),
        total_price=F('quantity') * F('payment'),
        colors_list=ArrayAgg('colors__name', distinct=True),  # Group colors into a list
        fabrics_list=ArrayAgg('fabrics__name', distinct=True)  # Group fabrics into a list
    ).values(
        'id', 'model_name', 'quantity', 'total_price', 'status', 'assortment_name', 'colors_list', 'fabrics_list'
    ).order_by('assortment_name')

    return list(orders_data)

def get_production_data(start_date, end_date):
    recent_orders = Order.objects.filter(
        cuts__date__range=[start_date, end_date]
    ).distinct()
    
    in_progress_orders_count = recent_orders.filter(status=Order.IN_PROGRESS).count()

    total_amount = recent_orders.aggregate(total=Sum('quantity'))['total'] or 0

    total_revenue = recent_orders.aggregate(
        total=Sum(F('quantity') * F('payment'))
    )['total'] or 0

    completed_amount = recent_orders.aggregate(total=Sum('completed_quantity'))['total'] or 0

    orders_in_progress = ClientOrder.objects.filter(
        status=ClientOrder.IN_PROGRESS,
        created_at__range=[start_date, end_date]
    ).count()

    total_salary = AssignedWork.objects.filter(
        end_time__range=[start_date, end_date],
        is_success=True
    ).aggregate(total=Sum(F('quantity') * F('work__operation__payment')))['total'] or 0

    total_errors = Error.objects.filter(
        reported_date__range=[start_date, end_date]
    ).count()

    total_rolls_used = Passport.objects.filter(
        cut__date__range=[start_date, end_date],
        roll__isnull=False  # Ensures only Passports with associated rolls are counted
    ).aggregate(total_meters=Sum('meters'))['total_meters'] or 0

    return {
        'total_amount': total_amount,
        'total_revenue': total_revenue,
        'completed_amount': completed_amount,
        'orders_in_progress': orders_in_progress,
        'in_progress_orders_count': in_progress_orders_count,
        'total_salary': total_salary,
        'total_errors': total_errors,
        'total_rolls_used': total_rolls_used
    }


def get_client_data(start_date, end_date):
    client_orders = ClientOrder.objects.filter(created_at__range=[start_date, end_date])
    clients = Client.objects.filter(client_orders__in=client_orders).distinct()
    
    client_data = []
    for client in clients:
        client_orders = client.client_orders.filter(created_at__range=[start_date, end_date])
        
        total_ordered_amount_by_orders = client_orders.annotate(
            total_amount=Sum(F('orders__quantity') * F('orders__payment'))
        ).aggregate(sum=Sum('total_amount'))['sum'] or 0
        
        total_ordered_amount = client_orders.aggregate(
            total_amount=Sum('orders__quantity')
        )['total_amount'] or 0
        
        client_orders_details = []
        for co in client_orders:
            order_details = co.orders.aggregate(
                income=Sum(F('quantity') * F('payment')),
                total_quantity=Sum('quantity')
            ) or {'income': 0, 'total_quantity': 0}
            
            models = list(co.orders.values_list('model__name', flat=True))
            client_orders_details.append((
                co.order_number, 
                co.id, 
                models, 
                order_details['income'], 
                order_details['total_quantity']
            ))

        client_data.append({
            'id': client.id,
            'client': client.name,
            'client_orders_details': client_orders_details,
            'total_ordered_amount_by_orders': total_ordered_amount_by_orders,
            'total_ordered_amount': total_ordered_amount
        })

    return sorted(client_data, key=lambda x: x['total_ordered_amount'], reverse=True)

def get_employee_data(start_date, end_date):
    # Aggregating units produced by each employee from AssignedWork within the date range
    employee_units = AssignedWork.objects.filter(
        work__passport_size__passport__cut__date__range=[start_date, end_date]
    ).values('employee__id').annotate(
        total_units=Sum('quantity')
    ).order_by('-total_units')
    
    units_dict = {eu['employee__id']: eu['total_units'] for eu in employee_units}

    # Calculating hours worked from EmployeeAttendance within the date range
    employee_hours = {}
    attendances = EmployeeAttendance.objects.filter(
        timestamp__range=[start_date, end_date], 
        is_clock_in=True
    ).values('employee__id', 'timestamp').order_by('employee__id', 'timestamp')
    
    for emp_id, group in itertools.groupby(attendances, key=lambda x: x['employee__id']):
        timestamps = list(group)
        total_hours = sum(
            (timestamps[i+1]['timestamp'] - timestamps[i]['timestamp']).total_seconds() / 3600
            for i in range(0, len(timestamps) - 1, 2)
        ) if len(timestamps) % 2 == 0 else 0
        employee_hours[emp_id] = total_hours

    # Fetch all employees and compile their data with units produced and hours worked
    all_employees = UserProfile.objects.all().values(
        'id', 'user__username', 'user__first_name', 'user__last_name', 'employee_id'
    )

    employee_data = []
    for employee in all_employees:
        employee_id = employee['id']
        units_produced = units_dict.get(employee_id, 0)
        hours_worked = employee_hours.get(employee_id, 0)
        full_name = f"{employee['user__first_name']} {employee['user__last_name']}".strip()
        employee_data.append({
            'id': employee_id,
            'name': employee['user__username'],
            'employee_id': employee['employee_id'],
            'full_name': full_name,
            'units_produced': units_produced,
            'hours_worked': hours_worked
        })

    return sorted(employee_data, key=lambda x: x['units_produced'], reverse=True)

@method_decorator([login_required, admin_required], name='dispatch')
class BranchListView(ListView):
    model = Branch
    template_name = 'admin/branches/list.html'
    context_object_name = 'branches'
    paginate_by = 10

    def get_queryset(self):
        return Branch.objects.filter(is_archived=False).order_by('name')
@method_decorator([login_required, admin_required], name='dispatch')
class ArchivedBranchListView(ListView):
    model = Branch
    template_name = 'admin/branches/list.html'
    context_object_name = 'branches'
    paginate_by = 10

    def get_queryset(self):
        return Branch.objects.filter(is_archived=True).order_by('name')
    

    
@method_decorator([login_required, admin_required], name='dispatch')
class BranchCreateView(CreateView):
    model = Branch
    form_class = BranchForm
    template_name = 'admin/branches/create.html'
    success_url = reverse_lazy('branch_list')

@method_decorator([login_required, admin_required], name='dispatch')
class BranchDetailView(DetailView):
    model = Branch
    template_name = 'admin/branches/detail.html'
    context_object_name = 'branch'

@method_decorator([login_required, admin_required], name='dispatch')
class BranchUpdateView(UpdateView):
    model = Branch
    form_class = BranchForm
    template_name = 'admin/branches/edit.html'
    success_url = reverse_lazy('branch_list')

@method_decorator([login_required, admin_required], name='dispatch')
class BranchDeleteView(DeleteView):
    model = Branch
    template_name = 'admin/branches/delete.html'
    success_url = reverse_lazy('branch_list')
    
@method_decorator([login_required, admin_required], name='dispatch')
class BranchArchiveView(UpdateView):
    model = Branch
    template_name = 'admin/branches/list.html'
    success_url = reverse_lazy('branch_list')

    def post(self, request, *args, **kwargs):
        branch = self.get_object()
        branch.is_archived = True
        branch.save()
        return HttpResponseRedirect(self.success_url)
    

@method_decorator([login_required, admin_required], name='dispatch')
class BranchUnArchiveView(UpdateView):
    model = Branch  
    template_name = 'admin/branches/list.html'  
    success_url = reverse_lazy('branch_list') 

    def post(self, request, *args, **kwargs):
        branch = self.get_object()  
        branch.is_archived = False  
        branch.save() 
        return HttpResponseRedirect(self.success_url)  

@method_decorator([login_required, admin_required], name='dispatch')
class ArchivedBranchDetailView(DetailView):
    model = Branch
    template_name = 'admin/branches/archived_detail.html'
    context_object_name = 'archive_branch'
    
# @method_decorator([login_required, admin_required], name='dispatch')
# class ArchivedBranchDeleteView(DeleteView):
#     model = Branch
#     template_name = 'admin/branches/archived_delete.html'
#     success_url = reverse_lazy('archive_branch_list')

   
@login_required
@admin_required
def branch_switch(request):
    branch_id = request.POST.get('branch')
    
    try:
        new_branch = Branch.objects.get(id=branch_id)
        
        user_profile = UserProfile.objects.get(user=request.user)
        user_profile.branch = new_branch
        user_profile.save()
        
        messages.success(request, 'Branch switched successfully.')
        return redirect('admin_page')

    except Branch.DoesNotExist:
        messages.error(request, 'Selected branch does not exist.')
        return redirect('admin_page')

# @login_required
# @admin_required
# def passport_detail_admin(request, pk):
#     passport = get_object_or_404(Passport, pk=pk)
#     operations = passport.order.model.operations.all() 
#     size_quantities = PassportSize.objects.filter(passport=passport).order_by('size_quantity__size')
#     passport_rolls = PassportRoll.objects.filter(passport=passport)

#     work_by_op_and_size = {}
#     for assigned_work in AssignedWork.objects.filter(work__passport=passport).select_related('employee', 'work__operation', 'work__passport_size'):
#         # Key as a tuple of operation_id and passport_size_id
#         key = (assigned_work.work.operation_id, assigned_work.work.passport_size_id)
#         if key not in work_by_op_and_size:
#             work_by_op_and_size[key] = [assigned_work]
#         else:
#             work_by_op_and_size[key].append(assigned_work)

#     return render(request, 'admin/passports/detail.html', {
#         'passport': passport,
#         'passport_rolls': passport_rolls,
#         'operations': operations,
#         'size_quantities': size_quantities,
#         'work_by_op_and_size': work_by_op_and_size
#     })

@login_required
@admin_required
def salary_list(request):
    form = SalaryListForm(request.GET or None)
    salaries = {}

    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        salary_type = form.cleaned_data['salary_type']

        if salary_type == 'non_fixed':
            assigned_works = AssignedWork.objects.filter(
                end_time__range=(start_date, end_date),
                end_time__isnull=False,
                is_success=True,
                work__passport_size__passport__cut__order__client_order__branch=request.user.userprofile.branch
            ).select_related('work__operation', 'employee')

            reassigned_works = ReassignedWork.objects.filter(
                original_assigned_work__end_time__range=(start_date, end_date),
                is_success=True,
                original_assigned_work__work__passport_size__passport__cut__order__client_order__branch=request.user.userprofile.branch
            ).select_related('original_assigned_work__work__operation', 'new_employee')

            for work_group in [assigned_works, reassigned_works]:
                for work in work_group:
                    if work_group is assigned_works:
                        employee = work.employee
                        payment = work.work.operation.payment
                        quantity = work.quantity
                    else:  # This is for reassigned_works
                        employee = work.new_employee
                        payment = work.original_assigned_work.work.operation.payment
                        quantity = work.reassigned_quantity

                    if employee not in salaries:
                        salaries[employee] = {'salary': 0, 'status': 0, 'errors': 0, 'error_cost': 0}
                    
                    salaries[employee]['salary'] += payment * quantity
                    salaries[employee]['status'] = 1 if work.payment_date else 0

                    if employee.type not in [UserProfile.ADMIN, UserProfile.TECHNOLOGIST]:
                        error_responsibilities = ErrorResponsibility.objects.filter(
                            employee=employee,
                            error__reported_date__range=(start_date, end_date)
                        )
                        for responsibility in error_responsibilities:
                            salaries[employee]['error_cost'] += responsibility.error.cost * (responsibility.percentage / 100)

        elif salary_type == 'fixed':
            fixed_salaries = FixedSalary.objects.filter(branch=request.user.userprofile.branch)
            for fixed_salary in fixed_salaries:
                for employee in fixed_salary.employees.all():
                    timestamps = EmployeeAttendance.objects.filter(
                        employee=employee,
                        timestamp__range=(start_date, end_date)
                    ).order_by('timestamp').annotate(
                        next_timestamp=Window(
                            expression=Lead('timestamp'),
                            order_by=F('timestamp').asc(),
                            partition_by=[F('employee')]
                        )
                    )

                    total_salary = 0
                    for attendance in timestamps:
                        if attendance.is_clock_in and attendance.next_timestamp:
                            if (attendance.next_timestamp - attendance.timestamp).total_seconds() <= 86400:
                                total_salary += fixed_salary.salary

                    if total_salary > 0:
                        if employee not in salaries:
                            salaries[employee] = {'salary': total_salary, 'status': 0, 'errors': 0, 'error_cost': 0}

                        error_responsibilities = ErrorResponsibility.objects.filter(
                            employee=employee,
                            error__reported_date__range=(start_date, end_date)
                        )
                        for responsibility in error_responsibilities:
                            salaries[employee]['error_cost'] += responsibility.error.cost * (responsibility.percentage / 100)

                        payment_exists = SalaryPayment.objects.filter(
                            employee=employee,
                            fixed_salary=fixed_salary,
                            payment_date__range=(start_date, end_date)
                        ).exists()
                        
                        salaries[employee]['status'] = 1 if payment_exists else 0

    context = {'form': form, 'salaries': {k: v for k, v in salaries.items() if v['salary'] > 0}}
    return render(request, 'admin/salaries/list.html', context)

@login_required
@admin_required
@require_POST
def process_payments(request):
    form = SalaryListForm(request.POST)
    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        salary_type = form.cleaned_data['salary_type']

        if salary_type == 'non_fixed':
            # Process Non-Fixed Salary Payments (Existing logic)
            assigned_works = AssignedWork.objects.filter(
                end_time__range=(start_date, end_date),
                work__passport_size__passport__cut__order__client_order__branch=request.user.userprofile.branch
            )

            reassigned_works = ReassignedWork.objects.filter(
                original_assigned_work__end_time__range=(start_date, end_date),
                original_assigned_work__work__passport_size__passport__cut__order__client_order__branch=request.user.userprofile.branch
            )

            for work in assigned_works:
                work.payment_date = timezone.now()
                work.save()

            for work in reassigned_works:
                work.payment_date = timezone.now()
                work.save()

        elif salary_type == 'fixed':
            fixed_salaries = FixedSalary.objects.filter(
                branch=request.user.userprofile.branch
            ).prefetch_related('employees')

            for fixed_salary in fixed_salaries:
                for employee in fixed_salary.employees.all():
                    attendances = EmployeeAttendance.objects.filter(
                        employee=employee,
                        timestamp__range=(start_date, end_date)
                    ).order_by('timestamp').annotate(
                        next_timestamp=Window(
                            expression=Lead('timestamp'),
                            order_by=F('timestamp').asc(),
                            partition_by=[F('employee')]
                        )
                    )

                    days_processed = set()
                    for attendance in attendances:
                        if attendance.is_clock_in and attendance.next_timestamp:
                            # Check for valid clock-out within 24 hours to accommodate overnight shifts
                            clock_in_local = timezone.localtime(attendance.timestamp)
                            clock_out_local = timezone.localtime(attendance.next_timestamp)
                            if (clock_out_local - clock_in_local).total_seconds() <= 86400:
                                day_key = clock_in_local.date()
                                if day_key not in days_processed:
                                    days_processed.add(day_key)

                    days_with_complete_records = len(days_processed)

                    if days_with_complete_records > 0:
                        first_day_of_month = start_date.replace(day=1)
                        last_day_of_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

                        existing_payment = SalaryPayment.objects.filter(
                            employee=employee,
                            payment_date__range=(first_day_of_month, last_day_of_month)
                        ).exists()

                        if not existing_payment:
                            total_salary = days_with_complete_records * fixed_salary.salary
                            SalaryPayment.objects.create(
                                fixed_salary=fixed_salary,
                                employee=employee,
                                payment_date=timezone.now(),
                                amount=total_salary
                            )

        base_url = reverse('salary_list')
        query_string = urlencode({
            'start_date': start_date.strftime('%Y-%m-%d'), 
            'end_date': (end_date - timedelta(days=1)).strftime('%Y-%m-%d'),
            'salary_type': salary_type
        })
        url = f"{base_url}?{query_string}"
        return redirect(url)

    else:
        return redirect('salary_list')

@login_required
@admin_required
def salary_detail(request, pk):
    employee = get_object_or_404(UserProfile, pk=pk, branch=request.user.userprofile.branch)
    initial_data = {
        'start_date': request.GET.get('start_date'),
        'end_date': request.GET.get('end_date'),
        'salary_type': request.GET.get('salary_type', 'non_fixed') 
    }
    form = SalaryListForm(request.GET or None, initial=initial_data)
    assigned_work_details = []
    total_salary = 0
    error_details = []

    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        salary_type = form.cleaned_data['salary_type']

        if salary_type == 'non_fixed':
            assigned_works = AssignedWork.objects.filter(
                employee=employee,
                end_time__range=(start_date, end_date),
                is_success=True,
                work__passport_size__passport__cut__order__client_order__branch=request.user.userprofile.branch
            ).select_related('work__operation', 'work__passport_size__size_quantity', 'work__passport_size__passport__cut__order__model')

            reassigned_works = ReassignedWork.objects.filter(
                new_employee=employee,
                original_assigned_work__end_time__range=(start_date, end_date),
                is_success=True,
                original_assigned_work__work__passport_size__passport__cut__order__client_order__branch=request.user.userprofile.branch
            ).select_related('original_assigned_work__work__operation', 'original_assigned_work__work__passport_size__size_quantity', 'original_assigned_work__work__passport_size__passport__cut__order__model')

            for work in assigned_works:
                work_salary, work_details = calculate_salary_and_details(work)
                total_salary += work_salary

                # Add model and passport/cut information
                work_details['model'] = work.work.passport_size.passport.cut.order.model.name
                work_details['passport_cut'] = f"{work.work.passport_size.passport.number} / {work.work.passport_size.passport.cut.number}"

                assigned_work_details.append(work_details)

            for work in reassigned_works:
                work_salary, work_details = calculate_salary_and_details(work.original_assigned_work, reassigned_quantity=work.reassigned_quantity)
                total_salary += work_salary

                # Add model and passport/cut information
                work_details['model'] = work.original_assigned_work.work.passport_size.passport.cut.order.model.name
                work_details['passport_cut'] = f"{work.original_assigned_work.work.passport_size.passport.number} / {work.original_assigned_work.work.passport_size.passport.cut.number}"

                assigned_work_details.append(work_details)

            # Calculate errors only if the employee is of type EMPLOYEE
            if employee.type not in [UserProfile.ADMIN, UserProfile.TECHNOLOGIST]:
                error_details = calculate_errors(employee, start_date, end_date)
                total_error_cost = sum(detail['cost'] for detail in error_details)
                total_salary -= total_error_cost

        elif salary_type == 'fixed':
            fixed_salary = FixedSalary.objects.filter(employees=employee, branch=request.user.userprofile.branch).first()
            if fixed_salary:
                attendances = EmployeeAttendance.objects.filter(
                    employee=employee,
                    timestamp__range=(start_date, end_date)
                ).order_by('timestamp').annotate(
                    next_timestamp=Window(
                        expression=Lead('timestamp'),
                        order_by=F('timestamp').asc(),
                        partition_by=[F('employee')]
                    )
                )

                for attendance in attendances:
                    if attendance.is_clock_in and attendance.next_timestamp:
                        if (attendance.next_timestamp - attendance.timestamp).total_seconds() <= 86400:
                            clock_in_local = timezone.localtime(attendance.timestamp)
                            clock_out_local = timezone.localtime(attendance.next_timestamp)
                            duration = clock_out_local - clock_in_local
                            hours, remainder = divmod(duration.total_seconds(), 3600)
                            minutes = remainder // 60
                            total_salary += fixed_salary.salary
                            assigned_work_details.append({
                                'date': clock_in_local.date(),
                                'clock_in': clock_in_local,
                                'clock_out': clock_out_local,
                                'hours_worked': f"{int(hours)}h {int(minutes)}m",
                                'daily_salary': fixed_salary.salary,
                                'model': 'N/A',  # Fixed salary doesn't involve specific models
                                'passport_cut': 'N/A'
                            })

                # Calculate errors for all employees on fixed salary
                error_details = calculate_errors(employee, start_date, end_date)
                total_error_cost = sum(detail['cost'] for detail in error_details)
                total_salary -= total_error_cost

    context = {
        'form': form,
        'employee': employee,
        'works': assigned_work_details,
        'total_salary': total_salary,
        'errors': error_details
    }
    return render(request, 'admin/salaries/detail.html', context)

def calculate_errors(employee, start_date, end_date):
    error_responsibilities = ErrorResponsibility.objects.filter(
        employee=employee,
        error__reported_date__range=(start_date, end_date)
    ).select_related('error')

    error_details = [{
        'type': 'Дефект' if resp.error.error_type == Error.ErrorType.DEFECT else 'Несоответствие',
        'passport': resp.error.piece.passport_size.passport.id,
        'size': resp.error.piece.passport_size.size_quantity.size,
        'quantity': resp.error.piece.passport_size.quantity,
        'reported_date': resp.error.reported_date,
        'cost': resp.error.cost * (resp.percentage / 100)
    } for resp in error_responsibilities]

    return error_details

def calculate_salary_and_details(work, reassigned_quantity=None):
    """Helper function to calculate salary and details for a work or reassigned work."""
    quantity = reassigned_quantity if reassigned_quantity is not None else work.quantity
    work_salary = work.work.operation.payment * quantity
    time_spent = (work.end_time - work.start_time).total_seconds() if work.start_time and work.end_time else 0
    return work_salary, {
        'operation': work.work.operation,
        'size': work.work.passport_size.size_quantity.size,
        'quantity': quantity,
        'time_spent_seconds': time_spent,
        'work_salary': work_salary
    }

@login_required
@admin_required
def export_salaries_to_excel(request):
    form = SalaryListForm(request.GET or None)

    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        salary_type = form.cleaned_data['salary_type']
        data = []
        errors_data = []

        if salary_type == 'non_fixed':
            assigned_works = AssignedWork.objects.filter(
                end_time__range=(start_date, end_date),
                is_success=True
            ).select_related('work__operation', 'work__passport', 'work__passport__order', 'employee', 'work__passport_size')

            reassigned_works = ReassignedWork.objects.filter(
                original_assigned_work__end_time__range=(start_date, end_date),
                is_success=True
            ).select_related('original_assigned_work', 'new_employee', 'original_assigned_work__work__passport_size')

            for work in assigned_works:
                passport = work.work.passport
                passport_size = work.work.passport_size
                order = passport.order
                data.append([
                    datetime.now().date(), order.client_order.client.name, order.model.name if order.model else '',
                    order.assortment.name if order.assortment else '', passport.id, passport_size.size_quantity.size,
                    order.color, order.fabrics, passport.date, work.work.operation.id,
                    work.work.operation.name, work.work.operation.payment, work.employee.employee_id,
                    work.employee.user.get_full_name(), work.quantity,
                    work.work.operation.payment * work.quantity
                ])

            for work in reassigned_works:
                original = work.original_assigned_work
                passport = original.work.passport
                passport_size = original.work.passport_size
                order = passport.order
                data.append([
                    datetime.now().date(), order.client_order.client.name, order.model.name if order.model else '',
                    order.assortment.name if order.assortment else '', passport.id, passport_size.size_quantity.size,
                    order.color, order.fabrics, passport.date, original.work.operation.id,
                    original.work.operation.name, original.work.operation.payment, work.new_employee.employee_id,
                    work.new_employee.user.get_full_name(), work.reassigned_quantity,
                    original.work.operation.payment * work.reassigned_quantity
                ])

            salary_df = pd.DataFrame(data, columns=[
                "Today's date", "Client's name", "Model's name", "Assortment's name", "Passport id", 
                "Passport size", "Order's color", "Order's fabrics", "Passport date", "Operation id", 
                "Operation name", "Operation payment", "ID", "Employee", 
                "Work's quantity", "Salary"
            ])

            employees = UserProfile.objects.filter(type=UserProfile.EMPLOYEE)

        elif salary_type == 'fixed':
            fixed_salaries = FixedSalary.objects.filter(
                branch=request.user.userprofile.branch
            ).prefetch_related('employees')

            for fixed_salary in fixed_salaries:
                for employee in fixed_salary.employees.all():
                    attendances = EmployeeAttendance.objects.filter(
                        employee=employee,
                        timestamp__range=(start_date, end_date)
                    ).order_by('timestamp').values_list('timestamp', flat=True)

                    paired_times = []
                    for i in range(0, len(attendances) - 1, 2):
                        if len(attendances) > i + 1:
                            clock_in = attendances[i]
                            clock_out = attendances[i + 1]
                            if clock_in < clock_out:
                                paired_times.append((clock_in, clock_out))

                    for clock_in, clock_out in paired_times:
                        clock_in_local = timezone.localtime(clock_in)
                        clock_out_local = timezone.localtime(clock_out)
                        duration = clock_out_local - clock_in_local
                        hours, remainder = divmod(duration.total_seconds(), 3600)
                        minutes = remainder // 60
                        data.append([
                            employee.user.get_full_name(),
                            employee.employee_id,
                            clock_in_local.date(),
                            clock_in_local.strftime('%H:%M:%S'),
                            clock_out_local.strftime('%H:%M:%S'),
                            f"{int(hours)}h {int(minutes)}m",
                            fixed_salary.salary
                        ])

            salary_df = pd.DataFrame(data, columns=[
                "Employee", "ID", "Date", "Clock in", "Clock out", "Hours worked", "Salary per day"
            ])

            employees = UserProfile.objects.all()

        # Process errors for selected employees
        for employee in employees:
            error_responsibilities = ErrorResponsibility.objects.filter(
                employee=employee,
                error__reported_date__range=(start_date, end_date)
            ).select_related('error')

            for responsibility in error_responsibilities:
                errors_data.append([
                    responsibility.error.piece.passport_size.passport.order.model.name,
                    responsibility.error.piece.passport_size.passport.id,
                    responsibility.error.piece.passport_size.size_quantity.size,
                    employee.user.get_full_name(),
                    employee.employee_id,
                    'Defect' if responsibility.error.error_type == Error.ErrorType.DEFECT else 'Discrepancy',
                    responsibility.error.reported_date.strftime('%Y-%m-%d'),
                    responsibility.error.cost * (responsibility.percentage / 100)
                ])

        errors_df = pd.DataFrame(errors_data, columns=[
            "Model", "Passport ID", "Size", "Employee", "ID", "Error Type", "Reported Date", "Error Cost"
        ])

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="salaries.xlsx"'
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            salary_df.to_excel(writer, sheet_name='Salaries', index=False)
            errors_df.to_excel(writer, sheet_name='Errors', index=False)  # Writing errors to a separate sheet
        
        return response

    # Handle form errors or initial page access
    context = {'form': form}
    return render(request, 'blank.html', context)



@login_required
@admin_required
def attendance_list(request):
    form = DateForm()
    attendances = None

    if request.method == 'POST':
        form = DateForm(request.POST)
        if form.is_valid():
            selected_date = form.cleaned_data['date']
            next_day = selected_date + timedelta(days=1)
            
            attendances = EmployeeAttendance.objects.filter(
                timestamp__range=(selected_date, next_day),
                is_clock_in=True,
                branch=request.user.userprofile.branch 
            ).distinct('employee')

    context = {
        'form': form,
        'attendances': attendances,
    }
    return render(request, 'admin/attendances/list.html', context)


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
    
@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryListView(RestrictBranchMixin, ListView):
    model = FixedSalary
    template_name = 'admin/fixed_salaries/list.html'
    context_object_name = 'fixed_salaries'
    paginate_by = 10
    def get_queryset(self):
        return FixedSalary.objects.filter(
            is_archived = False
            ).order_by('position')

@method_decorator([login_required, admin_required], name='dispatch')
class ArchivedFixedSalaryListView(RestrictBranchMixin, ListView):
    model = FixedSalary
    template_name = 'admin/fixed_salaries/list.html'
    context_object_name = 'fixed_salaries'
    paginate_by = 10
    def get_queryset(self):
        return FixedSalary.objects.filter(
            is_archived = True
            ).order_by('position')

@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryCreateView(AssignBranchMixin, CreateView):
    model = FixedSalary
    form_class = FixedSalaryForm
    template_name = 'admin/fixed_salaries/create.html'
    success_url = reverse_lazy('fixed_salary_list')

@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryDetailView(DetailView):
    model = FixedSalary
    template_name = 'admin/fixed_salaries/detail.html'
    context_object_name = 'fixed_salary'

@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryUpdateView(RestrictBranchMixin, UpdateView):
    model = FixedSalary
    form_class = FixedSalaryForm
    template_name = 'admin/fixed_salaries/edit.html'
    success_url = reverse_lazy('fixed_salary_list')

@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryDeleteView(RestrictBranchMixin, DeleteView):
    model = FixedSalary
    template_name = 'admin/fixed_salaries/delete.html'
    success_url = reverse_lazy('fixed_salary_list')


@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryArchiveView(RestrictBranchMixin, UpdateView):
    model = FixedSalary
    template_name = 'admin/fixed_salaries/delete.html'
    success_url = reverse_lazy('fixed_salary_list')
    
    def post(self, request, *args, **kwargs):
        fixed_salary = self.get_object()
        fixed_salary.is_archived = True
        fixed_salary.save()
        return HttpResponseRedirect(self.success_url)


@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryUnArchiveView(RestrictBranchMixin, UpdateView):
    model = FixedSalary
    template_name = 'admin/fixed_salaries/delete.html'
    success_url = reverse_lazy('fixed_salary_list')
    
    def post(self, request, *args, **kwargs):
        fixed_salary = self.get_object()
        fixed_salary.is_archived = False
        fixed_salary.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, admin_required], name='dispatch')
class ErrorDetailAdminView(CreateView):
    model = ErrorResponsibility
    form_class = ErrorResponsibilityForm
    template_name = 'admin/errors/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        error = get_object_or_404(Error, pk=self.kwargs.get('pk'))
        context['error'] = error
        context['responsibility_errors'] = ErrorResponsibility.objects.filter(error=error)
        return context

    def form_valid(self, form):
        responsibility = form.save(commit=False)
        error_id = self.kwargs['pk']
        responsibility.error_id = error_id
        responsibility.save()
        return redirect('error_detail_admin', pk=error_id)
    
    def get_success_url(self):
        return reverse('error_detail_admin', kwargs={'pk': self.kwargs['pk']})

@login_required
@admin_required
@require_POST
def error_edit_admin(request, rd_id):
    try:
        data = json.loads(request.body)
        percentage = Decimal(data.get('percentage'))
        
        errorResponsibility = ErrorResponsibility.objects.get(id=rd_id)
        errorResponsibility.percentage = percentage
        errorResponsibility.save()
        return JsonResponse({'status': 'success', 'message': 'Percentage updated successfully'})

    except ErrorResponsibility.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'ErrorResponsibility not found'}, status=404)
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@login_required
@admin_required
@require_POST
def error_delete_admin(request, rd_id):
    try:
        errorResponsibility = ErrorResponsibility.objects.get(id=rd_id)
        errorResponsibility.delete()

        return JsonResponse({'status': 'success', 'message': 'ErrorResponsibility deleted successfully'})

    except ErrorResponsibility.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'ErrorResponsibility not found'}, status=404)
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@admin_required
@require_POST
def edit_error_cost_admin(request, error_id):
    error = get_object_or_404(Error, pk=error_id)
    try:
        data = json.loads(request.body)
        new_cost = data.get('cost')
        if new_cost:
            new_cost = new_cost.replace(',', '.')
            new_cost = Decimal(new_cost)
        error.cost = new_cost
        error.save()
        return JsonResponse({'status': 'success'})
    except Exception as e :
        return JsonResponse({'status': 'error', 'message': str(e)})




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