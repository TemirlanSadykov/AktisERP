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
class OrderListTechnologistView(RestrictOrderBranchMixin, ListView):
    model = Order
    template_name = 'technologist/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 10

    def get_queryset(self):
        status = self.request.GET.get('status', None)
        queryset = super().get_queryset().order_by('client_order__term')

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
            days_left = (order.client_order.term - today).days
            orders_with_days_left.append({
                'order': order,
                'days_left': days_left
            })

        orders_with_days_left_sorted = sorted(orders_with_days_left, key=lambda x: x['days_left'])

        context['orders_with_days_left'] = orders_with_days_left_sorted
        context['selected_status'] = self.request.GET.get('status', '')
        context['Order'] = Order
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
        passport = Passport.objects.filter(order=order).first()
        if passport:
            context['defects'] = Defect.objects.filter(passport=passport)
            context['discrepancies'] = Discrepancy.objects.filter(passport=passport)
        else:
            context['defects'] = Defect.objects.none()
            context['discrepancies'] = Discrepancy.objects.none()
        context['size_quantities'] = order.size_quantities.all().order_by('size')
        today = timezone.localdate() 
        if order.client_order.term >= today:
            days_left = (order.client_order.term - today).days
        else:
            days_left = 0  
        context['days_left'] = days_left

        return context
    
@login_required
@technologist_required
def defect_detail(request, pk):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        defect = Defect.objects.filter(pk=pk).values(
            'pk',
            'passport__id',
            'size_quantity__size',
            'size_quantity__id', 
            'quantity',
            'defect_type',
            'severity',
            'status',
            'reported_date',
            'resolved_date'
        ).first()

        if defect:
            defect['reported_date'] = defect['reported_date'].strftime('%Y-%m-%d %H:%M:%S')
            defect['resolved_date'] = defect['resolved_date'].strftime('%Y-%m-%d %H:%M:%S') if defect['resolved_date'] else None

            works = AssignedWork.objects.filter(
                work__passport_id=defect['passport__id'],
                work__passport_size__size_quantity_id=defect['size_quantity__id']
            ).select_related('employee')
            employee_ids = [work.employee.employee_id for work in works]
            defect['responsible_employees'] = employee_ids
            
            return JsonResponse({'defect': defect}, status=200)
        else:
            return JsonResponse({'error': 'Defect not found'}, status=404)
    else:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    
@login_required
@technologist_required
@require_POST
def defect_update_status_technologist(request, pk):
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    if new_status not in [choice[0] for choice in Defect.Status.choices]:
        return JsonResponse({'status': 'error', 'message': 'Invalid status'}, status=400)

    try:
        defect = Defect.objects.get(pk=pk)
        defect.status = new_status
        defect.resolved_date = timezone.now() if new_status == Defect.Status.RESOLVED else None
        defect.save()

        return JsonResponse({'status': 'success', 'message': 'Defect status updated successfully'})
    except Defect.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Defect not found'}, status=404)
    
@login_required
@technologist_required
def discrepancy_detail(request, pk):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        discrepancy = Discrepancy.objects.filter(pk=pk).values(
            'pk',
            'passport__id',
            'size_quantity__size',
            'quantity',
            'status',
            'reported_date',
            'resolved_date'
        ).first()

        if discrepancy:
            discrepancy['reported_date'] = discrepancy['reported_date'].strftime('%Y-%m-%d %H:%M:%S')
            discrepancy['resolved_date'] = discrepancy['resolved_date'].strftime('%Y-%m-%d %H:%M:%S') if discrepancy['resolved_date'] else None
            
            return JsonResponse({'discrepancy': discrepancy}, status=200)
        else:
            return JsonResponse({'error': 'Discrepancy not found'}, status=404)
    else:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    
@login_required
@technologist_required
@require_POST
def discrepancy_update_status_technologist(request, pk):
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    if new_status not in [choice[0] for choice in Discrepancy.Status.choices]:
        return JsonResponse({'status': 'error', 'message': 'Invalid status'}, status=400)

    try:
        discrepancy = Discrepancy.objects.get(pk=pk)
        discrepancy.status = new_status
        discrepancy.resolved_date = timezone.now() if new_status == Discrepancy.Status.RESOLVED else None
        discrepancy.save()

        return JsonResponse({'status': 'success', 'message': 'Discrepancy status updated successfully'})
    except Discrepancy.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Discrepancy not found'}, status=404)
    

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

    passport_rolls = PassportRoll.objects.filter(passport=passport)
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
        'passport_rolls': passport_rolls,
        'operations': operations,
        'size_quantities': size_quantities,
        'work_by_op_and_size': work_by_op_and_size
    })

