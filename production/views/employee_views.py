from datetime import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.db import transaction
from django.views.decorators.cache import cache_page
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from ..decorators import employee_required
from ..models import AssignedWork

CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@employee_required
def employee_page(request):
    user_profile = request.user.userprofile
    assigned_works = AssignedWork.objects.filter(employee=user_profile, is_success=False, created_at__gt=datetime(2025, 2, 7)).select_related('work', 'work__operation', 'work__passport_size')
    return render(request, 'employee/works/list.html', {'assigned_works': assigned_works, 'sidebar_type' : 'emp'})

@login_required
@employee_required
@require_POST
def complete_work(request, id):
    assigned_work = get_object_or_404(
        AssignedWork,
        id=id,
        employee=request.user.userprofile
    )
    assigned_work.is_success = True
    assigned_work.save(update_fields=["is_success"])
    return JsonResponse({"status": "success"})

