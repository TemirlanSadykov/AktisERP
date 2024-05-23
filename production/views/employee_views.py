from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from ..decorators import employee_required
from ..models import Work, AssignedWork, ReassignedWork
from django.utils import timezone
from django.views.decorators.http import require_POST
from datetime import datetime
from django.db import transaction

@login_required
@employee_required
def employee_page(request):
    return render(request, 'employee_page.html')

@login_required
@employee_required
def done_works_list(request):
    user_profile = request.user.userprofile
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    assigned_works = AssignedWork.objects.filter(employee=user_profile, end_time__isnull=False).select_related('work', 'work__operation', 'work__passport_size')
    if start_date:
        assigned_works = assigned_works.filter(end_time__date__gte=datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        assigned_works = assigned_works.filter(end_time__date__lte=datetime.strptime(end_date, '%Y-%m-%d').date())
    return render(request, 'employee/works/done_list.html', {'assigned_works': assigned_works, 'start_date': start_date, 'end_date': end_date})

@login_required
@employee_required
def pending_works_list(request):
    user_profile = request.user.userprofile
    assigned_works = AssignedWork.objects.filter(employee=user_profile, end_time__isnull=True).select_related('work', 'work__operation', 'work__passport_size')
    return render(request, 'employee/works/pending_list.html', {'assigned_works': assigned_works})

@login_required
@employee_required
def reassigned_works_list(request):
    user_profile = request.user.userprofile

    if request.method == 'POST':
        reassigned_work_id = request.POST.get('reassigned_work_id')
        reassigned_work = get_object_or_404(ReassignedWork, id=reassigned_work_id, new_employee=user_profile)
        
        with transaction.atomic():
            reassigned_work.is_completed = True
            reassigned_work.save()
            return redirect('reassigned_works_list')

    reassigned_works = ReassignedWork.objects.filter(
        new_employee=user_profile, 
        is_completed=False
    ).select_related('original_assigned_work__work', 'original_assigned_work__work__operation')

    return render(request, 'employee/works/reassigned_list.html', {'reassigned_works': reassigned_works})

@login_required
@employee_required
@require_POST
def start_work(request, assigned_work_id):
    assigned_work = get_object_or_404(AssignedWork, id=assigned_work_id, employee=request.user.userprofile)
    if assigned_work.start_time is None:
        assigned_work.start_time = timezone.now()
        assigned_work.save()
    return redirect('pending_works_list') 

@login_required
@employee_required
@require_POST
def finish_work(request, assigned_work_id):
    assigned_work = get_object_or_404(AssignedWork, id=assigned_work_id, employee=request.user.userprofile)
    if assigned_work.start_time is not None and assigned_work.end_time is None:
        assigned_work.end_time = timezone.now()
        assigned_work.save()
    return redirect('pending_works_list')
