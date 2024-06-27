from collections import defaultdict
import json
import openpyxl

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.db import transaction
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView 
from openpyxl import Workbook
from openpyxl.styles import  Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from ..decorators import technologist_required
from ..forms import *
from ..mixins import *
from ..models import *


CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@technologist_required
def technologist_page(request):
    context = {
               'sidebar_type': 'technology'
               }
    return render(request, 'technologist_page.html', context)

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
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class OrderDetailTechnologistView(DetailView):
    model = Order
    template_name = 'technologist/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']

        # Fetch all passports related to the order
        passports = order.passports.all()

        # Aggregating errors across all passports associated with the order
        errors = Error.objects.filter(piece__passport_size__passport__in=passports).order_by('error_type')

        size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'passport_size_id': None, 'stage': None, 'extra': None}))
        total_per_size = defaultdict(int)

        for passport in passports:
            for passport_size in passport.passport_sizes.all():
                size = passport_size.size_quantity.size
                extra_key = f"{size}-{passport_size.extra}" if passport_size.extra else size
                size_data[extra_key][passport.id]['quantity'] += passport_size.quantity
                size_data[extra_key][passport.id]['passport_size_id'] = passport_size.id
                size_data[extra_key][passport.id]['stage'] = passport_size.stage
                size_data[extra_key][passport.id]['extra'] = passport_size.extra
                total_per_size[size] += passport_size.quantity

        required_missing = {sq.size: {'required': sq.quantity, 'missing': sq.quantity - total_per_size.get(sq.size, 0)}
                            for sq in order.size_quantities.all().order_by('size')}

        # Adjusting for sizes in passports not in order sizes
        for size in total_per_size:
            if size not in required_missing:
                required_missing[size] = {'required': 0, 'missing': -total_per_size[size]}

        # Sorting size_data keys
        sorted_size_data_keys = sorted(size_data.keys(), key=lambda x: (int(x.split('-')[0]), x))

        context.update({
            'errors': errors,
            'size_data': {k: dict(size_data[k]) for k in sorted_size_data_keys},
            'total_per_size': dict(total_per_size),
            'required_missing': required_missing,
            'passports': passports,
            'days_left': (order.client_order.term - timezone.now().date()).days if order.client_order.term >= timezone.now().date() else 0,
            'sidebar_type': 'technology'
        })

        return context
    
@login_required
@technologist_required
def error_detail(request, pk):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        error = Error.objects.filter(pk=pk).values(
            'pk', 'piece__passport_size__passport__id', 'piece__passport_size__size_quantity__size', 'piece__id', 'piece__passport_size__size_quantity__id',
            'error_type', 'piece__defect_type', 'cost', 'status',
            'reported_date', 'resolved_date'
        ).first()

        if error:
            error['reported_date'] = error['reported_date'].strftime('%Y-%m-%d %H:%M:%S')
            error['resolved_date'] = error['resolved_date'].strftime('%Y-%m-%d %H:%M:%S') if error['resolved_date'] else None
            error['status'] = Error.Status(error['status']).label

            if error['error_type'] == 'DEFECT':
                works = AssignedWork.objects.filter(
                    work__passport_id=error['piece__passport_size__passport__id'],
                    work__passport_size__size_quantity_id=error['piece__passport_size__size_quantity__id']
                ).select_related('employee')
                employee_ids = [work.employee.employee_id for work in works]
                error['responsible_employees'] = employee_ids
            
            return JsonResponse({'error': error}, status=200)
        else:
            return JsonResponse({'error': 'Error not found'}, status=404)
    else:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    
@login_required
@technologist_required
@require_POST
def error_update_status(request, pk):
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    
    valid_statuses = [choice[0] for choice in Error.Status.choices]
    if new_status not in valid_statuses:
        return JsonResponse({'status': 'error', 'message': 'Invalid status'}, status=400)

    try:
        error = Error.objects.get(pk=pk)
        error.status = new_status
        error.resolved_date = timezone.now() if new_status == Error.Status.RESOLVED else None
        error.save()

        return JsonResponse({'status': 'success', 'message': 'Error status updated successfully'})
    except Error.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Error not found'}, status=404)    

