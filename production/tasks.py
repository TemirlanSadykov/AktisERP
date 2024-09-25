from django.http import JsonResponse
from django.utils import timezone

from production.models import *
from twilio.rest import Client
import os
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
from dotenv import load_dotenv

load_dotenv()
                                                                          
def send_whatsapp_message(data):
    if not data:
        logger.warning("No data passed to send_whatsapp_message")
        return
    
    account_sid = os.getenv('account_sid')
    auth_token =os.getenv('auth_token')

    if not account_sid or not auth_token:
        logger.error("Twilio credentials are missing.")
        return

    client = Client(account_sid, auth_token)
    twilio_number = os.getenv('twilio_number')
    all_numbers = list(PhoneNumberScaner.objects.values_list('phone_number', flat=True).distinct())
    recipient_numbers = [number if number.startswith('+') else f'+{number}' for number in all_numbers]
    recipient_number = recipient_numbers
    message_body = "1 day to ship:\n\n"
    
    for order in data:
        message_body += f"Order Number: {order['order_number']}\nEND DATE: {order['term']}\nClient: {order['client__name']}\n\n"
    for number in recipient_number:
        try:
            message = client.messages.create(
                from_=twilio_number,
                body=message_body,
                to=f'whatsapp:{number}'
            )
        except Exception as e:
            logger.error(f"Failed to send message to {recipient_number}: {str(e)}")

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
        logger.info("Message sending on Whatsapp")
        send_whatsapp_message(data)
        logger.info("Message sent on Whatsapp")
    return JsonResponse(data, safe=False, json_dumps_params={'indent': 2})

