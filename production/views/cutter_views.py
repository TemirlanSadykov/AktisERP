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
from django.views.generic import ListView, DetailView, CreateView, DeleteView, UpdateView
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
class ClientOrderListCutterView(RestrictBranchMixin, ListView):
    model = ClientOrder
    template_name = 'cutter/client/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 10
    form_class = DateRangeForm 

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_archived=False)
        today = timezone.localdate()

        # Get the term filter from the URL, defaulting to upcoming if not provided
        term_filter = self.request.GET.get('term', 'upcoming').lower()

        if term_filter == 'upcoming':
            # Orders with a term today or later, ordered by the soonest term first.
            queryset = queryset.filter(term__gte=today).order_by('term')
        elif term_filter == 'passed':
            # Orders with a term before today, ordered so that the most recent passed comes first.
            queryset = queryset.filter(term__lt=today).order_by('-term')
        else:
            # If for some reason the parameter is not recognized, default to upcoming.
            queryset = queryset.filter(term__gte=today).order_by('term')

        # Optionally filter by the created_at date range using your DateRangeForm
        form = self.form_class(self.request.GET)
        if form.is_valid():
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')
            if start_date and end_date:
                queryset = queryset.filter(launch__range=[start_date, end_date])
            elif start_date:
                queryset = queryset.filter(launch__gte=start_date)
            elif end_date:
                queryset = queryset.filter(launch__lte=end_date)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form_class(self.request.GET or None)
        today = timezone.localdate()

        # Prepare orders along with the number of days left (which will be negative for passed orders)
        orders_with_days_left = []
        for order in context['orders']:
            days_left = (order.term - today).days
            orders_with_days_left.append({'order': order, 'days_left': days_left})
        context['orders_with_days_left'] = orders_with_days_left

        # Pass the active filter to the template (default to 'upcoming')
        context['term_filter'] = self.request.GET.get('term', 'upcoming').lower()
        context['ClientOrder'] = ClientOrder 
        context['sidebar_type'] = 'cutter'
        return context
    
