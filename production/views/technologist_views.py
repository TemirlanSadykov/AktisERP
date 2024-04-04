# technologist_views.py
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

@login_required
@technologist_required
def technologist_page(request):
    return render(request, 'technologist_page.html')

@method_decorator([login_required, technologist_required], name='dispatch')
class PassportListView(ListView):
    model = Passport
    template_name = 'technologist/passports/list.html'
    context_object_name = 'passports'

@method_decorator([login_required, technologist_required], name='dispatch')
class PassportCreateView(CreateView):
    model = Passport
    form_class = PassportForm
    template_name = 'technologist/passports/create.html'
    success_url = reverse_lazy('passport_list')
    def get_success_url(self):
        passport_id = self.object.pk
        return reverse('create_size_quantity', kwargs={'passport_id': passport_id})

@method_decorator([login_required, technologist_required], name='dispatch')
class PassportDetailView(DetailView):
    model = Passport
    template_name = 'technologist/passports/detail.html'
    context_object_name = 'passport'

@method_decorator([login_required, technologist_required], name='dispatch')
class PassportUpdateView(UpdateView):
    model = Passport
    form_class = PassportForm
    template_name = 'technologist/passports/edit.html'
    success_url = reverse_lazy('passport_list')

    def form_valid(self, form):
        messages.success(self.request, 'Passport updated successfully.')
        return super().form_valid(form)

@method_decorator([login_required, technologist_required], name='dispatch')
class PassportDeleteView(DeleteView):
    model = Passport
    template_name = 'technologist/passports/delete.html'
    success_url = reverse_lazy('passport_list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Passport deleted successfully.')
        return super().delete(request, *args, **kwargs)

@method_decorator([login_required, technologist_required], name='dispatch')
class SizeQuantityCreateView(View):
    def get(self, request, passport_id):
        passport = get_object_or_404(Passport, pk=passport_id)
        form = SizeQuantityForm()
        size_quantities = passport.size_quantities.all()
        return render(request, 'technologist/passports/create_size_quantity.html', {
            'form': form,
            'size_quantities': size_quantities,
            'passport': passport
        })
    def post(self, request, passport_id):
        print(request.headers)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            form = SizeQuantityForm(request.POST)
            if form.is_valid():
                new_size_quantity = form.save(commit=False)
                new_size_quantity.save()
                passport = get_object_or_404(Passport, pk=passport_id)
                passport.size_quantities.add(new_size_quantity)
                size_quantities = passport.size_quantities.values('id', 'size', 'quantity')
                return JsonResponse({'success': True, 'sizeQuantities': list(size_quantities)})
            else:
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        return JsonResponse({'success': False, 'error': 'Non-AJAX request not allowed'}, status=400)
    
@login_required
@technologist_required
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
@technologist_required
def delete_size_quantity(request, sq_id):
    if request.method == 'POST':
        size_quantity = get_object_or_404(SizeQuantity, id=sq_id)
        size_quantity.delete()
        return JsonResponse({'status': 'success'}, status=200)
    return JsonResponse({'status': 'error'}, status=400)