@login_required
@technologist_required
def update_work(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        assigned_work_id = data.get('work_id')
        value = data.get('value')

        try:
            current_assignment = AssignedWork.objects.get(id=assigned_work_id)
            work = Work.objects.get(id=current_assignment.work.id)
            if not value.strip():
                current_assignment.delete()
                remaining_assignments = AssignedWork.objects.filter(work=work).exists()
                if not remaining_assignments:
                    work.delete()
                return JsonResponse({'status': 'success'})

            new_assignments_data = value.split(',')
            new_assignments = {}

            for item in new_assignments_data:
                employee_id, quantity = item.split('(')
                employee_id = employee_id.strip()
                quantity = int(quantity.strip(' )'))
                new_assignments[employee_id] = quantity

            for employee_id, quantity in new_assignments.items():
                employee_profile = UserProfile.objects.filter(
                    employee_id=employee_id, type=UserProfile.EMPLOYEE,
                    branch=request.user.userprofile.branch).first()

                if not employee_profile:
                    continue

                assigned_work, created = AssignedWork.objects.update_or_create(
                    work=work, employee=employee_profile,
                    defaults={'quantity': quantity}
                )

            return JsonResponse({'status': 'success'})

        except Work.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Work not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

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
    
# @login_required
# @technologist_required
# @require_POST
# def complete_passport(request, passport_id):
#     passport = get_object_or_404(Passport, id=passport_id)
#     total_completed = PassportSize.objects.filter(passport=passport).aggregate(total=Sum('quantity'))['total'] or 0
#     order = passport.order
#     client_order = order.client_order

#     with transaction.atomic():
#         if not passport.is_completed:
#             passport.is_completed = True
#             order.completed_quantity += total_completed
#         else:
#             passport.is_completed = False
#             order.completed_quantity -= total_completed

#         passport.save()
#         order.save()

#         if order.completed_quantity >= order.quantity:
#             order.status = Order.COMPLETED
#             order.save()
#             all_orders_completed = not Order.objects.filter(client_order=client_order, status=Order.IN_PROGRESS).exists()
#             if all_orders_completed:
#                 client_order.status = ClientOrder.COMPLETED
#                 client_order.save()
#         elif order.completed_quantity < order.quantity and order.status == Order.COMPLETED:
#             order.status = Order.IN_PROGRESS
#             order.save()
#             if client_order.status == ClientOrder.COMPLETED:
#                 client_order.status = ClientOrder.IN_PROGRESS
#                 client_order.save()

#     return redirect('order_detail_technologist', pk=order.pk)

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
        queryset = super().get_queryset().order_by('name')
        node_id = self.request.GET.get('node', None)
        if node_id:
            queryset = queryset.filter(node_id=node_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        nodes = Node.objects.all().order_by('name')
        context['nodes'] = nodes
        context['selected_node'] = self.request.GET.get('node', '')
        return context

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

    def form_valid(self, form):
        return super().form_valid(form)
    
    def form_invalid(self, form):
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['nodes'] = Node.objects.prefetch_related('operations').all()
        return context

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



@method_decorator([login_required, technologist_required], name='dispatch')
class NodeListVIew(ListView):
    model = Node
    template_name = 'technologist/nodes/list.html'
    context_object_name = 'nodes'
    paginate_by = 10
    
    def get_queryset(self):
        return Node.objects.all().order_by('name')

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeCreateView(CreateView):
    model = Node
    form_class = NodeForm
    template_name = 'technologist/nodes/create.html'
    success_url = reverse_lazy('node_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeDetailView(DetailView):
    model = Node
    template_name = 'technologist/nodes/detail.html'
    context_object_name = 'node'

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeUpdateView(UpdateView):
    model = Node
    form_class = NodeForm
    template_name = 'technologist/nodes/edit.html'
    success_url = reverse_lazy('node_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeDeleteView(DeleteView):
    model = Node
    template_name = 'technologist/nodes/delete.html'
    success_url = reverse_lazy('node_list')



@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentListView(ListView):
    model = Equipment
    template_name = 'technologist/equipment/list.html'
    context_object_name = 'equipment'
    paginate_by = 10

    def get_queryset(self):
        return Equipment.objects.all().order_by('name')

@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentCreateView(CreateView):
    model = Equipment
    form_class = EquipmentForm
    template_name = 'technologist/equipment/create.html'
    success_url = reverse_lazy('equipment_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentDetailView(DetailView):
    model = Equipment
    template_name = 'technologist/equipment/detail.html'
    context_object_name = 'equipment'

@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentUpdateView(UpdateView):
    model = Equipment
    form_class = EquipmentForm
    template_name = 'technologist/equipment/edit.html'
    success_url = reverse_lazy('equipment_list')

@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentDeleteView(DeleteView):
    model = Equipment
    template_name = 'technologist/equipment/delete.html'
    success_url = reverse_lazy('equipment_list')