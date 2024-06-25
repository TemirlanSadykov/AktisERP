from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from ..decorators import admin_required
from django.http import JsonResponse
from django.db.models import Sum, F
from django.utils.dateformat import DateFormat

from ..models import *

@login_required
@admin_required
def client_api(request, client_id):
    try:
        client = Client.objects.get(pk=client_id)

        # Gather all client_orders by this client
        client_orders = ClientOrder.objects.filter(client=client).order_by('created_at')

        # Calculate total spendings across all orders
        total_spendings = sum(order.payment * order.quantity for order in Order.objects.filter(client_order__in=client_orders))

        # Aggregate spendings per order and group by the date of the client order
        spendings_by_date = []
        for co in client_orders:
            orders = Order.objects.filter(client_order=co)
            total_spent = orders.aggregate(
                total_spent=Sum(F('payment') * F('quantity'))
            )['total_spent'] or 0

            # Format date and sum spendings
            date = DateFormat(co.created_at).format('Y-m-d')
            spendings_by_date.append({
                'date': date,
                'co': co.order_number,
                'spendings': total_spent
            })

        response_data = {
            'id': client.id,
            'name': client.name,
            'contact_info': client.contact_info,
            'total_spendings': total_spendings,
            'spendings_over_time': spendings_by_date
        }

        return JsonResponse(response_data)

    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)
    
@login_required
@admin_required
def employee_api(request, employee_id):
    try:
        employee = UserProfile.objects.get(pk=employee_id)

        # Calculate earnings based on assigned works
        assigned_works = AssignedWork.objects.filter(employee=employee, is_success=True)
        earnings = sum(work.quantity * work.work.operation.payment for work in assigned_works)

        # Group operations and calculate average time spent in seconds
        operation_summary = {}
        total_units = 0
        total_weighted_efficiency = 0

        for work in assigned_works:
            operation_name = work.work.operation.name
            preferred_completion_time = work.work.operation.preferred_completion_time
            total_time = (work.end_time - work.start_time).total_seconds() if work.end_time and work.start_time else 0
            if operation_name not in operation_summary:
                operation_summary[operation_name] = {
                    'operation': operation_name,
                    'quantity': work.quantity,
                    'total_time': total_time,
                    'preferred_completion_time': preferred_completion_time,
                }
            else:
                operation_summary[operation_name]['quantity'] += work.quantity
                operation_summary[operation_name]['total_time'] += total_time

        operations_details = []
        for operation in operation_summary.values():
            average_time_per_unit = operation['total_time'] / operation['quantity'] if operation['quantity'] else 0
            efficiency = 100 if average_time_per_unit <= operation['preferred_completion_time'] else (operation['preferred_completion_time'] / average_time_per_unit) * 100
            total_units += operation['quantity']
            total_weighted_efficiency += efficiency * operation['quantity']

            operations_details.append({
                'operation': operation['operation'],
                'quantity': operation['quantity'],
                'average_time_per_unit': average_time_per_unit,
                'preferred_completion_time': operation['preferred_completion_time']
            })

        overall_efficiency = total_weighted_efficiency / total_units if total_units else 100

        # Summarize units produced by day
        units_by_day = {}
        for work in assigned_works:
            date = work.start_time.date() if work.start_time else None
            if date:
                if date not in units_by_day:
                    units_by_day[date] = work.quantity
                else:
                    units_by_day[date] += work.quantity

        units_over_time = [{'date': date, 'units': units} for date, units in sorted(units_by_day.items())]

        # Calculate total defects
        total_defects = ErrorResponsibility.objects.filter(employee=employee).count()

        response_data = {
            'id': employee.id,
            'full_name': f"{employee.user.first_name} {employee.user.last_name}",
            'username': employee.user.username,
            'earnings': earnings,
            'efficiency': overall_efficiency,
            'operations': operations_details,
            'total_defects': total_defects,
            'units_over_time': units_over_time,
        }

        return JsonResponse(response_data)

    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Employee not found'}, status=404)
    
@login_required
@admin_required
def order_api(request, order_id):
    try:
        order = Order.objects.get(pk=order_id)
        # Calculate the production cost per piece
        production_cost_per_piece = order.model.operations.aggregate(
            total_cost=Sum('payment')
        )['total_cost'] or 0

        passports_data = [
            {
                'passport_id': passport.id,
                'size_range': f"{passport.passport_sizes.first().size_quantity.size} - {passport.passport_sizes.last().size_quantity.size}",
                'rolls': [
                    {
                        'roll_name': pr.roll.name,
                        'meters': pr.meters
                    } for pr in passport.passport_rolls.all()
                ]
            } for passport in order.passports.all()
        ]
        response_data = {
            'model_name': order.model.name,
            'quantity': order.quantity,
            'price_per_piece': float(order.payment),
            'production_cost_per_piece': float(production_cost_per_piece),
            'status': order.get_status_display(),
            'assortment': order.assortment.name if order.assortment else 'N/A',
            'color': order.color,
            'passports': passports_data
        }

        return JsonResponse(response_data)

    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)
    
@login_required
@admin_required
def roll_api(request, roll_id):
    try:
        roll = Roll.objects.get(pk=roll_id)
        passport_rolls_data = [
            {
                'passport_id': passport_roll.passport.id,
                'meters_used': float(passport_roll.meters),
                'passport_details': {
                    'date': passport_roll.passport.date,
                    'is_completed': passport_roll.passport.is_completed,
                    'order': passport_roll.passport.order.model.name if passport_roll.passport.order else None
                }
            } for passport_roll in roll.passport_rolls.all()
        ]
        
        data = {
            'name': roll.name,
            'color': roll.color,
            'fabrics': roll.fabrics,
            'meters': float(roll.meters),
            'used_meters': float(roll.used_meters),
            'available_meters': float(roll.available_meters),
            'passports_used': passport_rolls_data
        }
        
        return JsonResponse(data)

    except Roll.DoesNotExist:
        return JsonResponse({'error': 'Roll not found'}, status=404)