@login_required
@technologist_required
def assign_operations(request, passport_id):
    passport = get_object_or_404(Passport, pk=passport_id)
    model_operations = ModelOperation.objects.filter(
        model=passport.order.model
    ).select_related('operation').order_by('order')
    operations = [model_op.operation for model_op in model_operations]
    size_quantities = PassportSize.objects.filter(passport=passport).order_by('size_quantity__size')

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        data = json.loads(request.body)
        operation_id = data.get('operation_id')
        passport_size_id = data.get('passport_size_id')
        value = data.get('value')

        try:
            with transaction.atomic():
                passport_size = PassportSize.objects.get(id=passport_size_id)
                total_quantity = passport_size.quantity

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
        'work_by_op_and_size': work_by_op_and_size,
        'sidebar_type': 'technology'
    })

@login_required
@technologist_required
@require_POST
def update_work(request):
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
        first = True  # Flag to track the first item

        for item in new_assignments_data:
            employee_id, quantity = item.split('(')
            employee_id = employee_id.strip()
            quantity = int(quantity.strip(' )'))

            employee_profile = UserProfile.objects.filter(
                employee_id=employee_id, type=UserProfile.EMPLOYEE,
                branch=request.user.userprofile.branch).first()

            if not employee_profile:
                continue

            # Handle the first item by updating existing assigned work
            if first:
                current_assignment.employee = employee_profile
                current_assignment.quantity = quantity
                current_assignment.save()
                first = False  # Update the flag after handling the first item
            else:
                # Create new assigned works for subsequent items
                AssignedWork.objects.create(
                    work=work,
                    employee=employee_profile,
                    quantity=quantity
                )

        return JsonResponse({'status': 'success'})

    except Work.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Work not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

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

@login_required
@technologist_required
def download_passport_excel(request, passport_id):
    # Fetch the Passport and related data
    passport = get_object_or_404(Passport, pk=passport_id)
    passport_sizes = PassportSize.objects.filter(passport=passport)
    passport_rolls = PassportRoll.objects.filter(passport=passport)

    # Create a workbook and initialize a worksheet
    wb = Workbook()
    ws = wb.active

    # First row headers
    headers = [
        'заказч', 'модель', 'ассортимент', '', '№ рулона', 'цвет', 'Ткань', 'дата кроя'
    ]
    ws.append(headers)

    # Set headers style
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')

    # Insert data in the second row
    passport_roll = passport_rolls.first() if passport_rolls else None
    second_row_data = [
        passport.order.client_order.client.name, passport.order.model.name, passport.order.assortment.name,
        '', passport_roll.roll.name if passport_roll else '',
        passport_roll.roll.color if passport_roll else '',
        passport_roll.roll.fabrics if passport_roll else '',
        passport.date.strftime("%m/%d/%Y") if passport.date else ''
    ]
    ws.append(second_row_data)

    # Define the operation headers
    operation_headers = [
        '№', 'Операции', 'Оборуд.', 'тех-процесс', 'расценки', 'трудоемкость'
    ]

    # Add size columns based on size_quantities in the order
    sizes = [size.size for size in passport.order.size_quantities.all()]
    operation_headers.extend(sizes)

    # Append operation headers
    ws.append(operation_headers)

    # Set style for operation headers
    for cell in ws[3]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')

    model_operations = ModelOperation.objects.filter(
        model=passport.order.model
    ).select_related('operation').order_by('order')
    operations = [model_op.operation for model_op in model_operations]

    for index, operation in enumerate(operations, start=1):
        # Assume 'get_operation_details' is a method to fetch needed details
        # You will need to implement this based on your application's specific data
        operation_details = get_operation_details(operation, passport_sizes)
        row_data = [index] + operation_details
        ws.append(row_data)


    # Autosize column widths
    for column_cells in ws.columns:
        length = max(len(str(cell.value)) for cell in column_cells)
        ws.column_dimensions[get_column_letter(column_cells[0].column)].width = length

    # Apply bold font style to headers and sizes
    bold_font = Font(bold=True)
    header_rows = [1, 3]  # Rows which contain the headers you mentioned

    # Apply bold font to all cells in the header rows
    for row in header_rows:
        for cell in ws[row]:
            cell.font = bold_font

    # Additionally, bold the size headers individually in case they are not in the above rows
    size_header_row = 3  # Assuming the size headers are in the third row
    for size_col in range(7, 7 + len(sizes)):  # Adjust 7 if your size columns start from a different index
        ws.cell(row=size_header_row, column=size_col).font = bold_font

    # Define border style
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # Apply borders to the first two rows, creating a box effect
    for row in ws.iter_rows(min_row=1, max_row=2, min_col=1, max_col=ws.max_column):
        for cell in row:
            cell.border = thin_border

    # Insert an empty row after the first two rows
    ws.insert_rows(3)

    # Now adjust your other rows accordingly since you inserted a new row
    # You might need to update the `header_rows` and `size_header_row` if you used the previous code snippet
    header_rows = [1, 4]  # Updated to reflect the new empty row
    size_header_row = 4   # Updated to reflect the new empty row

    # Apply bold font to all cells in the updated header rows
    for row in header_rows:
        for cell in ws[row]:
            cell.font = bold_font

    # Additionally, bold the size headers individually
    for size_col in range(7, 7 + len(sizes)):  # Adjust 7 if your size columns start from a different index
        ws.cell(row=size_header_row, column=size_col).font = bold_font

    ws.column_dimensions['D'].width = 50

    # Set the HTTP response with a content-type for Excel file
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="Passport_{passport_id}_Details.xlsx"'

    # Save the workbook to the response
    wb.save(response)
    return response

