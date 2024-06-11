from collections import defaultdict

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from barcode import Code128
from barcode.writer import ImageWriter
from django.http import HttpResponse
from django.shortcuts import render
from io import BytesIO
from django.views.decorators.http import require_POST

from ..decorators import qc_required
from ..forms import *
from ..mixins import *
from ..models import *

CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@qc_required
def qc_page(request):
    context = {
            'sidebar_type': 'qc_page'
            }
    return render(request, 'qc_page.html', context)

@method_decorator([login_required, qc_required], name='dispatch')
class OrderListQcView(RestrictOrderBranchMixin, ListView):
    model = Order
    template_name = 'qc/orders/list.html'
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
        context['Order'] = Order
        context['selected_status'] = self.request.GET.get('status', '')
        context['orders_with_days_left'] = orders_with_days_left_sorted
        context['sidebar_type'] = 'qc_page'
        return context

@method_decorator([login_required, qc_required], name='dispatch')
class OrderDetailQcView(DetailView):
    model = Order
    template_name = 'qc/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']
        passport = Passport.objects.filter(order=order).first()
        if passport:
            context['errors'] = Error.objects.filter(passport=passport, error_type=Error.ErrorType.DEFECT)
        else:
            context['errors'] = Error.objects.none()
        
        passports = order.passports.all()

        # Extended defaultdict to track checked quantity
        size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'passport_size_id': None, 'stage': None, 'checked_quantity': 0}))
        total_per_size = defaultdict(int)

        for passport in passports:
            for passport_size in passport.passport_sizes.all():
                size = passport_size.size_quantity.size
                size_data[size][passport.id]['quantity'] += passport_size.quantity
                size_data[size][passport.id]['passport_size_id'] = passport_size.id
                size_data[size][passport.id]['stage'] = passport_size.stage

                # Counting checked pieces
                checked_pieces = ProductionPiece.objects.filter(passport_size=passport_size, stage=ProductionPiece.StageChoices.CHECKED).count()
                size_data[size][passport.id]['checked_quantity'] += checked_pieces
                
                total_per_size[size] += passport_size.quantity

        required_missing = {sq.size: {'required': sq.quantity, 'missing': sq.quantity - total_per_size.get(sq.size, 0)}
                            for sq in order.size_quantities.all().order_by('size')}

        # Adjusting for sizes in passports not in order sizes
        for size in total_per_size:
            if size not in required_missing:
                required_missing[size] = {'required': 0, 'missing': -total_per_size[size]}

        context.update({
            'size_data': {k: dict(v) for k, v in size_data.items()},
            'total_per_size': dict(total_per_size),
            'required_missing': required_missing,
            'passports': passports,
            'days_left': (order.client_order.term - timezone.now().date()).days if order.client_order.term >= timezone.now().date() else 0,
            'sidebar_type' : 'qc_page'
        })

        return context
    
@login_required
@qc_required
def get_piece_info(request, barcode):
    try:
        # Split the barcode and extract the piece ID
        parts = barcode.split('-')
        if len(parts) != 3:
            return JsonResponse({'error': 'Invalid barcode format'}, status=400)

        piece_id = parts[2]  # Assuming the last part is the piece ID
        piece = ProductionPiece.objects.get(id=piece_id)  # Fetch the piece using the extracted ID

        data = {
            'piece_id': piece.id,
            'passport': piece.passport_size.passport.id,
            'passport_size': piece.passport_size.id,
            'size': piece.passport_size.size_quantity.size,
            'defect': piece.defect_type if piece.defect_type else "--",
            'stage': piece.get_stage_display(),
        }
        return JsonResponse(data)
    except ProductionPiece.DoesNotExist:
        return JsonResponse({'error': 'Piece not found'}, status=404)

    except ValueError:
        return JsonResponse({'error': 'Error processing barcode'}, status=500)
    
