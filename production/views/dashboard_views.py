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