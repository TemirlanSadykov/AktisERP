from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, DeleteView, UpdateView
from django.views.generic.edit import CreateView
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.shortcuts import render
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from ..decorators import admin_required
from ..models import *
from ..forms import *
from ..mixins import *
from datetime import datetime
import pandas as pd
from django.http import HttpResponse
from django.views import View
from django.http import JsonResponse
import json
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.views.decorators.http import require_POST
from urllib.parse import urlencode
from django.db import transaction
from django.db.models import F, Window
from collections import defaultdict
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDay
import openpyxl
from django.db.models.functions import Lead
from decimal import Decimal

@login_required
@admin_required
def admin_page(request):
    branches = Branch.objects.all()
    context = {
        'branches': branches,
    }
    return render(request, 'admin_page.html', context)

@login_required
@admin_required
def dashboard_page(request):
    clients = Client.objects.all()
    client_data = []

    for client in clients:
        client_orders = ClientOrder.objects.filter(client=client)
        orders = Order.objects.filter(client_order__in=client_orders)
        
        total_ordered_amount_by_orders = orders.aggregate(total_amount=Sum(F('quantity') * F('payment')))['total_amount'] or 0
        total_ordered_amount = client_orders.aggregate(total_amount=Sum('orders__quantity'))['total_amount'] or 0
        
        client_orders_details = [
            (co.order_number, list(co.orders.values_list('model__name', flat=True)))
            for co in client_orders
        ]

        client_data.append({
            'client': client.name,
            'client_orders_details': client_orders_details,
            'total_ordered_amount_by_orders': total_ordered_amount_by_orders,
            'total_ordered_amount': total_ordered_amount
        })

    client_data = sorted(client_data, key=lambda x: x['total_ordered_amount'], reverse=True)

    return render(request, 'dashboard.html', {'client_data': client_data})

@method_decorator([login_required, admin_required], name='dispatch')
class BranchListView(ListView):
    model = Branch
    template_name = 'admin/branches/list.html'
    context_object_name = 'branches'
    paginate_by = 10

    def get_queryset(self):
        return Branch.objects.all().order_by('name')

@method_decorator([login_required, admin_required], name='dispatch')
class BranchCreateView(CreateView):
    model = Branch
    form_class = BranchForm
    template_name = 'admin/branches/create.html'
    success_url = reverse_lazy('branch_list')

@method_decorator([login_required, admin_required], name='dispatch')
class BranchDetailView(DetailView):
    model = Branch
    template_name = 'admin/branches/detail.html'
    context_object_name = 'branch'

@method_decorator([login_required, admin_required], name='dispatch')
class BranchUpdateView(UpdateView):
    model = Branch
    form_class = BranchForm
    template_name = 'admin/branches/edit.html'
    success_url = reverse_lazy('branch_list')

@method_decorator([login_required, admin_required], name='dispatch')
class BranchDeleteView(DeleteView):
    model = Branch
    template_name = 'admin/branches/delete.html'
    success_url = reverse_lazy('branch_list')

@login_required
@admin_required
def branch_switch(request):
    branch_id = request.POST.get('branch')
    
    try:
        new_branch = Branch.objects.get(id=branch_id)
        
        user_profile = UserProfile.objects.get(user=request.user)
        user_profile.branch = new_branch
        user_profile.save()
        
        messages.success(request, 'Branch switched successfully.')
        return redirect('admin_page')

    except Branch.DoesNotExist:
        messages.error(request, 'Selected branch does not exist.')
        return redirect('admin_page')

@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeListView(ListView):
    model = UserProfile
    template_name = 'admin/employees/list.html'
    context_object_name = 'employees'
    paginate_by = 10
    def get_queryset(self):
        return UserProfile.objects.filter(
            branch=self.request.user.userprofile.branch
        ).order_by('employee_id')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['upload_form'] = UploadFileForm()
        return context

@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeCreateView(AssignBranchForEmployeeMixin, CreateView):
    template_name = 'admin/employees/create.html'
    form_class = UserWithProfileForm
    success_url = reverse_lazy('employee_list')

@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeDetailView(DetailView):
    model = UserProfile
    template_name = 'admin/employees/detail.html'
    context_object_name = 'employee'

@login_required
@admin_required
def employee_edit(request, pk):
    user_profile = get_object_or_404(UserProfile, pk=pk, branch=request.user.userprofile.branch)
    user = user_profile.user

    if request.method == 'POST':
        user_form = UserEditForm(request.POST, instance=user)
        if user_form.is_valid():
            user_form.save()
            messages.success(request, 'Employee details updated successfully.')
            return redirect('employee_list')
    else:
        user_form = UserEditForm(instance=user)

    context = {'user_form': user_form, 'user_profile': user_profile}
    return render(request, 'admin/employees/edit.html', context)