@require_POST
@login_required
@qc_required
def update_piece_qc(request, piece_id):
    try:
        data = json.loads(request.body)
        status = data.get('status')
        defect_type = data.get('defectType', None)  # Retrieve defect type if provided

        valid_statuses = {
            'Checked': ProductionPiece.StageChoices.CHECKED,
            'Defect': ProductionPiece.StageChoices.DEFECT
        }
        
        if status not in valid_statuses:
            return JsonResponse({'success': False, 'message': 'Invalid status provided.'}, status=400)

        piece = ProductionPiece.objects.get(id=piece_id)
        piece.stage = valid_statuses[status]

        if status == 'Defect' and defect_type in [choice[0] for choice in ProductionPiece.DefectType.choices]:
            piece.defect_type = defect_type
            piece.save()

            # Create an Error instance if a defect is reported
            error = Error.objects.create(
                error_type=Error.ErrorType.DEFECT,
                defect_type=defect_type,
                cost=piece.passport_size.passport.order.payment if piece.passport_size.passport.order.payment else 0,
                passport=piece.passport_size.passport,
                size_quantity=piece.passport_size.size_quantity,
                quantity=1,
                status=Error.Status.REPORTED,
                reported_date=timezone.now()
            )
            return JsonResponse({'success': True, 'message': f'Piece status updated to {status} with defect type {defect_type}. Error record created.'})

        elif status == 'Defect' and not defect_type:
            return JsonResponse({'success': False, 'message': 'Defect type required for defect status.'}, status=400)
        else:
            piece.save()
            return JsonResponse({'success': True, 'message': f'Piece status updated to {status}.'})
        
    except ProductionPiece.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Piece not found.'}, status=404)
    except KeyError:
        return JsonResponse({'success': False, 'message': 'Status or defect type not provided in request.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@method_decorator([login_required, qc_required], name='dispatch')
class DefectCreateView(CreateView):
    model = Error
    form_class = ErrorForm
    template_name = 'qc/defects/create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        order_pk = self.kwargs.get('order_pk')
        kwargs['order_pk'] = order_pk
        kwargs['error_type'] = 'DEFECT'
        return kwargs

    def form_valid(self, form):
        order = get_object_or_404(Order, pk=self.kwargs['order_pk'])
        form.instance.order = order
        unit_price = getattr(order, 'payment', None)
        quantity = getattr(form.instance, 'quantity', None)
        if unit_price is not None and quantity is not None:
            form.instance.cost = unit_price * quantity
        return super().form_valid(form)

    def get_success_url(self):
        order_pk = self.kwargs['order_pk']
        return reverse_lazy('order_detail_qc', kwargs={'pk': order_pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order_pk = self.kwargs['order_pk']
        context['order'] = get_object_or_404(Order, pk=order_pk)
        context['sidebar_type'] = 'qc_page'
        return context

@method_decorator([login_required, qc_required], name='dispatch')
class DefectDetailView(DetailView):
    model = Error 
    template_name = 'qc/defects/detail.html'  
    context_object_name = 'error'

@method_decorator([login_required, qc_required], name='dispatch')
class DefectUpdateView(UpdateView):
    model = Error 
    form_class = ErrorForm
    template_name = 'qc/defects/edit.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        order_pk = self.kwargs.get('order_pk')
        kwargs['order_pk'] = order_pk
        kwargs['error_type'] = 'DEFECT'
        return kwargs

    def get_success_url(self):
        order_pk = self.kwargs['order_pk']
        return reverse_lazy('order_detail_qc', kwargs={'pk': order_pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        error_pk = self.kwargs['pk']
        context['error'] = get_object_or_404(Error, pk=error_pk)
        context['sidebar_type'] = 'qc_page'
        return context

@method_decorator([login_required, qc_required], name='dispatch')
class DefectDeleteView(DeleteView):
    model = Error

    def get_success_url(self):
        order_pk = self.kwargs['order_pk']
        return reverse_lazy('order_detail_qc', kwargs={'pk': order_pk})
    
@login_required
@qc_required
def mark_as_packing(request, passport_size_id):
    try:
        passport_size = PassportSize.objects.get(id=passport_size_id)
        operations = Operation.objects.filter(node__type=Node.QC)
        with transaction.atomic():
            if passport_size.stage == PassportSize.PACKING:
                passport_size.stage = PassportSize.QC
                for operation in operations:
                    work = Work.objects.filter(passport_size=passport_size, operation=operation)
                    work.delete()
            else:
                for operation in operations:
                    work = Work.objects.create(
                        operation=operation,
                        passport=passport_size.passport,
                        passport_size=passport_size
                    )
                    AssignedWork.objects.create(
                        work=work,
                        employee=operation.employee,
                        quantity=passport_size.quantity,
                        start_time=timezone.now(),
                        end_time=timezone.now(),
                        is_success=True
                    )
                passport_size.stage = PassportSize.PACKING
            passport_size.save()

        return JsonResponse({'success': True})

    except PassportSize.DoesNotExist:
        return JsonResponse({'error': 'PassportSize not found'}, status=404)
