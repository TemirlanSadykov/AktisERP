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
WORKPLACE_LAT = settings.WORKPLACE_LAT
WORKPLACE_LON = settings.WORKPLACE_LON
ALLOWED_RADIUS = settings.ALLOWED_RADIUS

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

    # Update fingerprint if not already present in the user profile
    if not user_profile.fingerprint:
        user_profile.fingerprint = fingerprint
        user_profile.save()

    # Proceed with clock-in/out regardless of the distance
    user_profile.status = not user_profile.status
    user_profile.save()

    # Save attendance data with the distance and fingerprint
    EmployeeAttendance.objects.create(
        employee=user_profile,
        is_clock_in=user_profile.status,
        branch=user_profile.branch,
        fingerprint=fingerprint,
        distance=distance  # Store the calculated distance
    )

    # Respond with success message and the recorded distance
    return JsonResponse({ 'success': 'Clock-in/out successful' })