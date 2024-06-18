from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

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