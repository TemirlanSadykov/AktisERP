from collections import defaultdict
from decimal import Decimal
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView, CreateView
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q

from ..decorators import cutter_required
from ..forms import *
from ..mixins import *
from ..models import *

CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@cutter_required
def cutter_page(request):
    context = {
            'sidebar_type': 'cutter'
            }
    return render(request, 'cutter_page.html', context)

@method_decorator([login_required, cutter_required], name='dispatch')
class OrderListCutterView(RestrictOrderBranchMixin, ListView):
    model = Order
    template_name = 'cutter/orders/list.html'
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

        context['orders_with_days_left'] = orders_with_days_left_sorted
        context['selected_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('search', '')
        context['Order'] = Order
        context['sidebar_type'] = 'cutter'
        return context

@method_decorator([login_required, cutter_required], name='dispatch')
class OrderDetailCutterView(DetailView):
    model = Order
    template_name = 'cutter/orders/detail.html'
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
            'sidebar_type': 'cutter'
        })

        return context
    
@method_decorator([login_required, cutter_required], name='dispatch')
class CutCreateView(CreateView):
    model = Cut
    form_class = CutForm
    template_name = 'cutter/cuts/create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        order_id = self.kwargs.get('pk')
        order = get_object_or_404(Order, pk=order_id)
        kwargs['order'] = order  # Pass order to the form
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order_id = self.kwargs.get('pk')
        order = get_object_or_404(Order, pk=order_id)
        context['order'] = order
        context['sidebar_type'] = 'cutter'
        return context

    def form_valid(self, form):
        order_id = self.kwargs.get('pk')
        order = get_object_or_404(Order, pk=order_id)
        cut = form.save(commit=False)
        cut.order = order
        cut.save()
        form.save_m2m()
        return redirect('consumption_create', pk=cut.pk)

    def get_success_url(self):
        return reverse('cut_create', kwargs={'pk': self.kwargs['pk']})
    
@method_decorator([login_required, cutter_required], name='dispatch')
class CutDetailView(DetailView):
    model = Cut
    template_name = 'cutter/cuts/detail.html'
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
            'sidebar_type': 'cutter'
        })

        return context
    
@method_decorator([login_required, cutter_required], name='dispatch')
class ConsumptionCreateView(CreateView):
    model = Consumption
    form_class = ConsumptionForm
    template_name = 'cutter/consumptions/create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        cut_id = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_id)
        kwargs['cut'] = cut
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cut_id = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_id)
        context['cut'] = cut
        context['sidebar_type'] = 'cutter'
        return context

    def form_valid(self, form):
        cut_id = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_id)
        consumption = form.save(commit=False)
        consumption.cut = cut
        consumption.save()
        return redirect(self.request.path)

    def get_success_url(self):
        return reverse('consumption_create', kwargs={'pk': self.kwargs['pk']})
    
@login_required
@cutter_required
def delete_consumption(request, pk):
    if request.method == 'POST':
        consumption = get_object_or_404(Consumption, pk=pk)
        consumption.delete()
        return JsonResponse({'status': 'success'}, status=200)
    return JsonResponse({'status': 'error'}, status=400)
  
@method_decorator([login_required, cutter_required], name='dispatch')
class PassportCreateView(CreateView):
    model = Passport
    form_class = PassportForm
    template_name = 'cutter/passports/create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        cut_id = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_id)
        kwargs['cut'] = cut  # Pass the cut to the form
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cut_id = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_id)
        context['cut'] = cut
        context['sidebar_type'] = 'cutter'
        return context

    def form_valid(self, form):
        cut_id = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_id)
        passport = form.save(commit=False)

        # Generate passport number starting from 1 for each cut
        last_passport = Passport.objects.filter(cut=cut).order_by('number').last()
        passport.number = last_passport.number + 1 if last_passport else 1

        passport.cut = cut

        # Fetch the selected roll and reduce its available meters
        roll = passport.roll
        meters_requested = passport.meters

        # Check if the roll has enough available meters
        if roll.available_meters is not None and roll.available_meters >= meters_requested:
            roll.used_meters += meters_requested  # Update used meters
            roll.save()  # Save the updated roll

            passport.save()  # Save the passport instance

            # Automatically create PassportSize for each size_quantity in the cut
            for size_quantity in cut.size_quantities.filter(color=roll.color):
                passport_size = PassportSize.objects.create(
                    passport=passport,
                    size_quantity=size_quantity,
                    quantity=form.cleaned_data['layers'],  # Layers from form input
                    stage=0,  # Default to CUTTING
                    extra=''  # Extra left empty
                )
                
                quantity = int(passport_size.quantity)

                # Generate ProductionPiece for each PassportSize based on quantity
                for i in range(1, quantity + 1):
                    ProductionPiece.objects.create(
                        passport_size=passport_size,
                        piece_number=i
                    )

            return redirect(self.get_success_url())
        else:
            form.add_error('meters', 'Not enough available meters on the selected roll.')
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('passport_create', kwargs={'pk': self.kwargs['pk']})
    
@method_decorator([login_required, cutter_required], name='dispatch')
class PassportDetailView(DetailView):
    model = Passport
    template_name = 'cutter/passports/detail.html'
    context_object_name = 'passport'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        passport = context['passport']
        context['passport_sizes'] = passport.passport_sizes.all().order_by('size_quantity__size')
        context['sidebar_type'] = 'cutter'
        return context
    
@login_required
@cutter_required
def delete_passport(request, pk):
    if request.method == 'POST':
        passport = get_object_or_404(Passport, pk=pk)
        passport.delete()
        return JsonResponse({'status': 'success'}, status=200)
    return JsonResponse({'status': 'error'}, status=400)

