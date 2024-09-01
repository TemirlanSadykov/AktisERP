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
from django.db.models import Q

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
        search_query = self.request.GET.get('search', None)
        queryset = super().get_queryset().order_by('client_order__term')

        if status:
            try:
                status = int(status)
                if status in dict(self.model.TYPE_CHOICES):
                    queryset = queryset.filter(status=status)
            except ValueError:
                pass

        if search_query:
            queryset = queryset.filter(
                Q(model__name__icontains=search_query) |
                Q(color__icontains=search_query) |
                Q(fabrics__icontains=search_query)
            )
            
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
        context['search_query'] = self.request.GET.get('search', '')
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
            context['errors'] = Error.objects.filter(piece__passport_size__passport=passport, error_type=Error.ErrorType.DEFECT)
        else:
            context['errors'] = Error.objects.none()
        
        passports = order.passports.all()

        # Extended defaultdict to track checked quantity
        size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'passport_size_id': None, 'stage': None, 'checked_quantity': 0, 'extra': None}))
        total_per_size = defaultdict(int)

        for passport in passports:
            for passport_size in passport.passport_sizes.all():
                size = passport_size.size_quantity.size
                roll = passport_size.roll.name
                extra_key = f'{size} - {roll}'
                size_data[extra_key][passport.id]['quantity'] += passport_size.quantity
                size_data[extra_key][passport.id]['passport_size_id'] = passport_size.id
                size_data[extra_key][passport.id]['stage'] = passport_size.stage
                size_data[extra_key][passport.id]['extra'] = passport_size.extra

                # Counting checked pieces
                checked_pieces = ProductionPiece.objects.filter(passport_size=passport_size, stage__in=[ProductionPiece.StageChoices.CHECKED, ProductionPiece.StageChoices.PACKED]).count()
                size_data[extra_key][passport.id]['checked_quantity'] += checked_pieces
                
                total_per_size[size] += passport_size.quantity

        required_missing = {sq.size: {'required': sq.quantity, 'missing': sq.quantity - total_per_size.get(sq.size, 0)}
                            for sq in order.size_quantities.all().order_by('size')}

        # Adjusting for sizes in passports not in order sizes
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

        size = f"{piece.passport_size.size_quantity.size}-{piece.passport_size.extra}" if piece.passport_size.extra else piece.passport_size.size_quantity.size

        data = {
            'piece_id': piece.id,
            'passport': piece.passport_size.passport.id,
            'order': piece.passport_size.passport.order.model.name,
            'passport_size': piece.passport_size.id,
            'size': size,
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
        defect_type = data.get('defectType', None)

        valid_statuses = {
            'Checked': ProductionPiece.StageChoices.CHECKED,
            'Defect': ProductionPiece.StageChoices.DEFECT
        }
        
        if status not in valid_statuses:
            return JsonResponse({'success': False, 'message': 'Invalid status provided.'}, status=400)

        piece = ProductionPiece.objects.get(id=piece_id)
        piece.stage = valid_statuses[status]

        if status == 'Defect':
            if defect_type in [choice[0] for choice in ProductionPiece.DefectType.choices]:
                piece.defect_type = defect_type
                piece.save()

                error, created = Error.objects.update_or_create(
                    piece=piece,
                    error_type=Error.ErrorType.DEFECT,
                    defaults={
                        'cost': piece.passport_size.passport.order.payment if piece.passport_size.passport.order.payment else 0,
                        'status': Error.Status.REPORTED,
                        'reported_date': timezone.now()
                    }
                )

                message = f'Piece status updated to {status} with defect type {defect_type}. {"Error record created." if created else "Error record updated."}'
                return JsonResponse({'success': True, 'message': message})

            else:
                return JsonResponse({'success': False, 'message': 'Invalid defect type provided for defect status.'}, status=400)
        
        else:
            piece.defect_type = None
            piece.save()
            Error.objects.filter(piece=piece, error_type=Error.ErrorType.DEFECT).delete()
            return JsonResponse({'success': True, 'message': f'Piece status updated to {status}. Any related error records have been removed.'})
        
    except ProductionPiece.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Piece not found.'}, status=404)
    except KeyError:
        return JsonResponse({'success': False, 'message': 'Status or defect type not provided in request.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@method_decorator([login_required, qc_required], name='dispatch')
class DefectDetailView(DetailView):
    model = Error 
    template_name = 'qc/defects/detail.html'  
    context_object_name = 'error'

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
        operations = Operation.objects.filter(node__type=Node.QC, node__is_common=True)
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

@login_required
@qc_required
def scan_qc_page(request):
    context = {
            'sidebar_type': 'qc_page'
            }
    return render(request, 'qc/scans/detail.html', context)