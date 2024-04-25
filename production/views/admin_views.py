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

@login_required
@admin_required
def admin_page(request):
    branches = Branch.objects.all()
    context = {
        'branches': branches,
    }
    return render(request, 'admin_page.html', context)

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
def passport_detail_admin(request, pk):
    passport = get_object_or_404(Passport, pk=pk)
    operations = passport.order.model.operations.all() 
    size_quantities = PassportSize.objects.filter(passport=passport)
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
    form = DateRangeForm(request.GET or None)
    salaries = {}

    # Initialize assigned_works and reassigned_works outside the if block
    assigned_works = AssignedWork.objects.none()
    reassigned_works = ReassignedWork.objects.none()

    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        
        # Apply branch filter to assigned_works and reassigned_works queries
        assigned_works = AssignedWork.objects.filter(
            end_time__range=(start_date, end_date),
            end_time__isnull=False,
            is_success=True,  # Only include successful works
            work__passport__order__client_order__branch=request.user.userprofile.branch  # Filter by the current user's branch
        ).select_related('work__operation', 'employee')

        reassigned_works = ReassignedWork.objects.filter(
            original_assigned_work__end_time__range=(start_date, end_date),
            is_success=True,  # Only include successful works
            original_assigned_work__work__passport__order__client_order__branch=request.user.userprofile.branch  # Filter by the current user's branch
        ).select_related('original_assigned_work__work__operation', 'new_employee')

    # Process assigned works
    for assigned_work in assigned_works:
        employee = assigned_work.employee
        if employee not in salaries:
            salaries[employee] = {'salary': 0, 'status': assigned_work.payment_status}
        salaries[employee]['salary'] += assigned_work.work.operation.payment * assigned_work.quantity
        # Update the status if it's more 'final' than the current one
        salaries[employee]['status'] = max(salaries[employee]['status'], assigned_work.payment_status)

    # Process reassigned works
    for reassigned_work in reassigned_works:
        employee = reassigned_work.new_employee
        if employee not in salaries:
            salaries[employee] = {'salary': 0, 'status': reassigned_work.payment_status}
        salaries[employee]['salary'] += reassigned_work.original_assigned_work.work.operation.payment * reassigned_work.reassigned_quantity
        # Update the status if it's more 'final' than the current one
        salaries[employee]['status'] = max(salaries[employee]['status'], reassigned_work.payment_status)

    context = {'form': form, 'salaries': salaries}
    return render(request, 'admin/salaries/list.html', context)

@login_required
@admin_required
@require_POST
def process_payments(request):
    form = DateRangeForm(request.POST)
    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)

        assigned_works = AssignedWork.objects.filter(
            end_time__range=(start_date, end_date),
            work__passport__order__client_order__branch=request.user.userprofile.branch
        )

        reassigned_works = ReassignedWork.objects.filter(
            original_assigned_work__end_time__range=(start_date, end_date),
            original_assigned_work__work__passport__order__client_order__branch=request.user.userprofile.branch
        )

        for work in assigned_works:
            work.payment_status = AssignedWork.PAID
            work.save()

        for work in reassigned_works:
            work.payment_status = ReassignedWork.PAID
            work.save()
        base_url = reverse('salary_list')
        query_string = urlencode({'start_date': form.cleaned_data['start_date'].strftime('%Y-%m-%d'), 'end_date': form.cleaned_data['end_date'].strftime('%Y-%m-%d')})
        url = f"{base_url}?{query_string}"
        return redirect(url)
    else:
        return redirect('salary_list')

@login_required
@admin_required
def salary_detail(request, pk):
    employee = get_object_or_404(UserProfile, pk=pk, branch=request.user.userprofile.branch)  # Ensures the employee is from the current user's branch
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
            is_success=True,
            work__passport__order__client_order__branch=request.user.userprofile.branch
        ).select_related('work__operation', 'work__passport_size__size_quantity')

        reassigned_works = ReassignedWork.objects.filter(
            new_employee=employee,
            original_assigned_work__end_time__range=(start_date, end_date),
            is_success=True,
            original_assigned_work__work__passport__order__client_order__branch=request.user.userprofile.branch
        ).select_related('original_assigned_work__work__operation', 'original_assigned_work__work__passport_size__size_quantity')

        for assigned_work in assigned_works:
            work_salary, work_details = calculate_salary_and_details(assigned_work)
            total_salary += work_salary
            assigned_work_details.append(work_details)

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
        'size': work.work.passport_size.size_quantity.size,  # Correctly accessing the size through PassportSize
        'quantity': quantity,
        'time_spent_seconds': time_spent,
        'work_salary': work_salary
    }

