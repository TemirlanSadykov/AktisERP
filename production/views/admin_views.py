# admin_views.py
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, DeleteView, UpdateView
from django.views.generic.edit import CreateView
from django.contrib.auth.decorators import login_required
from ..decorators import admin_required
from ..models import UserProfile
from ..forms import UserWithProfileForm
from django.urls import reverse_lazy
from django.shortcuts import render
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from ..decorators import employee_required
from ..forms import UserEditForm
from ..models import UserProfile
from django.contrib import messages
from ..models import Passport, Work, Operation, SizeQuantity
from django.utils import timezone
from datetime import timedelta
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from ..decorators import admin_required
from ..models import EmployeeAttendance, Order, AssignedWork, Client, ReassignedWork
from ..forms import DateForm, DateRangeForm, OrderForm, ClientForm

@login_required
@admin_required
def admin_page(request):
    return render(request, 'admin_page.html')

@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeListView(ListView):
    model = UserProfile
    template_name = 'admin/employees/list.html'
    context_object_name = 'employees'
    paginate_by = 10
    def get_queryset(self):
        return UserProfile.objects.filter(type__in=[UserProfile.EMPLOYEE, UserProfile.TECHNOLOGIST])

@method_decorator([login_required, admin_required], name='dispatch')
class EmployeeCreateView(CreateView):
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
    user_profile = get_object_or_404(UserProfile, pk=pk)
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
class EmployeeDeleteView(DeleteView):
    model = UserProfile
    template_name = 'admin/employees/delete.html'
    success_url = reverse_lazy('employee_list')


@method_decorator([login_required, admin_required], name='dispatch')
class PassportListViewAdmin(ListView):
    model = Passport
    template_name = 'admin/passports/list.html'
    context_object_name = 'passports'

@login_required
@admin_required
def passport_detail_admin(request, pk):
    passport = get_object_or_404(Passport, pk=pk)
    operations = passport.order.model.operations.all() 
    size_quantities = passport.size_quantities.all()
    work_by_op_and_size = {}
    for assigned_work in AssignedWork.objects.filter(work__passport=passport).select_related('employee', 'work__operation', 'work__size_quantity'):
        key = (assigned_work.work.operation_id, assigned_work.work.size_quantity_id)
        if key not in work_by_op_and_size:
            work_by_op_and_size[key] = [assigned_work]
        else:
            work_by_op_and_size[key].append(assigned_work)
    return render(request, 'admin/passports/detail.html', {
        'passport': passport, 
        'operations': operations, 
        'size_quantities': size_quantities,
        'work_by_op_and_size': work_by_op_and_size
    })

@login_required
@admin_required
def salary_list(request):
    form = DateRangeForm(request.GET or None)
    salaries = {}

    # Initialize assigned_works and reassigned_works outside the if block
    assigned_works = AssignedWork.objects.none()
    reassigned_works = ReassignedWork.objects.none()

    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        
        assigned_works = AssignedWork.objects.filter(
            end_time__range=(start_date, end_date),
            end_time__isnull=False,
            is_success=True  # Only include successful works
        ).select_related('work__operation', 'employee')

        reassigned_works = ReassignedWork.objects.filter(
            original_assigned_work__end_time__range=(start_date, end_date),
            is_success=True  # Only include successful works
        ).select_related('original_assigned_work__work__operation', 'new_employee')

    # Process assigned works
    for assigned_work in assigned_works:
        employee = assigned_work.employee
        salaries[employee] = salaries.get(employee, 0) + \
                             assigned_work.work.operation.payment * assigned_work.quantity

    # Process reassigned works
    for reassigned_work in reassigned_works:
        employee = reassigned_work.new_employee
        salaries[employee] = salaries.get(employee, 0) + \
                             reassigned_work.original_assigned_work.work.operation.payment * reassigned_work.reassigned_quantity

    context = {'form': form, 'salaries': salaries}
    return render(request, 'admin/salaries/list.html', context)

