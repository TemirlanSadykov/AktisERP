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
from django.db.models import Q

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
        context['sidebar_type'] = 'packer'
        return context

# @method_decorator([login_required, packer_required], name='dispatch')
# class OrderDetailPackerView(DetailView):
#     model = Order
#     template_name = 'packer/orders/detail.html'
#     context_object_name = 'order'

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         order = context['order']
#         passport = Passport.objects.filter(order=order).first()
        
#         if passport:
#             context['errors'] = Error.objects.filter(piece__passport_size__passport=passport, error_type=Error.ErrorType.DISCREPANCY)
#         else:
#             context['errors'] = Error.objects.none()

#         today = timezone.localdate()
#         days_left = (order.client_order.term - today).days if order.client_order.term >= today else 0
#         context['days_left'] = days_left

#         passports = order.passports.all()

#         # Initialize data structures to track quantity and packed quantities
#         size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'passport_size_id': None, 'packed_quantity': 0, 'extra': None}))
#         total_per_size = defaultdict(int)

#         for passport in passports:
#             for passport_size in passport.passport_sizes.all():
#                 size = passport_size.size_quantity.size
#                 color = passport_size.size_quantity.color
#                 extra_key = f'{size} - {color}'
#                 size_data[extra_key][passport.id]['stage'] = passport_size.stage
#                 size_data[extra_key][passport.id]['quantity'] += passport_size.quantity
#                 size_data[extra_key][passport.id]['passport_size_id'] = passport_size.id
#                 size_data[extra_key][passport.id]['extra'] = passport_size.extra

#                 # Count packed pieces only
#                 packed_pieces = ProductionPiece.objects.filter(passport_size=passport_size, stage=ProductionPiece.StageChoices.PACKED).count()
#                 size_data[extra_key][passport.id]['packed_quantity'] += packed_pieces
                
#                 total_per_size[size] += passport_size.quantity

#         required_missing = {sq.size: {'required': sq.quantity, 'missing': sq.quantity - total_per_size.get(sq.size, 0)}
#                             for sq in order.size_quantities.all().order_by('size')}

#         for size in total_per_size:
#             if size not in required_missing:
#                 required_missing[size] = {'required': 0, 'missing': -total_per_size[size]}

#         # Sorting size_data keys
#         def sort_key(x):
#             parts = x.split('-')
#             try:
#                 return int(parts[0]), x
#             except ValueError:
#                 return float('inf'), x

#         sorted_size_data_keys = sorted(size_data.keys(), key=sort_key)

#         context.update({
#             'size_data': {k: dict(size_data[k]) for k in sorted_size_data_keys},
#             'total_per_size': dict(total_per_size),
#             'required_missing': required_missing,
#             'passports': passports,
#             'sidebar_type' : 'packer',
#         })
#         return context

@method_decorator([login_required, packer_required], name='dispatch')
class OrderDetailPackerView(DetailView):
    model = Order
    template_name = 'packer/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']

        # Data for the "Required Quantities" table
        required_data = []

        for sq in order.size_quantities.all().order_by('size'):
            key = f'{sq.size} - {sq.color}'
            required = sq.quantity

            # Add to required_data for the "Required Quantities" table
            required_data.append({
                'size': sq.size,
                'color': sq.color,
                'required': required,
            })

        # Get associated cuts for the order
        associated_cuts = order.cuts.all().order_by('-date')

        context.update({
            'required_data': required_data,  # Data for the "Required Quantities" table
            'days_left': (order.client_order.term - timezone.now().date()).days if order.client_order.term >= timezone.now().date() else 0,
            'associated_cuts': associated_cuts,  # Associated cuts to display
            'sidebar_type': 'packer'
        })

        return context
    
@method_decorator([login_required, packer_required], name='dispatch')
class CutDetailPackerView(DetailView):
    model = Cut
    template_name = 'packer/cuts/detail.html'
    context_object_name = 'cut'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cut_pk = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_pk)
        # Get all consumptions related to the cut
        consumptions = cut.consumptions.all()

        # Get all passports related to the cut
        passports = cut.passports.all()

        # Prepare the total quantities for each size in the cut
        total_quantity_per_size = defaultdict(int)
        for size_quantity in cut.size_quantities.all():
            total_quantity_per_size[f'{size_quantity.size} - {size_quantity.color}'] = size_quantity.quantity

        # Total quantity of layers (sum layers for all passports)
        total_layers = sum(passport.layers for passport in passports if passport.layers)

        context.update({
            'consumptions': consumptions,
            'passports': passports,
            'total_quantity_per_size': dict(total_quantity_per_size),
            'total_layers': total_layers,
            'sidebar_type': 'packer'
        })

        return context
    