def get_operation_details(operation, passport_sizes):
    details = [
        operation.node.name,
        operation.equipment.name,
        operation.name,
        operation.payment,
        operation.preferred_completion_time
    ]

    # Ensure the sizes are sorted consistently
    sorted_sizes = sorted(passport_sizes, key=lambda x: x.size_quantity.size)
    
    # Fetch and accumulate details for each sorted size
    for passport_size in sorted_sizes:
        assigned_works = AssignedWork.objects.filter(
            work__operation=operation,
            work__passport_size=passport_size
        ).select_related('employee')

        reassigned_works = ReassignedWork.objects.filter(
            original_assigned_work__work__operation=operation,
            original_assigned_work__work__passport_size=passport_size
        ).select_related('new_employee')

        employee_ids = set(aw.employee.employee_id for aw in assigned_works)
        employee_ids.update(rw.new_employee.employee_id for rw in reassigned_works)

        details.append(', '.join(employee_ids))

    return details



@method_decorator([login_required, technologist_required], name='dispatch')
class OperationListView(ListView):
    model = Operation
    template_name = 'technologist/operations/list.html'
    context_object_name = 'operations'

    def get_paginate_by(self, queryset):
        node_id = self.request.GET.get('node', None)
        if node_id:
            return None
        return 15

    def get_queryset(self):
        queryset = super().get_queryset().order_by('number')
        node_id = self.request.GET.get('node', None)
        if node_id:
            queryset = queryset.filter(node_id=node_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        nodes = Node.objects.all().order_by('name')
        context['nodes'] = nodes
        context['selected_node'] = self.request.GET.get('node', '')
        context['upload_form'] = UploadFileForm()
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationCreateView(CreateView):
    model = Operation
    form_class = OperationForm
    template_name = 'technologist/operations/create.html'
    success_url = reverse_lazy('operation_create')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationDetailView(DetailView):
    model = Operation
    template_name = 'technologist/operations/detail.html'
    context_object_name = 'operation'
    def get_context_data(self, **kwargs):
        context = super(OperationDetailView, self).get_context_data(**kwargs)
        operation = self.object
        models = Model.objects.filter(operations=operation)
        context['models'] = models
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationUpdateView(UpdateView):
    model = Operation
    form_class = OperationForm
    template_name = 'technologist/operations/edit.html'
    success_url = reverse_lazy('operation_list')
    def form_valid(self, form):
        return super().form_valid(form)

    def form_invalid(self, form):
        # Print errors if the form is invalid
        print("Form errors:", form.errors)
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class OperationDeleteView(DeleteView):
    model = Operation
    template_name = 'technologist/operations/delete.html'
    success_url = reverse_lazy('operation_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

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

@login_required
@technologist_required
@require_POST
def operation_upload(request):
    form = UploadFileForm(request.POST, request.FILES)
    if form.is_valid():
        excel_file = request.FILES['excel_file']
        workbook = openpyxl.load_workbook(excel_file)
        sheet = workbook.active

        with transaction.atomic():
            for row in sheet.iter_rows(min_row=2, values_only=True):
                number, operation_name, node_name, node_number, equipment_name, time, price = row

                node, created = Node.objects.get_or_create(
                    number=node_number,
                    defaults={'name': node_name}
                )
                if not created and node.name != node_name:
                    node.name = node_name
                    node.save()
                equipment, _ = Equipment.objects.get_or_create(name=equipment_name)
                operation, created = Operation.objects.get_or_create(
                    number=number,
                    defaults={
                        'name': operation_name,
                        'equipment': equipment,
                        'node': node,
                        'preferred_completion_time': time,
                        'payment': price
                    }
                )
                if not created:
                    operation.name = operation_name
                    operation.equipment = equipment
                    operation.node = node
                    operation.preferred_completion_time = time
                    operation.payment = price
                    operation.save()
                print(operation)
        messages.success(request, 'Operations uploaded successfully.')
        return HttpResponseRedirect(reverse_lazy('operation_list'))
    else:
        messages.error(request, 'There was an error with the file upload.')
        return HttpResponseRedirect(reverse_lazy('operation_upload'))
    
@login_required
@technologist_required
def operation_download(request):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Operations"

    headers = ["№ПП (авто генерация)", "Тех-процесс", "Узел", "№ узла", "Оборудование", "Время", "Оплата"]
    sheet.append(headers)

    for operation in Operation.objects.all().order_by('number'):
        row = [
            operation.number,
            operation.name,
            operation.node.name if operation.node else "",
            operation.node.number if operation.node else "",
            operation.equipment.name if operation.equipment else "",
            operation.preferred_completion_time,
            operation.payment,
        ]
        sheet.append(row)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=operations.xlsx'
    workbook.save(response)
    return response


@method_decorator([login_required, technologist_required], name='dispatch')
class RollListView(RestrictBranchMixin, ListView):
    model = Roll
    template_name = 'technologist/rolls/list.html'
    context_object_name = 'rolls'
    paginate_by = 10
    def get_queryset(self):
        return super().get_queryset().order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class RollCreateView(AssignBranchMixin, CreateView):
    model = Roll
    form_class = RollForm
    template_name = 'technologist/rolls/create.html'
    success_url = reverse_lazy('roll_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class RollDetailView(DetailView):
    model = Roll
    template_name = 'technologist/rolls/detail.html'
    context_object_name = 'roll'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class RollUpdateView(RestrictBranchMixin, UpdateView):
    model = Roll
    form_class = RollForm
    template_name = 'technologist/rolls/edit.html'
    success_url = reverse_lazy('roll_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class RollDeleteView(RestrictBranchMixin, DeleteView):
    model = Roll
    template_name = 'technologist/rolls/delete.html'
    success_url = reverse_lazy('roll_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context



@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentListView(RestrictBranchMixin, ListView):
    model = Assortment
    template_name = 'technologist/assortments/list.html'
    context_object_name = 'assortments'
    paginate_by = 10
    def get_queryset(self):
        return super().get_queryset().order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context


@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentCreateView(AssignBranchMixin, CreateView):
    model = Assortment
    form_class = AssortmentForm
    template_name = 'technologist/assortments/create.html'
    def get_success_url(self):
        return reverse('model_list', kwargs={'a_id': self.object.id})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context


@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentDetailView(DetailView):
    model = Assortment
    template_name = 'technologist/assortments/detail.html'
    context_object_name = 'assortment'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentUpdateView(RestrictBranchMixin, UpdateView):
    model = Assortment
    form_class = AssortmentForm
    template_name = 'technologist/assortments/edit.html'
    def get_success_url(self):
        return reverse('assortment_detail', kwargs={'pk': self.kwargs.get('pk')})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentDeleteView(RestrictBranchMixin, DeleteView):
    model = Assortment
    template_name = 'technologist/assortments/delete.html'
    success_url = reverse_lazy('assortment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context



@method_decorator([login_required, technologist_required], name='dispatch')
class ModelListView(ListView):
    model = Model
    template_name = 'technologist/models/list.html'
    context_object_name = 'models'
    paginate_by = 10
    def get_queryset(self):
        assortment_id = self.kwargs.get('a_id')
        return Model.objects.filter(assortment=assortment_id).order_by('name')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['assortment'] = get_object_or_404(Assortment, pk=self.kwargs.get('a_id'))
        context['sidebar_type'] = 'technology'
        return context

@login_required
@technologist_required
def model_create(request, a_id, pk=None):
    assortment = get_object_or_404(Assortment, pk=a_id)
    copy_id = request.GET.get('copy')
    original = get_object_or_404(Model, pk=copy_id) if copy_id else None

    if request.method == 'POST':
        form = ModelCustomForm(request.POST, instance=None, a_id=a_id, copy_id=copy_id)
        if form.is_valid():
            form.save()
            return redirect('model_list', a_id=a_id)
    else:
        form = ModelCustomForm(instance=(original if copy_id else None), a_id=a_id, copy_id=copy_id)

    operations_order_json = ""
    if copy_id:
        operations_order = list(ModelOperation.objects.filter(model=original).order_by('order').values_list('operation_id', flat=True))
        operations_order_json = json.dumps(operations_order)

    template_name = 'technologist/models/edit.html' if original else 'technologist/models/create.html'
    context = {
        'form': form,
        'assortment': assortment,
        'is_copying': bool(copy_id),
        'copy_model': original if copy_id else None,
        'operations_order_json': operations_order_json,
        'sidebar_type' : 'technology',
    }
    return render(request, template_name, context)

@method_decorator([login_required, technologist_required], name='dispatch')
class ModelDetailView(DetailView):
    model = Model
    template_name = 'technologist/models/detail.html'
    context_object_name = 'model'

    def get_context_data(self, **kwargs):
        context = super(ModelDetailView, self).get_context_data(**kwargs)
        model = context['model']
        context['ordered_operations'] = model.operations.all().order_by('modeloperation__order')
        context['sidebar_type'] = 'technology'
        return context

@login_required
@technologist_required
def model_edit(request, a_id, pk):
    model_instance = get_object_or_404(Model, pk=pk)
    if request.method == 'POST':
        form = ModelCustomForm(request.POST, instance=model_instance)
        if form.is_valid():
            form.save()
            return redirect('model_list', a_id=a_id)
    else:
        form = ModelCustomForm(instance=model_instance)
        # Fetch and serialize operations order
        operations_order = list(ModelOperation.objects.filter(model=model_instance).order_by('order').values_list('operation_id', flat=True))
        operations_order_json = json.dumps(operations_order)

    return render(request, 'technologist/models/edit.html', {
        'form': form,
        'model': model_instance,
        'operations_order_json': operations_order_json
    })

@method_decorator([login_required, technologist_required], name='dispatch')
class ModelDeleteView(DeleteView):
    model = Model
    template_name = 'technologist/models/delete.html'
    def get_success_url(self):
        return reverse('model_list', kwargs={'a_id': self.kwargs.get('a_id')})



@method_decorator([login_required, technologist_required], name='dispatch')
class NodeListVIew(ListView):
    model = Node
    template_name = 'technologist/nodes/list.html'
    context_object_name = 'nodes'
    paginate_by = 10
    
    def get_queryset(self):
        return Node.objects.all().order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context


@method_decorator([login_required, technologist_required], name='dispatch')
class NodeCreateView(CreateView):
    model = Node
    form_class = NodeForm
    template_name = 'technologist/nodes/create.html'
    success_url = reverse_lazy('node_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeDetailView(DetailView):
    model = Node
    template_name = 'technologist/nodes/detail.html'
    context_object_name = 'node'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeUpdateView(UpdateView):
    model = Node
    form_class = NodeForm
    template_name = 'technologist/nodes/edit.html'
    success_url = reverse_lazy('node_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeDeleteView(DeleteView):
    model = Node
    template_name = 'technologist/nodes/delete.html'
    success_url = reverse_lazy('node_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context


@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentListView(ListView):
    model = Equipment
    template_name = 'technologist/equipment/list.html'
    context_object_name = 'equipment'
    paginate_by = 10

    def get_queryset(self):
        return Equipment.objects.all().order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context


@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentCreateView(CreateView):
    model = Equipment
    form_class = EquipmentForm
    template_name = 'technologist/equipment/create.html'
    success_url = reverse_lazy('equipment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentDetailView(DetailView):
    model = Equipment
    template_name = 'technologist/equipment/detail.html'
    context_object_name = 'equipment'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentUpdateView(UpdateView):
    model = Equipment
    form_class = EquipmentForm
    template_name = 'technologist/equipment/edit.html'
    success_url = reverse_lazy('equipment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentDeleteView(DeleteView):
    model = Equipment
    template_name = 'technologist/equipment/delete.html'
    success_url = reverse_lazy('equipment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context


@login_required
@technologist_required
def mark_as_qc(request, passport_size_id):
    try:
        passport_size = PassportSize.objects.get(id=passport_size_id)
        with transaction.atomic():
            if passport_size.stage == PassportSize.QC:
                passport_size.stage = PassportSize.SEWING
            else:
                passport_size.stage = PassportSize.QC
            passport_size.save()

        return JsonResponse({'success': True})

    except PassportSize.DoesNotExist:
        return JsonResponse({'error': 'PassportSize not found'}, status=404)
    
@login_required
@technologist_required
def update_assortment_name(request, pk):
    if request.method == 'POST':
        data = json.loads(request.body)
        assortment = Assortment.objects.get(pk=pk)
        assortment.name = data['name']
        assortment.save()
        return JsonResponse({'status': 'success', 'message': 'Assortment name updated successfully'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)