@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeDeleteView(RestrictBranchMixin, DeleteView):
    model = UserProfile
    template_name = 'admin/employees/delete.html'
    success_url = reverse_lazy('employee_list')
    
@login_required
@admin_required
@require_POST
def employee_upload(request):
    form = UploadFileForm(request.POST, request.FILES)
    if form.is_valid():
        excel_file = request.FILES['excel_file']
        try:
            workbook = openpyxl.load_workbook(excel_file)
            sheet = workbook.active
            with transaction.atomic():
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    branch_id, first_name, last_name, username, employee_id, type, station, password = row
                    branch = Branch.objects.get(id=branch_id)
                    try:
                        # Attempt to find an existing UserProfile with given employee_id and branch
                        profile = UserProfile.objects.get(employee_id=employee_id, branch=branch)
                        
                    except UserProfile.DoesNotExist:
                        # If it does not exist, create User and UserProfile
                        user = User.objects.create(username=username, first_name=first_name, last_name=last_name)
                        user.set_password(password)
                        user.save()
                        profile = UserProfile.objects.create(
                            user=user, 
                            branch=branch, 
                            employee_id=employee_id, 
                            type=type, 
                            station=station, 
                            status=False
                        )
                    else:
                        # If UserProfile exists, update both User and UserProfile
                        user = profile.user
                        user.first_name = first_name
                        user.last_name = last_name
                        user.username = username
                        user.set_password(password)
                        user.save()
                        
                        profile.type = type
                        profile.station = station
                        profile.save()

            messages.success(request, 'Employees uploaded successfully.')
            return redirect(reverse_lazy('employee_list'))
        except Exception as e:
            messages.error(request, f'Error processing the file: {e}')
            return redirect(reverse_lazy('employee_list'))
        finally:
            workbook.close()
    else:
        messages.error(request, 'Invalid file format.')
        return redirect(reverse_lazy('employee_list'))

@login_required
@admin_required
def passport_detail_admin(request, pk):
    passport = get_object_or_404(Passport, pk=pk)
    operations = passport.order.model.operations.all() 
    size_quantities = PassportSize.objects.filter(passport=passport).order_by('size_quantity__size')
    passport_rolls = PassportRoll.objects.filter(passport=passport)

    work_by_op_and_size = {}
    for assigned_work in AssignedWork.objects.filter(work__passport=passport).select_related('employee', 'work__operation', 'work__passport_size'):
        # Key as a tuple of operation_id and passport_size_id
        key = (assigned_work.work.operation_id, assigned_work.work.passport_size_id)
        if key not in work_by_op_and_size:
            work_by_op_and_size[key] = [assigned_work]
        else:
            work_by_op_and_size[key].append(assigned_work)

    return render(request, 'admin/passports/detail.html', {
        'passport': passport,
        'passport_rolls': passport_rolls,
        'operations': operations,
        'size_quantities': size_quantities,
        'work_by_op_and_size': work_by_op_and_size
    })

