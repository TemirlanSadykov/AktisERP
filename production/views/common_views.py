from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from ..models import EmployeeAttendance, UserProfile
from django.http import JsonResponse
import json
from geopy.distance import geodesic



@login_required
def user_redirect(request):
    user_profile = request.user.userprofile
    if user_profile.type == UserProfile.ADMIN:
        return redirect('admin_page')
    elif user_profile.type == UserProfile.TECHNOLOGIST:
        return redirect('technologist_page')
    elif user_profile.type == UserProfile.EMPLOYEE:
        return redirect('employee_page')
    elif user_profile.type == UserProfile.CUTTER:
        return redirect('cutter_page')
    elif user_profile.type == UserProfile.QC:
        return redirect('qc_page')
    elif user_profile.type == UserProfile.PACKER:
        return redirect('packer_page')
    else:
        return redirect('index')

# Set the workplace location
WORKPLACE_LAT = 35.38360653021277     # Example latitude
WORKPLACE_LON = 139.44952893343785  # Example longitude
ALLOWED_RADIUS = 200  # 100 meters radius

@login_required
@require_POST
def clock_in_out(request):
    user_profile = request.user.userprofile

    # Parse the JSON data sent from the frontend
    data = json.loads(request.body)
    fingerprint = data.get('fingerprint')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if not latitude or not longitude:
        return JsonResponse({'error': 'Location not provided'}, status=400)

    # Calculate distance from the workplace
    employee_location = (latitude, longitude)
    workplace_location = (WORKPLACE_LAT, WORKPLACE_LON)
    distance = geodesic(employee_location, workplace_location).meters

    if distance > ALLOWED_RADIUS:
        return JsonResponse({
            'error': 'You are outside the allowed clock-in area',
            'distance': distance,
        }, status=400)

    # Proceed with clock-in/out
    user_profile.status = not user_profile.status
    user_profile.save()

    return JsonResponse({
        'error': 'Clock-in/out successful',
        'distance': distance
    })