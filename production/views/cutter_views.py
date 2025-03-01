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
class ClientOrderListCutterView(ListView):
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
class OrderListCutterView(ListView):
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
        size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'passport_size_id': None, 'extra': None}))
        total_per_size = defaultdict(int)
        for passport in passports:
            passport_number = passport.id
            for passport_size in passport.passport_sizes.all():
                size = passport_size.size_quantity.size
                extra_key = f"{size}-{passport_size.extra}" if passport_size.extra else size
                size_data[extra_key][passport_number]['quantity'] += passport_size.quantity
                size_data[extra_key][passport_number]['passport_size_id'] = passport_size.id
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
        from collections import defaultdict
        context = super().get_context_data(**kwargs)
        cut_pk = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_pk)

        # Get all passports related to the cut.
        passports = cut.passports.all().order_by('-number')

        # Get overall sizes from CutSizes—but only those that have been used in passports.
        # We'll build a set of (size, extra) pairs from all PassportSize records.
        passport_sizes_set = set()
        for passport in passports:
            for ps in passport.passport_sizes.all():
                # Use ps.extra or '' if it's empty.
                passport_sizes_set.add((ps.size_quantity.size, ps.extra or ''))
        # Sort them: first by numeric value of size (if possible), then by extra.
        try:
            passport_sizes_display = sorted(passport_sizes_set, key=lambda x: (int(x[0]), x[1]))
        except ValueError:
            passport_sizes_display = sorted(passport_sizes_set, key=lambda x: (x[0], x[1]))

        # Prepare total quantities per size (if needed elsewhere)
        total_quantity_per_size = defaultdict(int)
        for cs in cut.cut_sizes.all():
            # Note: This sums by size only (ignoring extra).
            total_quantity_per_size[cs.size_quantity.size] += cs.size_quantity.quantity

        # Total layers from all passports.
        total_layers = sum(passport.layers for passport in passports if passport.layers)

        context.update({
            'passports': passports,
            'total_quantity_per_size': dict(total_quantity_per_size),
            'total_layers': total_layers,
            'passport_sizes_display': passport_sizes_display,  # New variable for overall passport sizes.
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
        order = get_object_or_404(self.model.order.field.related_model, pk=self.object.order.pk)
        kwargs['order'] = order
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = get_object_or_404(self.object.order.__class__, pk=self.object.order.pk)
        context['order'] = order
        context['sidebar_type'] = 'cutter'
        return context

    def form_valid(self, form):
        # Get the new sizes from the form.
        new_sizes = set(form.cleaned_data['size_choices'])
        # Get the old sizes from the existing cut.
        old_sizes = set(cs.size_quantity.size for cs in self.object.cut_sizes.all())
        removed_sizes = old_sizes - new_sizes
        added_sizes = new_sizes - old_sizes

        # Save the basic fields.
        response = super().form_valid(form)
        cut = self.object

        # Handle removed sizes.
        if removed_sizes:
            # Delete CutSize records for removed sizes.
            cut.cut_sizes.filter(size_quantity__size__in=removed_sizes).delete()
            # For each related passport, remove PassportSize records for those sizes.
            for passport in cut.passports.all():
                passport.passport_sizes.filter(size_quantity__size__in=removed_sizes).delete()
            # (If needed, also update related ProductionPiece records, 
            # but if they depend on PassportSize, cascade deletion may handle that.)

        # Handle added sizes.
        if added_sizes:
            # Create new CutSize records only for the newly added sizes.
            form.save_cut_sizes(cut, sizes_to_create=added_sizes)

        # Optionally, if the sizes that remain have changed quantities,
        # you might want to update those too.
        # One approach: delete and re-create them for sizes that remain.
        common_sizes = new_sizes & old_sizes
        if common_sizes:
            # Delete existing records for these sizes.
            cut.cut_sizes.filter(size_quantity__size__in=common_sizes).delete()
            # Re-create them with the new quantities.
            form.save_cut_sizes(cut, sizes_to_create=common_sizes)

        return response

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
        # Generate passport number starting from 1 for each cut.
        last_passport = Passport.objects.filter(cut=cut).order_by('number').last()
        passport.number = last_passport.number + 1 if last_passport else 1

        passport.cut = cut  # Link passport directly to the cut.
        passport.save()     # Save first to have an instance for m2m relations.

        # Handle passport sizes based on the selected combination.
        combination = form.cleaned_data['combination']
        layers = form.cleaned_data['layers']
        color_id, fabric_id = combination.split("|")
        matching_cut_sizes = cut.cut_sizes.filter(
            size_quantity__color_id=color_id,
            size_quantity__fabrics_id=fabric_id
        )
        for cut_size in matching_cut_sizes:
            passport_size = PassportSize.objects.create(
                passport=passport,
                size_quantity=cut_size.size_quantity,
                quantity=layers,
                extra=cut_size.extra
            )
            quantity = int(passport_size.quantity)
            for i in range(1, quantity + 1):
                ProductionPiece.objects.create(
                    passport_size=passport_size,
                    piece_number=i
                )
        
        # New logic: assign the selected roll to the passport.
        selected_roll = form.cleaned_data['roll']
        passport.roll = selected_roll
        passport.save()
        
        # Update the selected roll’s remainder.
        new_remainder = form.cleaned_data['remainder']
        selected_roll.remainder = new_remainder
        selected_roll.length_p = new_remainder+layers*cut.length
        selected_roll.is_used = True
        selected_roll.save()
        
        cut.consumption_p = selected_roll.length_p/passport.quantity # Use length_p or length_t?
        cut.save()
        return redirect(self.get_success_url())


    def get_success_url(self):
        return reverse('passport_create', kwargs={'pk': self.kwargs['pk']})
    
def ajax_get_rolls(request):
    color_id = request.GET.get('color_id')
    fabric_id = request.GET.get('fabric_id')
    if color_id and fabric_id:
        # Adjust the fields as needed (for display, here using the roll’s name or a concatenation)
        rolls_qs = Roll.objects.filter(color_id=color_id, fabric_id=fabric_id, is_used=False)
        rolls = [
            {"id": roll.id, "label": f"{roll.color.name} {roll.fabric.name} (Roll #{roll.name})"}
            for roll in rolls_qs
        ]
    else:
        rolls = []
    return JsonResponse({"rolls": rolls})
    
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

# @login_required
# @cutter_required
# def mark_as_sewing(request, passport_size_id):
#     try:
#         passport_size = PassportSize.objects.get(id=passport_size_id)
#         with transaction.atomic():
#             if passport_size.stage == PassportSize.SEWING:
#                 passport_size.stage = PassportSize.CUTTING
#             else:
#                 passport_size.stage = PassportSize.SEWING
#             passport_size.save()

#         return JsonResponse({'success': True})

#     except PassportSize.DoesNotExist:
#         return JsonResponse({'error': 'PassportSize not found'}, status=404)