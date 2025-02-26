from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from .models import set_current_company

class HandleCSRFMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except PermissionDenied:
            return redirect('login')
        return response
    
class SessionExpiredMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not request.user.is_authenticated:
            if request.path != reverse('login'):  # Assuming 'login' is the name of your login URL
                return redirect('login')
            
class CompanyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Set the company context from the user’s profile (if authenticated)
        if request.user.is_authenticated:
            # Adjust this as necessary for your project structure
            company = getattr(request.user, 'userprofile', None) and request.user.userprofile.company
            set_current_company(company)
        else:
            set_current_company(None)
        response = self.get_response(request)
        return response