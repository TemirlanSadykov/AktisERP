from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views import View
from ..models import *


class WhatsAppQRCodeView(TemplateView):
    template_name = 'whatsapp_qrcode.html'

    def get_context_data(self, **kwargs):
        context = super(WhatsAppQRCodeView, self).get_context_data(**kwargs)
        return context
    

class MobileNumberSubmitView(View):

    def post(self, request, *args, **kwargs):
        phone_number = request.POST.get('phone_number')    
        country_code = request.POST.get('country_code')   
        mobile_number=f"{country_code}{phone_number}"
        if mobile_number:
            if PhoneNumberScaner.objects.filter(phone_number=mobile_number).exists():
                return JsonResponse({'success': False, 'message': 'Number already exists'}, status=400)
            else:
                PhoneNumberScaner.objects.create(phone_number=mobile_number)
                return JsonResponse({'success': True, 'message': 'Number successfully verified'})
        else:
            return JsonResponse({'success': False, 'message': 'Invalid number'}, status=400)
        

