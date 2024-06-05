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