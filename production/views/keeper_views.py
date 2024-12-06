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

from ..decorators import keeper_required
from ..forms import *
from ..mixins import *
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
class RollListView(RestrictBranchMixin, ListView):
    model = Roll
    template_name = 'keeper/rolls/list.html'
    context_object_name = 'rolls'
    paginate_by = 10
    
    def get_queryset(self):
        return super().get_queryset().filter(is_archived=False).order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context
    
@method_decorator([login_required, keeper_required], name='dispatch')
class ArchivedRollListView(RestrictBranchMixin, ListView):
    model = Roll
    template_name = 'keeper/rolls/list.html'
    context_object_name = 'rolls'
    paginate_by = 10
    def get_queryset(self):
        return super().get_queryset().filter(is_archived=True).order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollCreateView(AssignBranchMixin, CreateView):
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
class RollUpdateView(RestrictBranchMixin, UpdateView):
    model = Roll
    form_class = RollForm
    template_name = 'keeper/rolls/edit.html'
    success_url = reverse_lazy('roll_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollDeleteView(RestrictBranchMixin, DeleteView):
    model = Roll
    template_name = 'keeper/rolls/delete.html'
    success_url = reverse_lazy('roll_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class RollArchiveView(RestrictBranchMixin, UpdateView):
    model = Roll
    template_name = 'keeper/rolls/delete.html'
    success_url = reverse_lazy('roll_list')
    
    def post(self, request, *args, **kwargs):
        roll = self.get_object()
        roll.is_archived = True
        roll.save()
        return HttpResponseRedirect(self.success_url)


@method_decorator([login_required, keeper_required], name='dispatch')
class RollUnArchiveView(RestrictBranchMixin, UpdateView):
    model = Roll
    template_name = 'keeper/rolls/delete.html'
    success_url = reverse_lazy('roll_list')

    def post(self, request, *args, **kwargs):
        roll = self.get_object()
        roll.is_archived = False
        roll.save()
        return HttpResponseRedirect(self.success_url)

@method_decorator([login_required, keeper_required], name='dispatch')
class ColorListView(ListView):
    model = Color
    template_name = 'keeper/color/list.html'
    context_object_name = 'color'
    paginate_by = 10

    def get_queryset(self):
        return Color.objects.filter(is_archived=False).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class ArchivedColorListView(ListView):
    model = Color
    template_name = 'keeper/color/list.html'
    context_object_name = 'color'
    paginate_by = 10

    def get_queryset(self):
        return Color.objects.filter(is_archived=True).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context
    
@method_decorator([login_required, keeper_required], name='dispatch')
class ColorArchiveView(UpdateView):
    model = Color
    template_name = 'keeper/color/delete.html'
    success_url = reverse_lazy('color_list')

    def post(self, request, *args, **kwargs):
        color = self.get_object()
        color.is_archived = True
        color.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, keeper_required], name='dispatch')
class ColorUnArchiveView(UpdateView):
    model = Color
    template_name = 'keeper/color/delete.html'
    success_url = reverse_lazy('color_list')

    def post(self, request, *args, **kwargs):
        color = self.get_object()
        color.is_archived = False
        color.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, keeper_required], name='dispatch')
class ColorCreateView(CreateView):
    model = Color
    form_class = ColorForm
    template_name = 'keeper/color/create.html'
    success_url = reverse_lazy('color_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class ColorDetailView(DetailView):
    model = Color
    template_name = 'keeper/color/detail.html'
    context_object_name = 'color'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class ColorUpdateView(UpdateView):
    model = Color
    form_class = ColorForm
    template_name = 'keeper/color/edit.html'
    success_url = reverse_lazy('color_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class ColorDeleteView(DeleteView):
    model = Color
    template_name = 'keeper/color/delete.html'
    success_url = reverse_lazy('color_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context



@method_decorator([login_required, keeper_required], name='dispatch')
class FabricsListView(ListView):
    model = Fabrics
    template_name = 'keeper/fabrics/list.html'
    context_object_name = 'fabrics'
    paginate_by = 10

    def get_queryset(self):
        return Fabrics.objects.filter(is_archived=False).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class ArchivedFabricsListView(ListView):
    model = Fabrics
    template_name = 'keeper/fabrics/list.html'
    context_object_name = 'fabrics'
    paginate_by = 10

    def get_queryset(self):
        return Fabrics.objects.filter(is_archived=True).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context
    
@method_decorator([login_required, keeper_required], name='dispatch')
class FabricsArchiveView(UpdateView):
    model = Fabrics
    template_name = 'keeper/fabrics/delete.html'
    success_url = reverse_lazy('fabrics_list')

    def post(self, request, *args, **kwargs):
        fabric = self.get_object()
        fabric.is_archived = True
        fabric.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, keeper_required], name='dispatch')
class FabricsUnArchiveView(UpdateView):
    model = Fabrics
    template_name = 'keeper/fabrics/delete.html'
    success_url = reverse_lazy('fabrics_list')

    def post(self, request, *args, **kwargs):
        fabric = self.get_object()
        fabric.is_archived = False
        fabric.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, keeper_required], name='dispatch')
