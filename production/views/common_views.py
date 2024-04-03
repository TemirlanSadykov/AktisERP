from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from ..models import UserProfile
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from ..models import EmployeeAttendance

@login_required
def user_redirect(request):
    user_profile = request.user.userprofile
    if user_profile.type == UserProfile.ADMIN:
        return redirect('admin_page')
    elif user_profile.type == UserProfile.TECHNOLOGIST:
        return redirect('technologist_page')
    elif user_profile.type == UserProfile.EMPLOYEE:
        return redirect('employee_page')
    else:
        return redirect('index')

@login_required
@require_POST
def clock_in_out(request):
    user_profile = request.user.userprofile
    user_profile.status = not user_profile.status
    user_profile.save()

    EmployeeAttendance.objects.create(employee=request.user.userprofile, is_clock_in=user_profile.status)

    return redirect('user_redirect')