@login_required
@admin_required
def export_salaries_to_excel(request):
    form = DateRangeForm(request.GET or None)
    
    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date'] + timedelta(days=1)
        
        assigned_works = AssignedWork.objects.filter(
            end_time__range=(start_date, end_date),
            is_success=True
        ).select_related('work__operation', 'work__passport', 'work__passport__order', 'employee', 'work__passport_size')

        reassigned_works = ReassignedWork.objects.filter(
            original_assigned_work__end_time__range=(start_date, end_date),
            is_success=True
        ).select_related('original_assigned_work', 'new_employee', 'original_assigned_work__work__passport_size')

        data = []

        for work in assigned_works:
            passport = work.work.passport
            passport_size = work.work.passport_size  # Assuming 'work' has a direct relation to 'passport_size'
            order = passport.order
            data.append([
                datetime.now().date(), order.client_order.client.name, order.model.name if order.model else '',
                order.assortment.name if order.assortment else '', passport.id, passport_size.size_quantity.size,  # Added size
                order.color, order.fabrics, passport.date, work.work.operation.id,
                work.work.operation.name, work.work.operation.payment, work.employee.employee_id,
                work.employee.user.get_full_name(), work.quantity,
                work.work.operation.payment * work.quantity
            ])

        for work in reassigned_works:
            original = work.original_assigned_work
            passport = original.work.passport
            passport_size = original.work.passport_size  # Assuming 'original' has a direct relation to 'passport_size'
            order = passport.order
            data.append([
                datetime.now().date(), order.client_order.client.name, order.model.name if order.model else '',
                order.assortment.name if order.assortment else '', passport.id, passport_size.size_quantity.size,  # Added size
                order.color, order.fabrics, passport.date, original.work.operation.id,
                original.work.operation.name, original.work.operation.payment, work.new_employee.employee_id,
                work.new_employee.user.get_full_name(), work.reassigned_quantity,
                original.work.operation.payment * work.reassigned_quantity
            ])
        
        df = pd.DataFrame(data, columns=[
            "Today's date", "Client's name", "Model's name", "Assortment's name", "Passport id", 
            "Passport size", "Order's color", "Order's fabrics", "Passport date", "Operation id", 
            "Operation name", "Operation payment", "Employee's employee_id", "Employee's full name", 
            "Work's quantity", "Salary"
        ])
        
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="salaries.xlsx"'
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        
        return response

    # Handle form errors or initial page access:
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

    def get_queryset(self):
        status = self.request.GET.get('status', None)
        queryset = super().get_queryset().order_by('term')

        if status:
            try:
                status = int(status)
                if status in dict(self.model.TYPE_CHOICES):
                    queryset = queryset.filter(status=status)
            except ValueError:
                pass

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        orders_with_days_left = []

        for order in context['orders']:
            days_left = (order.term - today).days
            orders_with_days_left.append({
                'order': order,
                'days_left': days_left
            })

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
        redirect_url = reverse('client_order_list')
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
    success_url = reverse_lazy('client_order_list')

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
        redirect_url = reverse('create_size_quantity', kwargs={'order_id': self.object.id})
        return HttpResponseRedirect(redirect_url)

@method_decorator([login_required, admin_required], name='dispatch')
class OrderDetailView(DetailView):
    model = Order
    form_class = OrderForm
    template_name = 'admin/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super(OrderDetailView, self).get_context_data(**kwargs)
        order = context['order']
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
    success_url = reverse_lazy('client_order_list')

@method_decorator([login_required, admin_required], name='dispatch')
class OrderDeleteView(DeleteView):
    model = Order
    template_name = 'admin/orders/delete.html'
    success_url = reverse_lazy('client_order_list')

@method_decorator([login_required, admin_required], name='dispatch')
class SizeQuantityCreateView(View):
    def get(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        form = SizeQuantityForm()
        size_quantities = order.size_quantities.all()
        return render(request, 'admin/orders/create_size_quantity.html', {
            'form': form,
            'size_quantities': size_quantities,
            'order': order
        })
    def post(self, request, order_id):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            form = SizeQuantityForm(request.POST)
            if form.is_valid():
                new_size_quantity = form.save(commit=False)
                new_size_quantity.save()
                order = get_object_or_404(Order, pk=order_id)
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
    success_url = reverse_lazy('client_list')

@method_decorator([login_required, admin_required], name='dispatch')
class ClientDeleteView(DeleteView):
    model = Client
    template_name = 'admin/clients/delete.html'
    success_url = reverse_lazy('client_list')



@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryListView(ListView):
    model = FixedSalary
    template_name = 'admin/fixed_salaries/list.html'
    context_object_name = 'fixed_salaries'
    paginate_by = 10
    def get_queryset(self):
        return FixedSalary.objects.all().order_by('position')

@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryCreateView(CreateView):
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
class FixedSalaryUpdateView(UpdateView):
    model = FixedSalary
    form_class = FixedSalaryForm
    template_name = 'admin/fixed_salaries/edit.html'
    success_url = reverse_lazy('fixed_salary_list')

@method_decorator([login_required, admin_required], name='dispatch')
class FixedSalaryDeleteView(DeleteView):
    model = FixedSalary
    template_name = 'admin/fixed_salaries/delete.html'
    success_url = reverse_lazy('fixed_salary_list')