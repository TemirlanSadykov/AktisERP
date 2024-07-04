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
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views.decorators.http import require_POST

from ..decorators import packer_required
from ..forms import *
from ..mixins import *
from ..models import *

CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@packer_required
def packer_page(request):
    context = {
        'sidebar_type': 'packer'
        }
    return render(request, 'packer_page.html' , context)

@method_decorator([login_required, packer_required], name='dispatch')
class OrderListPackerView(RestrictOrderBranchMixin, ListView):
    model = Order
    template_name = 'packer/orders/list.html'
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
        context['sidebar_type'] = 'packer'
        return context

@method_decorator([login_required, packer_required], name='dispatch')
class OrderDetailPackerView(DetailView):
    model = Order
    template_name = 'packer/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']
        passport = Passport.objects.filter(order=order).first()
        
        if passport:
            context['errors'] = Error.objects.filter(piece__passport_size__passport=passport, error_type=Error.ErrorType.DISCREPANCY)
        else:
            context['errors'] = Error.objects.none()

        today = timezone.localdate()
        days_left = (order.client_order.term - today).days if order.client_order.term >= today else 0
        context['days_left'] = days_left

        passports = order.passports.all()

        # Initialize data structures to track quantity and packed quantities
        size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'passport_size_id': None, 'packed_quantity': 0, 'extra': None}))
        total_per_size = defaultdict(int)

        for passport in passports:
            for passport_size in passport.passport_sizes.all():
                size = passport_size.size_quantity.size
                extra_key = f"{size}-{passport_size.extra}" if passport_size.extra else size
                size_data[extra_key][passport.id]['stage'] = passport_size.stage
                size_data[extra_key][passport.id]['quantity'] += passport_size.quantity
                size_data[extra_key][passport.id]['passport_size_id'] = passport_size.id
                size_data[extra_key][passport.id]['extra'] = passport_size.extra

                # Count packed pieces only
                packed_pieces = ProductionPiece.objects.filter(passport_size=passport_size, stage=ProductionPiece.StageChoices.PACKED).count()
                size_data[extra_key][passport.id]['packed_quantity'] += packed_pieces
                
                total_per_size[size] += passport_size.quantity

        required_missing = {sq.size: {'required': sq.quantity, 'missing': sq.quantity - total_per_size.get(sq.size, 0)}
                            for sq in order.size_quantities.all().order_by('size')}

        for size in total_per_size:
            if size not in required_missing:
                required_missing[size] = {'required': 0, 'missing': -total_per_size[size]}

        # Sorting size_data keys
        def sort_key(x):
            parts = x.split('-')
            try:
                return int(parts[0]), x
            except ValueError:
                return float('inf'), x

        sorted_size_data_keys = sorted(size_data.keys(), key=sort_key)

        context.update({
            'size_data': {k: dict(size_data[k]) for k in sorted_size_data_keys},
            'total_per_size': dict(total_per_size),
            'required_missing': required_missing,
            'passports': passports,
            'sidebar_type' : 'packer',
        })
        return context
    
@require_POST
@login_required
@packer_required
def update_piece_packer(request, piece_id):
    try:
        piece = ProductionPiece.objects.get(id=piece_id)
        
        if piece.stage == ProductionPiece.StageChoices.PACKED:
            return JsonResponse({'success': False, 'message': 'Piece is already packed.'}, status=409)
        elif piece.stage == ProductionPiece.StageChoices.DEFECT:
            return JsonResponse({'success': False, 'message': 'Piece is marked as defect.'}, status=409)
        elif piece.stage == ProductionPiece.StageChoices.NOT_CHECKED:
            return JsonResponse({'success': False, 'message': 'Piece is not checked and cannot be packed.'}, status=409)

        piece.stage = ProductionPiece.StageChoices.PACKED
        piece.save()

        Error.objects.filter(piece=piece, error_type=Error.ErrorType.DISCREPANCY).delete()

        size = f"{piece.passport_size.size_quantity.size}-{piece.passport_size.extra}" if piece.passport_size.extra else piece.passport_size.size_quantity.size

        # Forming the response with piece details
        data = {
            'success': True,
            'message': 'Piece status updated to Packed.',
            'piece_id': piece.id,
            'passport': piece.passport_size.passport.id,
            'order': piece.passport_size.passport.order.model.name,
            'passport_size': piece.passport_size.id,
            'size': size,
            'defect': piece.defect_type if piece.defect_type else "--",
            'stage': piece.get_stage_display()
        }
        return JsonResponse(data)

    except ProductionPiece.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Piece not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@method_decorator([login_required, packer_required], name='dispatch')
class DiscrepancyDetailView(DetailView):
    model = Error
    template_name = 'packer/discrepancies/detail.html'
    context_object_name = 'error'

@method_decorator([login_required, packer_required], name='dispatch')
class DiscrepancyDeleteView(DeleteView):
    model = Error

    def get_success_url(self):
        order_pk = self.kwargs['order_pk']
        return reverse_lazy('order_detail_packer', kwargs={'pk': order_pk})
    
@login_required
@packer_required
def mark_as_done(request, passport_size_id):
    try:
        passport_size = PassportSize.objects.get(id=passport_size_id)
        order = passport_size.passport.order
        operations = Operation.objects.filter(node__type=Node.PACKING, node__is_common=True)
        with transaction.atomic():
            if passport_size.stage == PassportSize.DONE:
                passport_size.stage = PassportSize.PACKING
                for operation in operations:
                    work = Work.objects.filter(passport_size=passport_size, operation=operation)
                    work.delete()
                order.completed_quantity -= passport_size.quantity
                order.save()
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
                passport_size.stage = PassportSize.DONE
                order.completed_quantity += passport_size.quantity
                order.save()
            passport_size.save()

        return JsonResponse({'success': True})

    except PassportSize.DoesNotExist:
        return JsonResponse({'error': 'PassportSize not found'}, status=404)
    
@login_required
@packer_required
@require_POST
def calculate_discrepancies(request, order_pk):
    try:
        order = Order.objects.get(pk=order_pk)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order does not exist'}, status=404)

    pieces = ProductionPiece.objects.filter(
        passport_size__passport__order=order,
        stage__in=[ProductionPiece.StageChoices.CHECKED, ProductionPiece.StageChoices.NOT_CHECKED]
    )

    discrepancies_created = 0

    for piece in pieces:
        error, created = Error.objects.get_or_create(
            piece=piece,
            error_type=Error.ErrorType.DISCREPANCY,
            defaults={
                'cost': piece.passport_size.passport.order.payment if piece.passport_size.passport.order.payment else 0,
                'status': Error.Status.REPORTED,
                'reported_date': timezone.now()
            }
        )
        if created:
            discrepancies_created += 1

    return JsonResponse({'success': True, 'discrepancies_created': discrepancies_created})

@login_required
@packer_required
def scan_packer_page(request):
    context = {
            'sidebar_type': 'packer'
            }
    return render(request, 'packer/scans/detail.html', context)