@method_decorator([login_required, packer_required], name='dispatch')
class PassportDetailPackerView(DetailView):
    model = Passport
    template_name = 'packer/passports/detail.html'
    context_object_name = 'passport'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        passport = context['passport']
        context['passport_sizes'] = passport.passport_sizes.all().order_by('size_quantity__size')
        context['sidebar_type'] = 'packer'
        return context

@require_POST
@login_required
@packer_required
def update_piece_packer(request, piece_id):
    try:
        piece = ProductionPiece.objects.get(id=piece_id)
        
        # Check conditions for packing
        if piece.stage == ProductionPiece.StageChoices.PACKED:
            return JsonResponse({'success': False, 'message': 'Единица уже упакована.'}, status=409)
        elif piece.stage == ProductionPiece.StageChoices.DEFECT:
            return JsonResponse({'success': False, 'message': 'Единица бракована.'}, status=409)
        elif piece.stage == ProductionPiece.StageChoices.NOT_CHECKED:
            return JsonResponse({'success': False, 'message': 'Единица еще не проверена.'}, status=409)

        # Update piece status to PACKED
        piece.stage = ProductionPiece.StageChoices.PACKED
        piece.save()

        # Delete discrepancy errors related to this piece
        Error.objects.filter(piece=piece, error_type=Error.ErrorType.DISCREPANCY).delete()

        # Fetch the Packing operation
        packing_operation = Operation.objects.filter(node__type=Node.PACKING).first()
        
        if packing_operation:
            # Create or update the assigned work entry
            work, created = Work.objects.get_or_create(
                passport_size=piece.passport_size,
                operation=packing_operation
            )

            # Check if an AssignedWork already exists for the user and work
            assigned_work = AssignedWork.objects.filter(
                work=work,
                employee=request.user.userprofile
            ).first()

            if assigned_work:
                # Increment quantity if assigned work already exists
                assigned_work.quantity += 1
                assigned_work.save()
            else:
                # Create a new assigned work with quantity 1
                AssignedWork.objects.create(
                    work=work,
                    employee=request.user.userprofile,
                    quantity=1,
                    start_time=timezone.now(),
                    end_time=timezone.now(),
                    is_success=False
                )

        # Prepare response data
        size = f"{piece.passport_size.size_quantity.size}-{piece.passport_size.extra}" if piece.passport_size.extra else piece.passport_size.size_quantity.size
        cut = piece.passport_size.passport.cut.number
        model = piece.passport_size.passport.cut.order.model.name
        color = piece.passport_size.passport.roll.color.name
        fabrics = piece.passport_size.passport.roll.fabrics.name
        passport_id = piece.passport_size.passport.id
        passport_number = piece.passport_size.passport.number
        
        # Forming the response with piece details
        data = {
            'success': True,
            'message': 'Piece status updated to Packed.',
            'piece_id': piece.id,
            'piece_number': piece.piece_number,
            'passport_id': passport_id,
            'passport_number': passport_number,
            'cut': cut,
            'model': model,
            'color': color,
            'fabrics': fabrics,
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
        order = passport_size.passport.cut.order
        assigned_works = AssignedWork.objects.filter(work__passport_size=passport_size)

        with transaction.atomic():
            if passport_size.stage == PassportSize.DONE:
                # Change the status to PACKING and update assigned_work is_success to False
                passport_size.stage = PassportSize.PACKING
                assigned_works.update(is_success=False)
                
                # Decrement the completed_quantity for the order
                order.completed_quantity -= passport_size.quantity
            else:
                # Change the status to DONE and update assigned_work is_success to True
                passport_size.stage = PassportSize.DONE
                assigned_works.update(is_success=True)
                
                # Increment the completed_quantity for the order
                order.completed_quantity += passport_size.quantity

            # Save the updated stage and order
            passport_size.save()
            order.save()

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