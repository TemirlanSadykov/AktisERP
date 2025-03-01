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
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.db.models import Q
from django.urls import reverse_lazy, reverse
from django.views.generic import FormView
from django.views.decorators.http import require_POST
from decimal import Decimal, InvalidOperation

from ..decorators import keeper_required
from ..forms import *
from ..models import *

CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@keeper_required
def keeper_page(request):
    context = {
        'sidebar_type': 'keeper'
        }
    return render(request, 'keeper_page.html' , context)

@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierListView(ListView):
    model = Supplier
    template_name = 'keeper/suppliers/list.html'
    context_object_name = 'suppliers'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Supplier.objects.filter(is_archived=False).order_by('name')


@method_decorator([login_required, keeper_required], name='dispatch')
class ArchivedSupplierListView(ListView):
    template_name = 'keeper/suppliers/list.html'
    context_object_name = 'suppliers'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Supplier.objects.filter(is_archived=True).order_by('name')


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierCreateView(CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'keeper/suppliers/create.html'
    success_url = reverse_lazy('supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierDetailView(DetailView):
    model = Supplier
    template_name = 'keeper/suppliers/detail.html'
    context_object_name = 'supplier'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierUpdateView(UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'keeper/suppliers/edit.html'

    def get_success_url(self):
        return reverse('supplier_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierDeleteView(DeleteView):
    model = Supplier
    template_name = 'keeper/suppliers/delete.html'
    success_url = reverse_lazy('supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierArchiveView(UpdateView):
    model = Supplier
    template_name = 'keeper/suppliers/delete.html'
    success_url = reverse_lazy('supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        supplier = self.get_object()
        supplier.is_archived = True
        supplier.save()
        return HttpResponseRedirect(self.success_url)


@method_decorator([login_required, keeper_required], name='dispatch')
class SupplierUnArchiveView(UpdateView):
    model = Supplier
    template_name = 'keeper/suppliers/delete.html'
    success_url = reverse_lazy('supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def post(self, request, *args, **kwargs):
        supplier = self.get_object()
        supplier.is_archived = False
        supplier.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, keeper_required], name='dispatch')
class RollListView(ListView):
    model = Roll
    template_name = 'keeper/rolls/list.html'
    context_object_name = 'rolls'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

    def get_queryset(self):
        return Roll.objects.all().order_by('name')

@method_decorator([login_required, keeper_required], name='dispatch')
class RollCreateView(CreateView):
    model = Roll
    form_class = RollForm
    template_name = 'keeper/rolls/create.html'
    success_url = reverse_lazy('roll_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollDetailView(DetailView):
    model = Roll
    template_name = 'keeper/rolls/detail.html'
    context_object_name = 'roll'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollUpdateView(UpdateView):
    model = Roll
    form_class = RollForm
    template_name = 'keeper/rolls/edit.html'

    def get_success_url(self):
        return reverse('roll_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollDeleteView(DeleteView):
    model = Roll
    template_name = 'keeper/rolls/delete.html'
    success_url = reverse_lazy('roll_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context
    
@require_POST
@login_required
def add_supplier_api(request):
    form = SupplierForm(request.POST)
    if form.is_valid():
        supplier = form.save()
        data = {
            'success': True,
            'supplier_id': supplier.id,
            'supplier_name': supplier.name,
        }
        return JsonResponse(data)
    else:
        # Return form errors as JSON (status code 400)
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)

@method_decorator([login_required, keeper_required], name='dispatch')
class ColorFabricListView(ListView):
    template_name = 'keeper/rolls/color_fabric_list.html'
    context_object_name = 'combinations'
    
    def get_queryset(self):
        qs = Roll.objects.filter(is_used=False)
        # Return distinct combinations including supplier, along with names for display
        return qs.values(
            'color',
            'fabric',
            'supplier',
            color_name=F('color__name'),
            fabric_name=F('fabric__name'),
            supplier_name=F('supplier__name')
        ).distinct()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollsByCombinationListView(ListView):
    model = Roll
    template_name = 'keeper/rolls/combination_detail.html'
    context_object_name = 'rolls'
    paginate_by = 10
    
    def get_queryset(self):
        color_id = self.kwargs.get('color_id')
        fabric_id = self.kwargs.get('fabric_id')
        supplier_id = self.kwargs.get('supplier_id')
        return Roll.objects.filter(is_used=False, color_id=color_id, fabric_id=fabric_id, supplier_id=supplier_id).order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        first_roll = self.get_queryset().first()
        if first_roll:
            context['color'] = first_roll.color.name
            context['fabric'] = first_roll.fabric.name
            context['supplier'] = first_roll.supplier.name
        else:
            context['color'] = ''
            context['fabric'] = ''
            context['supplier'] = ''
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollBulkCreateView(CreateView):
    model = Roll
    form_class = BulkRollForm
    template_name = 'keeper/rolls/bulk_create.html'
    success_url = reverse_lazy('roll_combinations')

    def form_valid(self, form):
        color = form.cleaned_data['color']
        fabric = form.cleaned_data['fabric']
        supplier = form.cleaned_data['supplier']
        width = form.cleaned_data['width']
        quantity = form.cleaned_data['quantity']
        
        weights = self.request.POST.getlist('weight')
        lengths = self.request.POST.getlist('length')
        cleaned_weights = []
        cleaned_lengths = []

        for w in weights:
            try:
                # Convert empty string to None (or set a default like 0)
                cleaned_weights.append(Decimal(w) if w.strip() else None)
            except InvalidOperation:
                cleaned_weights.append(None)  # or handle error as needed

        for l in lengths:
            try:
                cleaned_lengths.append(Decimal(l) if l.strip() else None)
            except InvalidOperation:
                cleaned_lengths.append(None)

        existing_count = Roll.objects.filter(color=color, fabric=fabric, supplier=supplier).count()
        current_company = get_current_company()  # should be valid
        
        new_rolls = []
        for i in range(quantity):
            roll_name = str(existing_count + i + 1)
            weight_value = cleaned_weights[i] if i < len(cleaned_weights) else None
            length_value = cleaned_lengths[i] if i < len(cleaned_lengths) else None
            new_rolls.append(Roll(
                color=color,
                fabric=fabric,
                supplier=supplier,
                width=width,
                weight=weight_value,
                length_t=length_value,
                name=roll_name,
                is_used=False,
                company=current_company,
            ))
        Roll.objects.bulk_create(new_rolls)
        
        # Set self.object to one of the created rolls (if any)
        if new_rolls:
            self.object = new_rolls[0]
        
        return HttpResponseRedirect(self.get_success_url())
      
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context