class FabricsCreateView(CreateView):
    model = Fabrics
    form_class = FabricsForm
    template_name = 'keeper/fabrics/create.html'
    success_url = reverse_lazy('fabrics_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class FabricsDetailView(DetailView):
    model = Fabrics
    template_name = 'keeper/fabrics/detail.html'
    context_object_name = 'fabrics'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class FabricsUpdateView(UpdateView):
    model = Fabrics
    form_class = FabricsForm
    template_name = 'keeper/fabrics/edit.html'
    success_url = reverse_lazy('fabrics_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class FabricsDeleteView(DeleteView):
    model = Fabrics
    template_name = 'keeper/fabrics/delete.html'
    success_url = reverse_lazy('fabrics_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context


@method_decorator([login_required, keeper_required], name='dispatch')
class AbstractAccessoryListView(ListView):
    model = AbstractAccessory
    template_name = 'keeper/abstract_accessory/list.html'
    context_object_name = 'abstract_accessory'
    paginate_by = 10

    def get_queryset(self):
        return AbstractAccessory.objects.filter(is_archived=False).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class ArchivedAbstractAccessoryListView(ListView):
    model = AbstractAccessory
    template_name = 'keeper/abstract_accessory/list.html'
    context_object_name = 'abstract_accessory'
    paginate_by = 10

    def get_queryset(self):
        return AbstractAccessory.objects.filter(is_archived=True).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class AbstractAccessoryArchiveView(UpdateView):
    model = AbstractAccessory
    template_name = 'keeper/abstract_accessory/delete.html'
    success_url = reverse_lazy('abstract_accessory_list')

    def post(self, request, *args, **kwargs):
        abstract_accessory = self.get_object()
        abstract_accessory.is_archived = True
        abstract_accessory.save()
        return HttpResponseRedirect(self.success_url)

@method_decorator([login_required, keeper_required], name='dispatch')
class AbstractAccessoryUnArchiveView(UpdateView):
    model = AbstractAccessory
    template_name = 'keeper/abstract_accessory/delete.html'
    success_url = reverse_lazy('abstract_accessory_list')

    def post(self, request, *args, **kwargs):
        abstract_accessory = self.get_object()
        abstract_accessory.is_archived = False
        abstract_accessory.save()
        return HttpResponseRedirect(self.success_url)

@method_decorator([login_required, keeper_required], name='dispatch')
class AbstractAccessoryCreateView(CreateView):
    model = AbstractAccessory
    form_class = AbstractAccessoryForm
    template_name = 'keeper/abstract_accessory/create.html'
    success_url = reverse_lazy('abstract_accessory_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class AbstractAccessoryDetailView(DetailView):
    model = AbstractAccessory
    template_name = 'keeper/abstract_accessory/detail.html'
    context_object_name = 'abstract_accessory'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class AbstractAccessoryUpdateView(UpdateView):
    model = AbstractAccessory
    form_class = AbstractAccessoryForm
    template_name = 'keeper/abstract_accessory/edit.html'
    success_url = reverse_lazy('abstract_accessory_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context

@method_decorator([login_required, keeper_required], name='dispatch')
class AbstractAccessoryDeleteView(DeleteView):
    model = AbstractAccessory
    template_name = 'keeper/abstract_accessory/delete.html'
    success_url = reverse_lazy('abstract_accessory_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'keeper'
        return context