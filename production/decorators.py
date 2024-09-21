from django.http import HttpResponseForbidden
from functools import wraps
from django.shortcuts import redirect

from .models import UserProfile

def employee_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not hasattr(request.user, 'userprofile') or (request.user.userprofile.type != UserProfile.EMPLOYEE and request.user.userprofile.type != UserProfile.ADMIN):
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def technologist_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not hasattr(request.user, 'userprofile') or (request.user.userprofile.type != UserProfile.TECHNOLOGIST and request.user.userprofile.type != UserProfile.ADMIN):
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.type != UserProfile.ADMIN:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def cutter_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.type != UserProfile.CUTTER and request.user.userprofile.type != UserProfile.ADMIN:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def qc_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.type != UserProfile.QC and request.user.userprofile.type != UserProfile.ADMIN:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def packer_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.type != UserProfile.PACKER and request.user.userprofile.type != UserProfile.ADMIN:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def keeper_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.type != UserProfile.KEEPER and request.user.userprofile.type != UserProfile.ADMIN:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view