@login_required
@admin_required
def salary_list(request):
    form = SalaryListForm(request.GET or None)
    salaries = {}

    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        salary_type = form.cleaned_data['salary_type']

        if salary_type == 'non_fixed':
            assigned_works = AssignedWork.objects.filter(
                end_time__range=(start_date, end_date),
                end_time__isnull=False,
                is_success=True,
                work__passport__order__client_order__branch=request.user.userprofile.branch
            ).select_related('work__operation', 'employee')

            reassigned_works = ReassignedWork.objects.filter(
                original_assigned_work__end_time__range=(start_date, end_date),
                is_success=True,
                original_assigned_work__work__passport__order__client_order__branch=request.user.userprofile.branch
            ).select_related('original_assigned_work__work__operation', 'new_employee')

            for work_group in [assigned_works, reassigned_works]:
                for work in work_group:
                    if work_group is assigned_works:
                        employee = work.employee
                        payment = work.work.operation.payment
                        quantity = work.quantity
                    else:  # This is for reassigned_works
                        employee = work.new_employee
                        payment = work.original_assigned_work.work.operation.payment
                        quantity = work.reassigned_quantity

                    if employee not in salaries:
                        salaries[employee] = {'salary': 0, 'status': 0, 'errors': 0, 'error_cost': 0}
                    
                    salaries[employee]['salary'] += payment * quantity
                    salaries[employee]['status'] = 1 if work.payment_date else 0

                    if employee.type not in [UserProfile.ADMIN, UserProfile.TECHNOLOGIST]:
                        error_responsibilities = ErrorResponsibility.objects.filter(
                            employee=employee,
                            error__reported_date__range=(start_date, end_date)
                        )
                        for responsibility in error_responsibilities:
                            salaries[employee]['error_cost'] += responsibility.error.cost * (responsibility.percentage / 100)

        elif salary_type == 'fixed':
            fixed_salaries = FixedSalary.objects.filter(branch=request.user.userprofile.branch)
            for fixed_salary in fixed_salaries:
                for employee in fixed_salary.employees.all():
                    timestamps = EmployeeAttendance.objects.filter(
                        employee=employee,
                        timestamp__range=(start_date, end_date)
                    ).order_by('timestamp').annotate(
                        next_timestamp=Window(
                            expression=Lead('timestamp'),
                            order_by=F('timestamp').asc(),
                            partition_by=[F('employee')]
                        )
                    )

                    total_salary = 0
                    for attendance in timestamps:
                        if attendance.is_clock_in and attendance.next_timestamp:
                            if (attendance.next_timestamp - attendance.timestamp).total_seconds() <= 86400:
                                total_salary += fixed_salary.salary

                    if total_salary > 0:
                        if employee not in salaries:
                            salaries[employee] = {'salary': total_salary, 'status': 0, 'errors': 0, 'error_cost': 0}

                        error_responsibilities = ErrorResponsibility.objects.filter(
                            employee=employee,
                            error__reported_date__range=(start_date, end_date)
                        )
                        for responsibility in error_responsibilities:
                            salaries[employee]['error_cost'] += responsibility.error.cost * (responsibility.percentage / 100)

                        payment_exists = SalaryPayment.objects.filter(
                            employee=employee,
                            fixed_salary=fixed_salary,
                            payment_date__range=(start_date, end_date)
                        ).exists()
                        
                        salaries[employee]['status'] = 1 if payment_exists else 0

    context = {'form': form, 'salaries': {k: v for k, v in salaries.items() if v['salary'] > 0}}
    return render(request, 'admin/salaries/list.html', context)

@login_required
@admin_required
@require_POST
def process_payments(request):
    form = SalaryListForm(request.POST)
    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        salary_type = form.cleaned_data['salary_type']

        if salary_type == 'non_fixed':
            # Process Non-Fixed Salary Payments (Existing logic)
            assigned_works = AssignedWork.objects.filter(
                end_time__range=(start_date, end_date),
                work__passport__order__client_order__branch=request.user.userprofile.branch
            )

            reassigned_works = ReassignedWork.objects.filter(
                original_assigned_work__end_time__range=(start_date, end_date),
                original_assigned_work__work__passport__order__client_order__branch=request.user.userprofile.branch
            )

            for work in assigned_works:
                work.payment_date = timezone.now()
                work.save()

            for work in reassigned_works:
                work.payment_date = timezone.now()
                work.save()

        elif salary_type == 'fixed':
            fixed_salaries = FixedSalary.objects.filter(
                branch=request.user.userprofile.branch
            ).prefetch_related('employees')

            for fixed_salary in fixed_salaries:
                for employee in fixed_salary.employees.all():
                    attendances = EmployeeAttendance.objects.filter(
                        employee=employee,
                        timestamp__range=(start_date, end_date)
                    ).order_by('timestamp').annotate(
                        next_timestamp=Window(
                            expression=Lead('timestamp'),
                            order_by=F('timestamp').asc(),
                            partition_by=[F('employee')]
                        )
                    )

                    days_processed = set()
                    for attendance in attendances:
                        if attendance.is_clock_in and attendance.next_timestamp:
                            # Check for valid clock-out within 24 hours to accommodate overnight shifts
                            clock_in_local = timezone.localtime(attendance.timestamp)
                            clock_out_local = timezone.localtime(attendance.next_timestamp)
                            if (clock_out_local - clock_in_local).total_seconds() <= 86400:
                                day_key = clock_in_local.date()
                                if day_key not in days_processed:
                                    days_processed.add(day_key)

                    days_with_complete_records = len(days_processed)

                    if days_with_complete_records > 0:
                        first_day_of_month = start_date.replace(day=1)
                        last_day_of_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

                        existing_payment = SalaryPayment.objects.filter(
                            employee=employee,
                            payment_date__range=(first_day_of_month, last_day_of_month)
                        ).exists()

                        if not existing_payment:
                            total_salary = days_with_complete_records * fixed_salary.salary
                            SalaryPayment.objects.create(
                                fixed_salary=fixed_salary,
                                employee=employee,
                                payment_date=timezone.now(),
                                amount=total_salary
                            )

        base_url = reverse('salary_list')
        query_string = urlencode({
            'start_date': start_date.strftime('%Y-%m-%d'), 
            'end_date': (end_date - timedelta(days=1)).strftime('%Y-%m-%d'),
            'salary_type': salary_type
        })
        url = f"{base_url}?{query_string}"
        return redirect(url)

    else:
        return redirect('salary_list')