@method_decorator([login_required, cutter_required], name='dispatch')
class ClientOrderDetailCutterView(DetailView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'cutter/client/orders/detail.html'
    context_object_name = 'client_order'

    def get_context_data(self, **kwargs):
        context = super(ClientOrderDetailCutterView, self).get_context_data(**kwargs)
        client_order = context['client_order']
        context['orders'] = client_order.orders.all()
        today = timezone.localdate()
        if client_order.term >= today:
            days_left = (client_order.term - today).days
        else:
            days_left = 0
        context['days_left'] = days_left
        context['sidebar_type'] = 'cutter'
        return context

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

        queryset = queryset.filter(client_order__is_archived=False)

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

        # ----- Build pivot data for "Required Quantities" table -----
        # We'll use order.size_quantities.all() (assumed to include both color and fabric)
        required_qs = order.size_quantities.all().order_by('size')
        pivot_data = {}  # keys: (color, fabric), value: {size: quantity}
        all_sizes_set = set()
        for sq in required_qs:
            # Collect the size (header) value.
            all_sizes_set.add(sq.size)
            # Use a tuple (color, fabric) as the key.
            key = (sq.color, sq.fabrics)  # Adjust field names if needed.
            if key not in pivot_data:
                pivot_data[key] = {}
            pivot_data[key][sq.size] = sq.quantity

        # Sort sizes. (If sizes are numeric strings, convert to int for sorting.)
        try:
            all_sizes = sorted(all_sizes_set, key=lambda s: int(s))
        except ValueError:
            all_sizes = sorted(all_sizes_set)

        # ----- Other context data (pass along your existing context) -----
        associated_cuts = order.cuts.all().order_by('number')
        passports = Passport.objects.filter(cut__in=associated_cuts).order_by('cut__number', 'number')
        size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'passport_size_id': None, 'stage': None, 'extra': None}))
        total_per_size = defaultdict(int)
        for passport in passports:
            passport_number = passport.id
            for passport_size in passport.passport_sizes.all():
                size = passport_size.size_quantity.size
                extra_key = f"{size}-{passport_size.extra}" if passport_size.extra else size
                size_data[extra_key][passport_number]['quantity'] += passport_size.quantity
                size_data[extra_key][passport_number]['passport_size_id'] = passport_size.id
                size_data[extra_key][passport_number]['stage'] = passport_size.stage
                size_data[extra_key][passport_number]['extra'] = passport_size.extra
                total_per_size[size] += passport_size.quantity

        required_missing = {sq.size: {'required': sq.quantity, 'missing': sq.quantity - total_per_size.get(sq.size, 0)}
                            for sq in order.size_quantities.all().order_by('size')}
        for size in total_per_size:
            if size not in required_missing:
                required_missing[size] = {'required': 0, 'missing': -total_per_size[size]}

        def sort_key(x):
            parts = x.split('-')
            try:
                return int(parts[0]), x
            except ValueError:
                return float('inf'), x
        sorted_size_data_keys = sorted(size_data.keys(), key=sort_key)

        context.update({
            'pivot_data': pivot_data,  # Our new pivoted required data
            'all_sizes': all_sizes,    # List of sizes for the header row
            # (Include your other context items as before.)
            'size_data': {k: dict(size_data[k]) for k in sorted_size_data_keys},
            'total_per_size': dict(total_per_size),
            'required_missing': required_missing,
            'days_left': (order.client_order.term - timezone.now().date()).days if order.client_order.term >= timezone.now().date() else 0,
            'associated_passports': passports,
            'associated_cuts': associated_cuts,
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
        kwargs['order'] = order
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
        form.save_cut_sizes(cut)  # Save sizes and quantities to CutSize
        return redirect('passport_create', pk=cut.pk)

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

        # Get all passports related to the cut
        passports = cut.passports.all()

        # Prepare the total quantities for each size in the cut
        total_quantity_per_size = defaultdict(int)
        for size_quantity in cut.size_quantities.all():
            total_quantity_per_size[f'{size_quantity.size} - {size_quantity.color}'] = size_quantity.quantity

        # Total quantity of layers (sum layers for all passports)
        total_layers = sum(passport.layers for passport in passports if passport.layers)

        context.update({
            'passports': passports,
            'total_quantity_per_size': dict(total_quantity_per_size),
            'total_layers': total_layers,
            'sidebar_type': 'cutter'
        })

        return context
    
@method_decorator([login_required, cutter_required], name='dispatch')
class CutEditView(UpdateView):
    model = Cut
    form_class = CutForm
    template_name = 'cutter/cuts/edit.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        order_id = self.object.order.pk  # Get order from the existing cut object
        order = get_object_or_404(Order, pk=order_id)
        kwargs['order'] = order  # Pass the order to the form
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order_id = self.object.order.pk  # Get order from the existing cut object
        order = get_object_or_404(Order, pk=order_id)
        context['order'] = order
        context['sidebar_type'] = 'cutter'
        return context

    def get_success_url(self):
        return reverse('cut_detail', kwargs={'pk': self.object.pk})
    
@method_decorator([login_required, cutter_required], name='dispatch')
class CutDeleteView(DeleteView):
    model = Cut
    def get_success_url(self):
        return reverse('order_detail_cutter', kwargs={'pk': self.object.order.pk})
  
@method_decorator([login_required, cutter_required], name='dispatch')
class PassportCreateView(CreateView):
    model = Passport
    form_class = PassportForm
    template_name = 'cutter/passports/create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        cut_id = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_id)
        kwargs['cut'] = cut  # Pass the cut to the form so it can build the combo choices.
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cut_id = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_id)
        context['cut'] = cut
        context['passports'] = cut.passports.all().order_by('-number')
        context['sidebar_type'] = 'cutter'
        return context

    def form_valid(self, form):
        cut_id = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_id)
        passport = form.save(commit=False)

        # Generate passport number starting from 1 for each cut
        last_passport = Passport.objects.filter(cut=cut).order_by('number').last()
        passport.number = last_passport.number + 1 if last_passport else 1

        passport.cut = cut  # Link passport directly to the cut
        passport.save()
        # Get the selected combination. The value is like "12|5"
        combination = form.cleaned_data['combination']
        color_id, fabric_id = combination.split("|")

        # Filter the cut's cut_sizes so that we only include those with matching color and fabric.
        matching_cut_sizes = cut.cut_sizes.filter(
            size_quantity__color_id=color_id,
            size_quantity__fabrics_id=fabric_id
        )
        # For each matching cut_size, create a PassportSize (and ProductionPieces)
        for cut_size in matching_cut_sizes:
            passport_size = PassportSize.objects.create(
                passport=passport,
                size_quantity=cut_size.size_quantity,
                quantity=form.cleaned_data['layers'],  # Use layers from the form input
                stage=0,  # Default stage (CUTTING)
                extra=cut_size.extra  # Use extra from CutSize
            )
            quantity = int(passport_size.quantity)
            for i in range(1, quantity + 1):
                ProductionPiece.objects.create(
                    passport_size=passport_size,
                    piece_number=i
                )

        return redirect(self.get_success_url())


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
        with transaction.atomic():
            if passport_size.stage == PassportSize.SEWING:
                passport_size.stage = PassportSize.CUTTING
            else:
                passport_size.stage = PassportSize.SEWING
            passport_size.save()

        return JsonResponse({'success': True})

    except PassportSize.DoesNotExist:
        return JsonResponse({'error': 'PassportSize not found'}, status=404)