# @method_decorator([login_required, cutter_required], name='dispatch')
# class PassportSizeCreateView(CreateView):
#     model = PassportSize
#     form_class = PassportSizeForm
#     template_name = 'cutter/passports/create_passport_size_quantity.html'

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         passport_id = self.kwargs.get('passport_id')
#         passport = get_object_or_404(Passport, pk=passport_id)
#         context['passport'] = passport
#         context['passport_sizes'] = PassportSize.objects.filter(passport=passport).order_by('size_quantity__size')
#         context['sidebar_type'] = 'cutter'
#         return context

#     def get_form_kwargs(self):
#         kwargs = super().get_form_kwargs()
#         passport_id = self.kwargs.get('passport_id')
#         kwargs['passport_id'] = passport_id
#         return kwargs

#     def form_valid(self, form):
#         passport_id = self.kwargs['passport_id']
#         passport = get_object_or_404(Passport, pk=passport_id)
#         passport_size = form.save(commit=False)
#         passport_size.passport = passport

#         # Check if the size_quantity already exists
#         existing_sizes = PassportSize.objects.filter(passport=passport, size_quantity=passport_size.size_quantity)
#         if existing_sizes.exists():
#             # Generate an 'extra' letter (A-Z)
#             used_extras = [ps.extra for ps in existing_sizes if ps.extra]
#             new_extra = self.generate_new_extra(used_extras)
#             passport_size.extra = new_extra

#         passport_size.save()

#         for i in range(1, passport_size.quantity + 1):
#             ProductionPiece.objects.create(
#                 passport_size=passport_size,
#                 piece_number=i,
#                 stage=ProductionPiece.StageChoices.NOT_CHECKED
#             )

#         return redirect(self.get_success_url())

#     def generate_new_extra(self, used_extras):
#         available_extras = [chr(i) for i in range(65, 91)]  # A-Z
#         for extra in available_extras:
#             if extra not in used_extras:
#                 return extra
#         raise ValueError("All extra letters (A-Z) are used for this size_quantity.")

#     def get_success_url(self):
#         return reverse('create_passport_size', kwargs={'passport_id': self.kwargs['passport_id']})
    
# @login_required
# @cutter_required
# @require_POST
# def edit_passport_size_quantity(request, sq_id):
#     try:
#         # Convert JSON data to Python dictionary
#         data = json.loads(request.body)
#         quantity = int(data.get('quantity'))
        
#         # Find the PassportSize instance
#         passport_size = PassportSize.objects.get(id=sq_id)
#         # Update the quantity
#         passport_size.quantity = quantity
#         passport_size.save()

#         # Return success response
#         return JsonResponse({'status': 'success', 'message': 'Quantity updated successfully'})
    
#     except PassportSize.DoesNotExist:
#         return JsonResponse({'status': 'error', 'message': 'PassportSize not found'}, status=404)
    
#     except Exception as e:
#         # Handle unexpected errors
#         return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# @login_required
# @cutter_required
# @require_POST
# def delete_passport_size_quantity(request, sq_id):
#     passport_size = get_object_or_404(PassportSize, id=sq_id)
#     passport_size.delete()
#     return JsonResponse({'status': 'success'}, status=200)

# @method_decorator([login_required, cutter_required], name='dispatch')
# class PassportDetailView(DetailView):
#     model = Passport
#     template_name = 'cutter/passports/detail.html'
#     context_object_name = 'passport'

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         passport = context['passport']
#         context['passport_sizes'] = passport.passport_sizes.all().order_by('size_quantity__size')
#         context['passport_rolls'] = passport.passport_rolls.all()
#         context['sidebar_type'] = 'cutter'
#         return context

# @login_required
# @cutter_required
# @require_POST
# def passport_delete(request, passport_id):
#     passport = get_object_or_404(Passport, id=passport_id)
#     order = passport.order
#     client_order = order.client_order

#     with transaction.atomic():
#         if passport.is_completed:
#             total_quantity = PassportSize.objects.filter(passport=passport).aggregate(Sum('quantity'))['quantity__sum'] or 0

#             if order.completed_quantity is not None:
#                 order.completed_quantity -= total_quantity
#                 order.save()

#         passport_rolls = PassportRoll.objects.filter(passport=passport)
#         for passport_roll in passport_rolls:
#             roll = passport_roll.roll
#             if roll.used_meters is not None:
#                 roll.used_meters -= passport_roll.meters
#                 roll.save()

#         passport.delete()
#         messages.success(request, 'Passport deleted successfully.')

#         remaining_passports = Passport.objects.filter(order=order).exists()
#         if not remaining_passports:
#             order.status = Order.NEW
#             order.save()
#             messages.info(request, 'Order status set to NEW due to no remaining passports.')

#         other_in_progress_orders = Order.objects.filter(client_order=client_order, status=Order.IN_PROGRESS).exists()
#         if not other_in_progress_orders:
#             client_order.status = ClientOrder.NEW
#             client_order.save()
#             messages.info(request, 'ClientOrder status set to NEW as no other orders are IN PROGRESS.')

#     return redirect(reverse('order_detail_cutter', args=[order.id]))

@login_required
@cutter_required
def mark_as_sewing(request, passport_size_id):
    try:
        passport_size = PassportSize.objects.get(id=passport_size_id)
        operations = Operation.objects.filter(node__type=Node.CUTTING, node__is_common=True) # Work for Employees type Cutter
        with transaction.atomic():
            if passport_size.stage == PassportSize.SEWING:
                passport_size.stage = PassportSize.CUTTING
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
                passport_size.stage = PassportSize.SEWING
            passport_size.save()

        return JsonResponse({'success': True})

    except PassportSize.DoesNotExist:
        return JsonResponse({'error': 'PassportSize not found'}, status=404)