@login_required
@admin_required
def salary_detail(request, pk):
    employee = get_object_or_404(UserProfile, pk=pk, branch=request.user.userprofile.branch)
    initial_data = {
        'start_date': request.GET.get('start_date'),
        'end_date': request.GET.get('end_date'),
        'salary_type': request.GET.get('salary_type', 'non_fixed') 
    }
    form = SalaryListForm(request.GET or None, initial=initial_data)
    assigned_work_details = []
    total_salary = 0
    error_details = []

    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        salary_type = form.cleaned_data['salary_type']

        if salary_type == 'non_fixed':
            assigned_works = AssignedWork.objects.filter(
                employee=employee,
                end_time__range=(start_date, end_date),
                is_success=True,
                work__passport__order__client_order__branch=request.user.userprofile.branch
            ).select_related('work__operation', 'work__passport_size__size_quantity')

            reassigned_works = ReassignedWork.objects.filter(
                new_employee=employee,
                original_assigned_work__end_time__range=(start_date, end_date),
                is_success=True,
                original_assigned_work__work__passport__order__client_order__branch=request.user.userprofile.branch
            ).select_related('original_assigned_work__work__operation', 'original_assigned_work__work__passport_size__size_quantity')

            for work in assigned_works:
                work_salary, work_details = calculate_salary_and_details(work)
                total_salary += work_salary
                assigned_work_details.append(work_details)

            for work in reassigned_works:
                work_salary, work_details = calculate_salary_and_details(work.original_assigned_work, reassigned_quantity=work.reassigned_quantity)
                total_salary += work_salary
                assigned_work_details.append(work_details)

            # Calculate errors only if the employee is of type EMPLOYEE
            if employee.type not in [UserProfile.ADMIN, UserProfile.TECHNOLOGIST]:
                error_details = calculate_errors(employee, start_date, end_date)
                total_error_cost = sum(detail['cost'] for detail in error_details)
                total_salary -= total_error_cost

        elif salary_type == 'fixed':
            fixed_salary = FixedSalary.objects.filter(employees=employee, branch=request.user.userprofile.branch).first()
            if fixed_salary:
                attendances = EmployeeAttendance.objects.filter(
                    employee=employee,
                    timestamp__range=(start_date, end_date)
                ).order_by('timestamp').annotate(
                    next_timestamp=Window(
                        expression=Lead('timestamp'),
                        order_by=F('timestamp').asc(),
                        partition_by=[F('employee')]
                    )
                )

                for attendance in attendances:
                    if attendance.is_clock_in and attendance.next_timestamp:
                        if (attendance.next_timestamp - attendance.timestamp).total_seconds() <= 86400:
                            clock_in_local = timezone.localtime(attendance.timestamp)
                            clock_out_local = timezone.localtime(attendance.next_timestamp)
                            duration = clock_out_local - clock_in_local
                            hours, remainder = divmod(duration.total_seconds(), 3600)
                            minutes = remainder // 60
                            total_salary += fixed_salary.salary
                            assigned_work_details.append({
                                'date': clock_in_local.date(),
                                'clock_in': clock_in_local,
                                'clock_out': clock_out_local,
                                'hours_worked': f"{int(hours)}h {int(minutes)}m",
                                'daily_salary': fixed_salary.salary
                            })

                # Calculate errors for all employees on fixed salary
                error_details = calculate_errors(employee, start_date, end_date)
                total_error_cost = sum(detail['cost'] for detail in error_details)
                total_salary -= total_error_cost

    context = {
        'form': form,
        'employee': employee,
        'works': assigned_work_details,
        'total_salary': total_salary,
        'errors': error_details
    }
    return render(request, 'admin/salaries/detail.html', context)

def calculate_errors(employee, start_date, end_date):
    error_responsibilities = ErrorResponsibility.objects.filter(
        employee=employee,
        error__reported_date__range=(start_date, end_date)
    ).select_related('error')

    error_details = [{
        'type': 'Дефект' if resp.error.error_type == Error.ErrorType.DEFECT else 'Несоответствие',
        'passport': resp.error.passport.id,
        'size': resp.error.size_quantity.size,
        'quantity': resp.error.quantity,
        'reported_date': resp.error.reported_date,
        'cost': resp.error.cost * (resp.percentage / 100)
    } for resp in error_responsibilities]

    return error_details

