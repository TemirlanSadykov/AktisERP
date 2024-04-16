from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from ..decorators import technologist_required
from ..forms import *
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.shortcuts import render, redirect, get_object_or_404
from ..models import *
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.http import HttpResponseRedirect
from django.http import JsonResponse
import json
from django.db import transaction
from django.db.models import Avg, F, ExpressionWrapper, fields
from django.views.decorators.http import require_POST
from django.db.models import Sum
from ..mixins import *

@login_required
@technologist_required
def technologist_page(request):
    return render(request, 'technologist_page.html')

@method_decorator([login_required, technologist_required], name='dispatch')
class OrderListTechnologistView(RestrictBranchMixin, ListView):
    model = Order
    template_name = 'technologist/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 10

    def get_queryset(self):
        return super().get_queryset().order_by('term')

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

        orders_with_days_left_sorted = sorted(orders_with_days_left, key=lambda x: x['days_left'])

        context['orders_with_days_left'] = orders_with_days_left_sorted
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class OrderDetailTechnologistView(DetailView):
    model = Order
    template_name = 'technologist/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']
        context['passports'] = order.passports.all()
        context['size_quantities'] = order.size_quantities.all()
        today = timezone.localdate() 
        if order.term >= today:
            days_left = (order.term - today).days
        else:
            days_left = 0  
        context['days_left'] = days_left

        return context

