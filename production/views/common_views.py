from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from ..models import UserProfile
from django.http import JsonResponse
import json
from geopy.distance import geodesic
from django.conf import settings


@login_required
def user_redirect(request):
    user_profile = request.user.userprofile
    if user_profile.type == UserProfile.ADMIN:
        return redirect('admin_page')
    elif user_profile.type == UserProfile.TECHNOLOGIST:
        return redirect('client_order_list')
    elif user_profile.type == UserProfile.EMPLOYEE:
        return redirect('employee_page')
    elif user_profile.type == UserProfile.CUTTER:
        return redirect('client_order_list_cutter')
    elif user_profile.type == UserProfile.QC:
        return redirect('client_order_list_qc')
    elif user_profile.type == UserProfile.PACKER:
        return redirect('client_order_list_packer')
    elif user_profile.type == UserProfile.KEEPER:
        return redirect('keeper_page')
    else:
        return redirect('index')