def calculate_salary_and_details(work, reassigned_quantity=None):
    """Helper function to calculate salary and details for a work or reassigned work."""
    quantity = reassigned_quantity if reassigned_quantity is not None else work.quantity
    work_salary = work.work.operation.payment * quantity
    time_spent = (work.end_time - work.start_time).total_seconds() if work.start_time and work.end_time else 0
    return work_salary, {
        'operation': work.work.operation,
        'size': work.work.passport_size.size_quantity.size,
        'quantity': quantity,
        'time_spent_seconds': time_spent,
        'work_salary': work_salary
    }

@login_required
@admin_required
def export_salaries_to_excel(request):
    form = SalaryListForm(request.GET or None)

    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        salary_type = form.cleaned_data['salary_type']
        data = []
        errors_data = []

        if salary_type == 'non_fixed':
            assigned_works = AssignedWork.objects.filter(
                end_time__range=(start_date, end_date),
                is_success=True
            ).select_related('work__operation', 'work__passport', 'work__passport__order', 'employee', 'work__passport_size')

            reassigned_works = ReassignedWork.objects.filter(
                original_assigned_work__end_time__range=(start_date, end_date),
                is_success=True
            ).select_related('original_assigned_work', 'new_employee', 'original_assigned_work__work__passport_size')

            for work in assigned_works:
                passport = work.work.passport
                passport_size = work.work.passport_size
                order = passport.order
                data.append([
                    datetime.now().date(), order.client_order.client.name, order.model.name if order.model else '',
                    order.assortment.name if order.assortment else '', passport.id, passport_size.size_quantity.size,
                    order.color, order.fabrics, passport.date, work.work.operation.id,
                    work.work.operation.name, work.work.operation.payment, work.employee.employee_id,
                    work.employee.user.get_full_name(), work.quantity,
                    work.work.operation.payment * work.quantity
                ])

            for work in reassigned_works:
                original = work.original_assigned_work
                passport = original.work.passport
                passport_size = original.work.passport_size
                order = passport.order
                data.append([
                    datetime.now().date(), order.client_order.client.name, order.model.name if order.model else '',
                    order.assortment.name if order.assortment else '', passport.id, passport_size.size_quantity.size,
                    order.color, order.fabrics, passport.date, original.work.operation.id,
                    original.work.operation.name, original.work.operation.payment, work.new_employee.employee_id,
                    work.new_employee.user.get_full_name(), work.reassigned_quantity,
                    original.work.operation.payment * work.reassigned_quantity
                ])

            salary_df = pd.DataFrame(data, columns=[
                "Today's date", "Client's name", "Model's name", "Assortment's name", "Passport id", 
                "Passport size", "Order's color", "Order's fabrics", "Passport date", "Operation id", 
                "Operation name", "Operation payment", "ID", "Employee", 
                "Work's quantity", "Salary"
            ])

            employees = UserProfile.objects.filter(type=UserProfile.EMPLOYEE)

        elif salary_type == 'fixed':
            fixed_salaries = FixedSalary.objects.filter(
                branch=request.user.userprofile.branch
            ).prefetch_related('employees')

            for fixed_salary in fixed_salaries:
                for employee in fixed_salary.employees.all():
                    attendances = EmployeeAttendance.objects.filter(
                        employee=employee,
                        timestamp__range=(start_date, end_date)
                    ).order_by('timestamp').values_list('timestamp', flat=True)

                    paired_times = []
                    for i in range(0, len(attendances) - 1, 2):
                        if len(attendances) > i + 1:
                            clock_in = attendances[i]
                            clock_out = attendances[i + 1]
                            if clock_in < clock_out:
                                paired_times.append((clock_in, clock_out))

                    for clock_in, clock_out in paired_times:
                        clock_in_local = timezone.localtime(clock_in)
                        clock_out_local = timezone.localtime(clock_out)
                        duration = clock_out_local - clock_in_local
                        hours, remainder = divmod(duration.total_seconds(), 3600)
                        minutes = remainder // 60
                        data.append([
                            employee.user.get_full_name(),
                            employee.employee_id,
                            clock_in_local.date(),
                            clock_in_local.strftime('%H:%M:%S'),
                            clock_out_local.strftime('%H:%M:%S'),
                            f"{int(hours)}h {int(minutes)}m",
                            fixed_salary.salary
                        ])

            salary_df = pd.DataFrame(data, columns=[
                "Employee", "ID", "Date", "Clock in", "Clock out", "Hours worked", "Salary per day"
            ])

            employees = UserProfile.objects.all()

        # Process errors for selected employees
        for employee in employees:
            error_responsibilities = ErrorResponsibility.objects.filter(
                employee=employee,
                error__reported_date__range=(start_date, end_date)
            ).select_related('error')

            for responsibility in error_responsibilities:
                errors_data.append([
                    responsibility.error.passport.order.model.name,
                    responsibility.error.passport.id,
                    responsibility.error.size_quantity.size,
                    employee.user.get_full_name(),
                    employee.employee_id,
                    'Defect' if responsibility.error.error_type == Error.ErrorType.DEFECT else 'Discrepancy',
                    responsibility.error.reported_date.strftime('%Y-%m-%d'),
                    responsibility.error.cost * (responsibility.percentage / 100)
                ])

        errors_df = pd.DataFrame(errors_data, columns=[
            "Model", "Passport ID", "Size", "Employee", "ID", "Error Type", "Reported Date", "Error Cost"
        ])

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="salaries.xlsx"'
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            salary_df.to_excel(writer, sheet_name='Salaries', index=False)
            errors_df.to_excel(writer, sheet_name='Errors', index=False)  # Writing errors to a separate sheet
        
        return response

    # Handle form errors or initial page access
    context = {'form': form}
    return render(request, 'blank.html', context)



