from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

class HandleCSRFMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except PermissionDenied:
            return redirect('login')
        return response