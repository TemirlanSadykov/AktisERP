from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from ..models import EmployeeAttendance, UserProfile
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

# @login_required
# @require_POST
# def clock_in_out(request):
#     user_profile = request.user.userprofile

#     # Parse the JSON data sent from the frontend
#     data = json.loads(request.body)
#     fingerprint = data.get('fingerprint')
#     latitude = data.get('latitude')
#     longitude = data.get('longitude')

#     if not latitude or not longitude:
#         return JsonResponse({'error': 'Location not provided'}, status=400)

#     # Calculate distance from the workplace
#     employee_location = (latitude, longitude)
#     workplace_location = (user_profile.branch.latitude, user_profile.branch.longitude)
#     distance = geodesic(employee_location, workplace_location).meters

#     # Update fingerprint if not already present in the user profile
#     if not user_profile.fingerprint:
#         user_profile.fingerprint = fingerprint
#         user_profile.save()

#     # Proceed with clock-in/out regardless of the distance
#     user_profile.status = not user_profile.status
#     user_profile.save()

#     # Save attendance data with the distance and fingerprint
#     EmployeeAttendance.objects.create(
#         employee=user_profile,
#         is_clock_in=user_profile.status,
#         branch=user_profile.branch,
#         fingerprint=fingerprint,
#         distance=distance,  # Store the calculated distance
#         latitude=latitude,
#         longitude=longitude
#     )

#     # Respond with success message and the recorded distance
#     return JsonResponse({ 'success': 'Clock-in/out successful' })