@login_required
@admin_required
def attendance_list(request):
    form = DateForm()
    attendances = None

    if request.method == 'POST':
        form = DateForm(request.POST)
        if form.is_valid():
            selected_date = form.cleaned_data['date']
            next_day = selected_date + timedelta(days=1)
            
            attendances = EmployeeAttendance.objects.filter(
                timestamp__range=(selected_date, next_day),
                is_clock_in=True,
                branch=request.user.userprofile.branch 
            ).distinct('employee')

    context = {
        'form': form,
        'attendances': attendances,
    }
    return render(request, 'admin/attendances/list.html', context)






@method_decorator([login_required, admin_required], name='dispatch')
class ClientOrderListView(RestrictBranchMixin, ListView):
    model = ClientOrder
    template_name = 'admin/client/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 10
    form_class = DateRangeForm 

    def get_queryset(self):
        queryset = super().get_queryset().order_by('term')
        status = self.request.GET.get('status', None)
        form = self.form_class(self.request.GET)

        if status:
            try:
                status = int(status)
                if status in dict(self.model.TYPE_CHOICES):
                    queryset = queryset.filter(status=status)
            except ValueError:
                pass

        if form.is_valid():
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')

            if start_date and end_date:
                queryset = queryset.filter(created_at__date__range=[start_date, end_date])
            elif start_date:
                queryset = queryset.filter(created_at__date__gte=start_date)
            elif end_date:
                queryset = queryset.filter(created_at__date__lte=end_date)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form_class(self.request.GET or None) 
        today = timezone.localdate()
        orders_with_days_left = []
        for order in context['orders']:
            days_left = (order.term - today).days
            orders_with_days_left.append({'order': order, 'days_left': days_left})

        context['orders_with_days_left'] = sorted(orders_with_days_left, key=lambda x: x['days_left'])
        context['selected_status'] = self.request.GET.get('status', '')
        context['ClientOrder'] = ClientOrder 
        return context
    