@login_required
@technologist_required
def assign_operations(request, passport_id):
    passport = get_object_or_404(Passport, pk=passport_id)
    operations = passport.order.model.operations.all()
    size_quantities = passport.size_quantities.all()

    if request.method == 'POST':
        with transaction.atomic():
            errors = False
            for key, input_value in request.POST.items():
                if key.startswith('employee_') and input_value:
                    _, operation_id, size_quantity_id = key.split('_')
                    entries = [entry.strip() for entry in input_value.split(',')]
                    total_quantity = passport.size_quantities.get(id=size_quantity_id).quantity
                    
                    # Reset quantities for existing assigned work to avoid duplication
                    Work.objects.filter(operation_id=operation_id, size_quantity_id=size_quantity_id, passport=passport).delete()

                    for entry in entries:
                        if '(' in entry and ')' in entry:
                            employee_id_input, quantity = entry.split('(')
                            employee_id_input = employee_id_input.strip()
                            quantity = int(quantity.strip(' )'))
                        else:
                            employee_id_input = entry
                            quantity = total_quantity

                        if employee_id_input:
                            employee_profile = UserProfile.objects.filter(employee_id=employee_id_input, type=UserProfile.EMPLOYEE).first()
                            if not employee_profile:
                                messages.error(request, f'Invalid employee ID: {employee_id_input}')
                                errors = True
                                continue
                            
                            work, created = Work.objects.get_or_create(
                                operation_id=operation_id,
                                size_quantity_id=size_quantity_id,
                                passport=passport
                            )
                            AssignedWork.objects.create(
                                work=work,
                                employee=employee_profile,
                                quantity=quantity
                            )
            if not errors:
                return HttpResponseRedirect(request.path_info)

    work_by_op_and_size = {}
    for assigned_work in AssignedWork.objects.filter(work__passport=passport).select_related('employee', 'work__operation', 'work__size_quantity'):
        key = (assigned_work.work.operation_id, assigned_work.work.size_quantity_id)
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

        new_employee_profile, created = UserProfile.objects.get_or_create(employee_id=new_employee_id)

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
        assigned_work = AssignedWork.objects.select_related('work__passport__order').get(pk=work_id)
        order = assigned_work.work.passport.order

        if is_success and not assigned_work.is_success:
            assigned_work.is_success = True
        elif not is_success and assigned_work.is_success:
            assigned_work.is_success = False
            assigned_work.start_time = None 
            assigned_work.end_time = None

        assigned_work.save()
        order.save() 

        return JsonResponse({'status': 'success'})
    except AssignedWork.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Assigned work not found'}, status=404)
    
@login_required
@technologist_required
@require_POST 
def complete_passport(request, passport_id):
    passport = get_object_or_404(Passport, id=passport_id)
    passport.is_completed = True
    passport.save()

    total_completed = passport.size_quantities.aggregate(Sum('quantity'))['quantity__sum'] or 0
    order = passport.order
    order.completed_quantity += total_completed
    order.save()

    if order.completed_quantity >= order.quantity:
        order.status = Order.COMPLETED
        order.save()

    return redirect('passport_list')
    



@method_decorator([login_required, technologist_required], name='dispatch')
class OperationListView(ListView):
    model = Operation
    template_name = 'technologist/operations/list.html'
    context_object_name = 'operations'

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
        avg_completion_time = assigned_works.annotate(
            completion_time_per_unit=ExpressionWrapper(
                (F('end_time') - F('start_time')) / F('quantity'),
                output_field=fields.DurationField()
            )
        ).aggregate(average_time=Avg('completion_time_per_unit'))

        average_seconds = avg_completion_time['average_time'].total_seconds()
        operation.average_completion_time = average_seconds
        operation.save()

        messages.success(request, 'Average completion time per unit calculated successfully.')
    else:
        messages.error(request, 'No completed assigned works found for this operation.')

    return redirect('operation_detail', pk=operation.pk)



@method_decorator([login_required, technologist_required], name='dispatch')
class RollListView(ListView):
    model = Roll
    template_name = 'technologist/rolls/list.html'
    context_object_name = 'rolls'

@method_decorator([login_required, technologist_required], name='dispatch')
class RollCreateView(CreateView):
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
class RollUpdateView(UpdateView):
    model = Roll
    form_class = RollForm
    template_name = 'technologist/rolls/edit.html'
    success_url = reverse_lazy('roll_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class RollDeleteView(DeleteView):
    model = Roll
    template_name = 'technologist/rolls/delete.html'
    success_url = reverse_lazy('roll_list')



@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentListView(ListView):
    model = Assortment
    template_name = 'technologist/assortments/list.html'
    context_object_name = 'assortments'

@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentCreateView(CreateView):
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
class AssortmentUpdateView(UpdateView):
    model = Assortment
    form_class = AssortmentForm
    template_name = 'technologist/assortments/edit.html'
    success_url = reverse_lazy('assortment_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentDeleteView(DeleteView):
    model = Assortment
    template_name = 'technologist/assortments/delete.html'
    success_url = reverse_lazy('assortment_list')



@method_decorator([login_required, technologist_required], name='dispatch')
class ModelListView(ListView):
    model = Model
    template_name = 'technologist/models/list.html'
    context_object_name = 'models'

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