@login_required
@admin_required
def salary_detail(request, employee_id):
    employee = get_object_or_404(UserProfile, pk=employee_id)
    initial_data = {
        'start_date': request.GET.get('start_date'),
        'end_date': request.GET.get('end_date'),
    }
    form = DateRangeForm(request.GET or None, initial=initial_data)
    assigned_work_details = []
    total_salary = 0

    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        assigned_works = AssignedWork.objects.filter(
            employee=employee,
            end_time__range=(start_date, end_date),
            is_success=True  # Only include successful works
        ).select_related('work__operation', 'work__size_quantity')

        reassigned_works = ReassignedWork.objects.filter(
            new_employee=employee,
            original_assigned_work__end_time__range=(start_date, end_date),
            is_success=True  # Only include successful works
        ).select_related('original_assigned_work__work__operation', 'original_assigned_work__work__size_quantity')

        # Process assigned works
        for assigned_work in assigned_works:
            work_salary, work_details = calculate_salary_and_details(assigned_work)
            total_salary += work_salary
            assigned_work_details.append(work_details)

        # Process reassigned works
        for reassigned_work in reassigned_works:
            work_salary, work_details = calculate_salary_and_details(reassigned_work.original_assigned_work, reassigned_quantity=reassigned_work.reassigned_quantity)
            total_salary += work_salary
            assigned_work_details.append(work_details)

    context = {
        'form': form,
        'employee': employee,
        'works': assigned_work_details,
        'total_salary': total_salary,
    }
    return render(request, 'admin/salaries/detail.html', context)

def calculate_salary_and_details(work, reassigned_quantity=None):
    """Helper function to calculate salary and details for a work or reassigned work."""
    quantity = reassigned_quantity if reassigned_quantity is not None else work.quantity
    work_salary = work.work.operation.payment * quantity
    time_spent = (work.end_time - work.start_time).total_seconds() if work.start_time and work.end_time else 0
    return work_salary, {
        'operation': work.work.operation,
        'size': work.work.size_quantity.size,
        'quantity': quantity,
        'time_spent_seconds': time_spent,
        'work_salary': work_salary
    }



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
                is_clock_in=True
            ).distinct('employee')

    context = {
        'form': form,
        'attendances': attendances,
    }
    return render(request, 'admin/attendances/list.html', context)



@method_decorator([login_required, admin_required], name='dispatch')
class OrderListView(ListView):
    model = Order
    template_name = 'admin/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 10

@method_decorator([login_required, admin_required], name='dispatch')
class OrderCreateView(CreateView):
    model = Order
    form_class = OrderForm
    template_name = 'admin/orders/create.html'
    success_url = reverse_lazy('order_list')

@method_decorator([login_required, admin_required], name='dispatch')
class OrderDetailView(DetailView):
    model = Order
    template_name = 'admin/orders/detail.html'
    context_object_name = 'order'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']
        context['passports'] = order.passports.all()
        return context

@method_decorator([login_required, admin_required], name='dispatch')
class OrderUpdateView(UpdateView):
    model = Order
    form_class = OrderForm
    template_name = 'admin/orders/edit.html'
    success_url = reverse_lazy('order_list')

@method_decorator([login_required, admin_required], name='dispatch')
class OrderDeleteView(DeleteView):
    model = Order
    template_name = 'admin/orders/delete.html'
    success_url = reverse_lazy('order_list')


@method_decorator([login_required, admin_required], name='dispatch')
class ClientListView(ListView):
    model = Client
    template_name = 'admin/clients/list.html'
    context_object_name = 'clients'
    paginate_by = 10

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
    success_url = reverse_lazy('client_list')

@method_decorator([login_required, admin_required], name='dispatch')
class ClientDeleteView(DeleteView):
    model = Client
    template_name = 'admin/clients/delete.html'
    success_url = reverse_lazy('client_list')