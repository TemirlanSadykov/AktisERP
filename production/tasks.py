from django.http import JsonResponse
from django.utils import timezone

from production.models import *
from twilio.rest import Client
import os
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)



def send_whatsapp_message(data):
    if not data:
        print("No data passed to send_whatsapp_message")
        return
    logger.info('HERE..............')
    
    account_sid = os.getenv("account_sid")
    auth_token = os.getenv("auth_token")

    if not account_sid or not auth_token:
        print("Twilio credentials are missing.")
        return

    client = Client(account_sid, auth_token)
    twilio_number = os.getenv("twilio_number")
    recipient_number = os.getenv("recipient_numbers")
    message_body = "1 day to ship:\n\n"

    for order in data:
        message_body += f"Order Number: {order['order_number']}\nEND DATE: {order['term']}\nClient: {order['client__name']}\n\n"

    try:
        message = client.messages.create(
            from_=twilio_number,
            body=message_body,
            to=f'whatsapp:{recipient_number}'
        )
        print(f"Message sent to {number}, SID: {message.sid}")
    except Exception as e:
        print(f"Failed to send message to {number}: {str(e)}")


def call_api():
    today = timezone.localdate()
    client_orders = ClientOrder.objects.filter(term__gte=today)
    filtered_orders = []

    for order in client_orders:
        if (order.term - today).days == 1:
            filtered_orders.append(order.id)
    client_order_details = ClientOrder.objects.filter(id__in=filtered_orders).values('order_number', 'term', 'client__name')
    data = list(client_order_details)
    if data:
        print(data)
        # send_whatsapp_message(data)
    return JsonResponse(data, safe=False, json_dumps_params={'indent': 2})

