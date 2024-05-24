from django.http import HttpResponseForbidden
from functools import wraps
from .models import UserProfile
from django.core.exceptions import PermissionDenied
from django.middleware.csrf import CsrfViewMiddleware
from django.shortcuts import redirect
from functools import wraps

def employee_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        try:
            if not hasattr(request.user, 'userprofile') or (request.user.userprofile.type != UserProfile.EMPLOYEE and request.user.userprofile.type != UserProfile.ADMIN):
                return HttpResponseForbidden()
            return view_func(request, *args, **kwargs)
        except CsrfViewMiddleware:
            return redirect('login')
    return _wrapped_view

def technologist_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        try:
            if not hasattr(request.user, 'userprofile') or (request.user.userprofile.type != UserProfile.TECHNOLOGIST and request.user.userprofile.type != UserProfile.ADMIN):
                return HttpResponseForbidden()
            return view_func(request, *args, **kwargs)
        except CsrfViewMiddleware:
            return redirect('login')
    return _wrapped_view

def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        try:
            if not hasattr(request.user, 'userprofile') or request.user.userprofile.type != UserProfile.ADMIN:
                return HttpResponseForbidden()
            return view_func(request, *args, **kwargs)
        except CsrfViewMiddleware:
            return redirect('login')
    return _wrapped_view

def cutter_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        try:
            if not hasattr(request.user, 'userprofile') or request.user.userprofile.type != UserProfile.CUTTER and request.user.userprofile.type != UserProfile.ADMIN:
                return HttpResponseForbidden()
            return view_func(request, *args, **kwargs)
        except CsrfViewMiddleware:
            return redirect('login')
    return _wrapped_view

def qc_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        try:
            if not hasattr(request.user, 'userprofile') or request.user.userprofile.type != UserProfile.QC and request.user.userprofile.type != UserProfile.ADMIN:
                return HttpResponseForbidden()
            return view_func(request, *args, **kwargs)
        except CsrfViewMiddleware:
            return redirect('login')
    return _wrapped_view

def packer_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        try:
            if not hasattr(request.user, 'userprofile') or request.user.userprofile.type != UserProfile.PACKER and request.user.userprofile.type != UserProfile.ADMIN:
                return HttpResponseForbidden()
            return view_func(request, *args, **kwargs)
        except CsrfViewMiddleware:
            return redirect('login')
    return _wrapped_view