@login_required
@technologist_required
def assign_operations(request, passport_id):
    passport = get_object_or_404(Passport, pk=passport_id)
    operations = passport.order.model.operations.all()
    size_quantities = PassportSize.objects.filter(passport=passport)

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        data = json.loads(request.body)
        operation_id = data.get('operation_id')
        passport_size_id = data.get('passport_size_id')
        value = data.get('value')

        try:
            with transaction.atomic():
                passport_size = PassportSize.objects.get(id=passport_size_id)
                total_quantity = passport_size.quantity
                assigned_quantity_sum = 0

                entries = value.split(',')
                for entry in entries:
                    if '(' in entry and ')' in entry:
                        employee_id_input, quantity = entry.split('(')
                        employee_id_input = employee_id_input.strip()
                        quantity = int(quantity.strip(' )'))
                    else:
                        employee_id_input = entry
                        quantity = total_quantity

                    employee_profile = UserProfile.objects.filter(employee_id=employee_id_input, type=UserProfile.EMPLOYEE, branch=request.user.userprofile.branch).first()
                    if not employee_profile:
                        continue

                    work, created = Work.objects.get_or_create(
                        operation_id=operation_id,
                        passport_size=passport_size,
                        passport=passport
                    )
                    AssignedWork.objects.create(
                        work=work,
                        employee=employee_profile,
                        quantity=quantity
                    )
                    assigned_quantity_sum += quantity
                    
                if assigned_quantity_sum != total_quantity:
                    raise ValueError("Assigned quantities do not match the required total.")

                return JsonResponse({'status': 'success'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    work_by_op_and_size = {}
    for assigned_work in AssignedWork.objects.filter(work__passport=passport).select_related('employee', 'work__operation', 'work__passport_size'):
        # Key as a tuple of operation_id and passport_size_id
        key = (assigned_work.work.operation_id, assigned_work.work.passport_size_id)
        if key not in work_by_op_and_size:
            work_by_op_and_size[key] = [assigned_work]
        else:
            work_by_op_and_size[key].append(assigned_work)

    return render(request, 'technologist/passports/assign_operations.html', {
        'passport': passport,
        'operations': operations,
        'size_quantities': size_quantities,
        'work_by_op_and_size': work_by_op_and_size
    })

@login_required
@technologist_required
def update_work(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        work_id = data.get('work_id')
        new_employee_id = data.get('new_employee_id')
        quantity = data.get('quantity')

        new_employee_profile, created = UserProfile.objects.get_or_create(employee_id=new_employee_id, branch=request.user.userprofile.branch)

        assigned_work, created = AssignedWork.objects.get_or_create(id=work_id)

        assigned_work.employee = new_employee_profile
        assigned_work.quantity = quantity
        assigned_work.save()

        return JsonResponse({'status': 'success'})

    return JsonResponse({'status': 'error'}, status=400)

@login_required
@technologist_required
def update_work_success(request):
    work_id = request.POST.get('work_id')
    is_success = request.POST.get('is_success') == 'true'

    try:
        assigned_work = AssignedWork.objects.get(pk=work_id)
        assigned_work.is_success = is_success
        assigned_work.save()

        return JsonResponse({'status': 'success'})
    except AssignedWork.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Assigned work not found'}, status=404)
    
@login_required
@technologist_required
@require_POST 
def complete_passport(request, passport_id):
    passport = get_object_or_404(Passport, id=passport_id)
    total_completed = passport.size_quantities.aggregate(Sum('quantity'))['quantity__sum'] or 0
    order = passport.order

    if not passport.is_completed:
        passport.is_completed = True
        order.completed_quantity += total_completed
    else:
        passport.is_completed = False
        order.completed_quantity -= total_completed

    passport.save()
    order.save()

    if order.completed_quantity >= order.quantity:
        order.status = Order.COMPLETED
    elif order.completed_quantity < order.quantity and order.status == Order.COMPLETED:
        order.status = Order.IN_PROGRESS
    order.save()

    return redirect('passport_detail', pk=passport.id)

@login_required
@technologist_required
def get_reassigned_works(request, assigned_work_id):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        reassigned_works = ReassignedWork.objects.filter(original_assigned_work_id=assigned_work_id)
        data = list(reassigned_works.values('id', 'new_employee__employee_id', 'reassigned_quantity', 'reason', 'is_completed', 'is_success'))
        return JsonResponse({'reassigned_works': data})
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
@require_POST
def reassign_work(request):
    data = json.loads(request.body)
    work_id = data.get('work_id')
    new_employee_id = data.get('new_employee_id')
    quantity = data.get('quantity')
    reason = data.get('reason')
    print(data)
    # Validation
    if not all([work_id, new_employee_id, quantity, reason]):
        return JsonResponse({'message': 'Missing required data'}, status=400)

    try:
        with transaction.atomic():
            assigned_work = get_object_or_404(AssignedWork, id=work_id)
            new_employee_profile = get_object_or_404(UserProfile, employee_id=new_employee_id, branch=request.user.userprofile.branch)

            # Attempt to retrieve an existing reassigned work
            reassigned_work, created = ReassignedWork.objects.get_or_create(
                original_assigned_work=assigned_work,
                new_employee=new_employee_profile,
                defaults={'reassigned_quantity': quantity, 'reason': reason}
            )

            if not created:
                # If the reassigned work is being updated, adjust the assigned_work.quantity
                # by adding the old reassigned quantity before setting the new one
                assigned_work.quantity += reassigned_work.reassigned_quantity
                reassigned_work.reassigned_quantity = quantity
                reassigned_work.reason = reason
                reassigned_work.is_success = False
            
            if quantity <= 0 or quantity > assigned_work.quantity:
                return JsonResponse({'message': 'Invalid quantity'}, status=400)

            # Adjust the assigned work quantity by subtracting the new reassigned quantity
            assigned_work.quantity -= quantity
            reassigned_work.save()
            assigned_work.save()

            return JsonResponse({"message": "Work reassigned successfully"}, status=200)
    
    except AssignedWork.DoesNotExist:
        return JsonResponse({'message': 'Assigned work not found'}, status=404)
    except UserProfile.DoesNotExist:
        return JsonResponse({'message': 'Employee profile not found'}, status=404)
    except Exception as e:
        return JsonResponse({'message': 'An error occurred: ' + str(e)}, status=500)
    
@login_required
@require_POST
def complete_reassigned_work(request):
    reassigned_work_id = request.POST.get('reassigned_work_id')
    try:
        reassigned_work = ReassignedWork.objects.get(id=reassigned_work_id)
        if reassigned_work.is_success:
            reassigned_work.is_success = False
            reassigned_work.is_completed = False
        else:
            reassigned_work.is_success = True

        reassigned_work.save()
        return JsonResponse({'message': 'Reassigned work status updated successfully'}, status=200)
    except ReassignedWork.DoesNotExist:
        return JsonResponse({'message': 'Reassigned work not found'}, status=404)
    except Exception as e:
        return JsonResponse({'message': 'An error occurred: ' + str(e)}, status=500)



@method_decorator([login_required, technologist_required], name='dispatch')
class OperationListView(ListView):
    model = Operation
    template_name = 'technologist/operations/list.html'
    context_object_name = 'operations'
    paginate_by = 10
    def get_queryset(self):
        return Operation.objects.all().order_by('name')

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationCreateView(CreateView):
    model = Operation
    form_class = OperationForm
    template_name = 'technologist/operations/create.html'
    success_url = reverse_lazy('operation_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationDetailView(DetailView):
    model = Operation
    template_name = 'technologist/operations/detail.html'
    context_object_name = 'operation'

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationUpdateView(UpdateView):
    model = Operation
    form_class = OperationForm
    template_name = 'technologist/operations/edit.html'
    success_url = reverse_lazy('operation_list')
    def form_valid(self, form):
        # Example print statement
        print("Form data:", form.cleaned_data)
        return super().form_valid(form)

    def form_invalid(self, form):
        # Print errors if the form is invalid
        print("Form errors:", form.errors)
        return super().form_invalid(form)

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationDeleteView(DeleteView):
    model = Operation
    template_name = 'technologist/operations/delete.html'
    success_url = reverse_lazy('operation_list')

@login_required
@technologist_required
def calculate_average_completion_time(request, operation_id):
    operation = get_object_or_404(Operation, pk=operation_id)
    assigned_works = AssignedWork.objects.filter(work__operation=operation, end_time__isnull=False, start_time__isnull=False)

    if assigned_works.exists():
        for assigned_work in assigned_works:
            reassigned_work = ReassignedWork.objects.filter(original_assigned_work=assigned_work).first()

            if reassigned_work:
                adjusted_quantity = assigned_work.quantity + reassigned_work.reassigned_quantity
            else:
                adjusted_quantity = assigned_work.quantity
            assigned_work.completion_time_per_unit = (assigned_work.end_time - assigned_work.start_time) / adjusted_quantity

        total_completion_time = sum([aw.completion_time_per_unit.total_seconds() for aw in assigned_works])
        average_seconds = total_completion_time / len(assigned_works)

        operation.average_completion_time = average_seconds
        operation.save()

        messages.success(request, 'Average completion time per unit calculated successfully.')
    else:
        messages.error(request, 'No completed assigned works found for this operation.')

    return redirect('operation_detail', pk=operation.pk)



@method_decorator([login_required, technologist_required], name='dispatch')
class RollListView(RestrictBranchMixin, ListView):
    model = Roll
    template_name = 'technologist/rolls/list.html'
    context_object_name = 'rolls'
    paginate_by = 10
    def get_queryset(self):
        return super().get_queryset().order_by('name')

@method_decorator([login_required, technologist_required], name='dispatch')
class RollCreateView(AssignBranchMixin, CreateView):
    model = Roll
    form_class = RollForm
    template_name = 'technologist/rolls/create.html'
    success_url = reverse_lazy('roll_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class RollDetailView(DetailView):
    model = Roll
    template_name = 'technologist/rolls/detail.html'
    context_object_name = 'roll'

@method_decorator([login_required, technologist_required], name='dispatch')
class RollUpdateView(RestrictBranchMixin, UpdateView):
    model = Roll
    form_class = RollForm
    template_name = 'technologist/rolls/edit.html'
    success_url = reverse_lazy('roll_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class RollDeleteView(RestrictBranchMixin, DeleteView):
    model = Roll
    template_name = 'technologist/rolls/delete.html'
    success_url = reverse_lazy('roll_list')



@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentListView(RestrictBranchMixin, ListView):
    model = Assortment
    template_name = 'technologist/assortments/list.html'
    context_object_name = 'assortments'
    paginate_by = 10
    def get_queryset(self):
        return super().get_queryset().order_by('name')

@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentCreateView(AssignBranchMixin, CreateView):
    model = Assortment
    form_class = AssortmentForm
    template_name = 'technologist/assortments/create.html'
    success_url = reverse_lazy('assortment_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentDetailView(DetailView):
    model = Assortment
    template_name = 'technologist/assortments/detail.html'
    context_object_name = 'assortment'

@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentUpdateView(RestrictBranchMixin, UpdateView):
    model = Assortment
    form_class = AssortmentForm
    template_name = 'technologist/assortments/edit.html'
    success_url = reverse_lazy('assortment_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentDeleteView(RestrictBranchMixin, DeleteView):
    model = Assortment
    template_name = 'technologist/assortments/delete.html'
    success_url = reverse_lazy('assortment_list')



@method_decorator([login_required, technologist_required], name='dispatch')
class ModelListView(ListView):
    model = Model
    template_name = 'technologist/models/list.html'
    context_object_name = 'models'
    paginate_by = 10
    def get_queryset(self):
        return Model.objects.all().order_by('name')

@method_decorator([login_required, technologist_required], name='dispatch')
class ModelCreateView(CreateView):
    model = Model
    form_class = ModelForm
    template_name = 'technologist/models/create.html'
    success_url = reverse_lazy('model_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class ModelDetailView(DetailView):
    model = Model
    template_name = 'technologist/models/detail.html'
    context_object_name = 'model'

@method_decorator([login_required, technologist_required], name='dispatch')
class ModelUpdateView(UpdateView):
    model = Model
    form_class = ModelForm
    template_name = 'technologist/models/edit.html'
    success_url = reverse_lazy('model_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class ModelDeleteView(DeleteView):
    model = Model
    template_name = 'technologist/models/delete.html'
    success_url = reverse_lazy('model_list')
