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
    print(employee_id)
    try:
        employee = UserProfile.objects.get(pk=employee_id)

        # Assuming you have some way to track earnings, here's a placeholder
        earnings = 0  # This should be replaced with actual earnings calculation logic

        # Placeholder for efficiency calculation
        efficiency = 0  # Replace with your actual efficiency calculation logic

        # Assuming you have a way to track operations and their details
        # operations_worked_on = AssignedWork.objects.filter(employee=employee, is_success=True)
        operations_details = 0
        # for work in operations_worked_on:
        #     operations_details.append({
        #         'operation': work.work.operation.name,
        #         'quantity': work.quantity,
        #         'date': DateFormat(work.start_time).format('Y-m-d') if work.start_time else None
        #     })

        # Placeholder for defects and discrepancies
        defects_discrepancies = 0  # Implement actual logic to calculate defects and discrepancies

        response_data = {
            'id': employee.id,
            'full_name': f"{employee.user.first_name} {employee.user.last_name}",
            'username': employee.user.username,
            'earnings': earnings,
            'efficiency': efficiency,
            'operations': operations_details,
            'defects_discrepancies': defects_discrepancies
        }
        print(response_data)

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