@method_decorator([login_required, admin_required], name='dispatch')
class ClientOrderCreateView(CreateView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'admin/client/orders/create.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.branch = self.request.user.userprofile.branch
        self.object.save()
        form.save_m2m()
        redirect_url = reverse('client_order_detail', kwargs={'pk': self.object.pk})
        return HttpResponseRedirect(redirect_url)


@method_decorator([login_required, admin_required], name='dispatch')
class ClientOrderDetailView(DetailView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'admin/client/orders/detail.html'
    context_object_name = 'client_order'

    def get_context_data(self, **kwargs):
        context = super(ClientOrderDetailView, self).get_context_data(**kwargs)
        client_order = context['client_order']
        context['orders'] = client_order.orders.all()
        today = timezone.localdate()
        if client_order.term >= today:
            days_left = (client_order.term - today).days
        else:
            days_left = 0
        context['days_left'] = days_left
        return context

@method_decorator([login_required, admin_required], name='dispatch')
class ClientOrderUpdateView(RestrictBranchMixin, UpdateView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'admin/client/orders/edit.html'

    def get_success_url(self):
        return reverse('client_order_detail', kwargs={'pk': self.object.pk})

@method_decorator([login_required, admin_required], name='dispatch')
class ClientOrderDeleteView(RestrictBranchMixin, DeleteView):
    model = ClientOrder
    template_name = 'admin/client/orders/delete.html'
    success_url = reverse_lazy('client_order_list')

@login_required
@admin_required
@require_POST
def client_order_complete(request, pk):
    client_order = get_object_or_404(ClientOrder, pk=pk)
    if client_order.status != ClientOrder.COMPLETED:
    # Retrieve all orders linked to this client order
        orders = Order.objects.filter(client_order=client_order)

        # Begin a transaction to ensure all or nothing is saved
        with transaction.atomic():
            for order in orders:
                # Retrieve all passports linked to each order
                passports = Passport.objects.filter(order=order)
                for passport in passports:
                    # Retrieve all passport sizes linked to each passport
                    passport_sizes = PassportSize.objects.filter(passport=passport)
                    for passport_size in passport_sizes:
                        # Assume operations need to be created for QC and Packing stages
                        operations = Operation.objects.filter(node__type=Node.QC)
                        for operation in operations:
                            # Create work for each operation
                            work = Work.objects.create(
                                operation=operation,
                                passport=passport,
                                passport_size=passport_size
                            )
                            # Create assigned work assuming quantity and success need handling
                            AssignedWork.objects.create(
                                work=work,
                                employee=operation.employee,
                                quantity=passport_size.quantity,
                                start_time=timezone.now(),
                                end_time=timezone.now(),
                                is_success=True  # Assuming work is successful for demonstration
                            )

            # Set the client order status to completed
            client_order.status = ClientOrder.COMPLETED
            client_order.save()

    return redirect('client_order_list')





@method_decorator([login_required, admin_required], name='dispatch')
class OrderCreateView(CreateView):
    model = Order
    form_class = OrderForm
    template_name = 'admin/orders/create.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.client_order = get_object_or_404(ClientOrder, pk=self.kwargs['client_order_pk'])
        self.object.save()
        form.save_m2m()
        redirect_url = reverse('create_size_quantity', kwargs={'pk': self.object.id})
        return HttpResponseRedirect(redirect_url)

    def get_context_data(self, **kwargs):
        context = super(OrderCreateView, self).get_context_data(**kwargs)
        context['client_order_pk'] = self.kwargs.get('client_order_pk')
        return context

@method_decorator([login_required, admin_required], name='dispatch')
class OrderDetailView(DetailView):
    model = Order
    form_class = OrderForm
    template_name = 'admin/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super(OrderDetailView, self).get_context_data(**kwargs)
        order = context['order']
        passport = Passport.objects.filter(order=order).first()
        if passport:
            context['errors'] = Error.objects.filter(passport=passport).order_by('error_type')
        else:
            context['errors'] = Error.objects.none()
        context['passports'] = order.passports.all()
        context['size_quantities'] = order.size_quantities.all().order_by('size')
        context['size_quantity_form'] = SizeQuantityForm()
        today = timezone.localdate()
        if order.client_order.term >= today:
            days_left = (order.client_order.term - today).days
        else:
            days_left = 0
        context['days_left'] = days_left
        return context

@method_decorator([login_required, admin_required], name='dispatch')
class OrderUpdateView(UpdateView):
    model = Order
    form_class = OrderForm
    template_name = 'admin/orders/edit.html'
    def get_success_url(self):
        return reverse('order_detail', kwargs={'pk': self.object.pk})

@method_decorator([login_required, admin_required], name='dispatch')
class OrderDeleteView(DeleteView):
    model = Order
    template_name = 'admin/orders/delete.html'
    def get_success_url(self):
        return reverse('client_order_detail', kwargs={'pk': self.object.client_order.pk})

@method_decorator([login_required, admin_required], name='dispatch')
class SizeQuantityCreateView(View):
    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = SizeQuantityForm()
        size_quantities = order.size_quantities.all()
        return render(request, 'admin/orders/create_size_quantity.html', {
            'form': form,
            'size_quantities': size_quantities,
            'order': order
        })
    def post(self, request, pk):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            form = SizeQuantityForm(request.POST)
            if form.is_valid():
                new_size_quantity = form.save(commit=False)
                new_size_quantity.save()
                order = get_object_or_404(Order, pk=pk)
                order.size_quantities.add(new_size_quantity)
                size_quantities = order.size_quantities.values('id', 'size', 'quantity')
                return JsonResponse({'success': True, 'sizeQuantities': list(size_quantities)})
            else:
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        return JsonResponse({'success': False, 'error': 'Non-AJAX request not allowed'}, status=400)
    
@login_required
@admin_required
def edit_size_quantity(request, sq_id):
    size_quantity = get_object_or_404(SizeQuantity, id=sq_id)

    if request.method == 'POST':
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        form = SizeQuantityForm(data, instance=size_quantity)
        if form.is_valid():
            form.save()
            return JsonResponse({'status': 'success'}, status=200)
    
    return JsonResponse({'status': 'error'}, status=400)

@login_required
@admin_required
def delete_size_quantity(request, sq_id):
    if request.method == 'POST':
        size_quantity = get_object_or_404(SizeQuantity, id=sq_id)
        size_quantity.delete()
        return JsonResponse({'status': 'success'}, status=200)
    return JsonResponse({'status': 'error'}, status=400)


@method_decorator([login_required, admin_required], name='dispatch')
class ClientListView(ListView):
    model = Client
    template_name = 'admin/clients/list.html'
    context_object_name = 'clients'
    paginate_by = 10
    def get_queryset(self):
        return Client.objects.all().order_by('name')

@method_decorator([login_required, admin_required], name='dispatch')
class ClientCreateView(CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'admin/clients/create.html'
    success_url = reverse_lazy('client_list')

@method_decorator([login_required, admin_required], name='dispatch')
class ClientDetailView(DetailView):
    model = Client
    template_name = 'admin/clients/detail.html'
    context_object_name = 'client'

@method_decorator([login_required, admin_required], name='dispatch')
class ClientUpdateView(UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'admin/clients/edit.html'
    def get_success_url(self):
        return reverse('client_detail', kwargs={'pk': self.object.pk})

@method_decorator([login_required, admin_required], name='dispatch')
class ClientDeleteView(DeleteView):
    model = Client
    template_name = 'admin/clients/delete.html'
    success_url = reverse_lazy('client_list')



@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryListView(RestrictBranchMixin, ListView):
    model = FixedSalary
    template_name = 'admin/fixed_salaries/list.html'
    context_object_name = 'fixed_salaries'
    paginate_by = 10
    def get_queryset(self):
        return FixedSalary.objects.all().order_by('position')

@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryCreateView(AssignBranchMixin, CreateView):
    model = FixedSalary
    form_class = FixedSalaryForm
    template_name = 'admin/fixed_salaries/create.html'
    success_url = reverse_lazy('fixed_salary_list')

@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryDetailView(DetailView):
    model = FixedSalary
    template_name = 'admin/fixed_salaries/detail.html'
    context_object_name = 'fixed_salary'

@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryUpdateView(RestrictBranchMixin, UpdateView):
    model = FixedSalary
    form_class = FixedSalaryForm
    template_name = 'admin/fixed_salaries/edit.html'
    success_url = reverse_lazy('fixed_salary_list')

@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryDeleteView(RestrictBranchMixin, DeleteView):
    model = FixedSalary
    template_name = 'admin/fixed_salaries/delete.html'
    success_url = reverse_lazy('fixed_salary_list')



@method_decorator([login_required, admin_required], name='dispatch')
class ErrorDetailAdminView(CreateView):
    model = ErrorResponsibility
    form_class = ErrorResponsibilityForm
    template_name = 'admin/errors/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        error = get_object_or_404(Error, pk=self.kwargs.get('pk'))
        context['error'] = error
        context['responsibility_errors'] = ErrorResponsibility.objects.filter(error=error)
        return context

    def form_valid(self, form):
        responsibility = form.save(commit=False)
        error_id = self.kwargs['pk']
        responsibility.error_id = error_id
        responsibility.save()
        return redirect('error_detail_admin', pk=error_id)
    
    def get_success_url(self):
        return reverse('error_detail_admin', kwargs={'pk': self.kwargs['pk']})

@login_required
@admin_required
@require_POST
def error_edit_admin(request, rd_id):
    try:
        data = json.loads(request.body)
        percentage = Decimal(data.get('percentage'))
        
        errorResponsibility = ErrorResponsibility.objects.get(id=rd_id)
        errorResponsibility.percentage = percentage
        errorResponsibility.save()
        return JsonResponse({'status': 'success', 'message': 'Percentage updated successfully'})

    except ErrorResponsibility.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'ErrorResponsibility not found'}, status=404)
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@login_required
@admin_required
@require_POST
def error_delete_admin(request, rd_id):
    try:
        errorResponsibility = ErrorResponsibility.objects.get(id=rd_id)
        errorResponsibility.delete()

        return JsonResponse({'status': 'success', 'message': 'ErrorResponsibility deleted successfully'})

    except ErrorResponsibility.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'ErrorResponsibility not found'}, status=404)
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@admin_required
@require_POST
def edit_error_cost_admin(request, error_id):
    error = get_object_or_404(Error, pk=error_id)
    try:
        data = json.loads(request.body)
        new_cost = data.get('cost')
        if new_cost:
            new_cost = new_cost.replace(',', '.')
            new_cost = Decimal(new_cost)
        error.cost = new_cost
        error.save()
        return JsonResponse({'status': 'success'})
    except Exception as e :
        return JsonResponse({'status': 'error', 'message': str(e)})