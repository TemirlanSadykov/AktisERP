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
from django.views.decorators.http import require_POST

from ..decorators import manager_required
from ..forms import *
from ..mixins import *
from ..models import *

CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@manager_required
def manager_page(request):
    context = {
        'sidebar_type': 'manager'
        }
    return render(request, 'manager_page.html' , context)

@method_decorator([login_required, manager_required], name='dispatch')
class WarehouseListView(ListView):
    model = Warehouse
    template_name = 'manager/warehouse/list.html'
    context_object_name = 'warehouse'
    paginate_by = 10

    def get_queryset(self):
        return Warehouse.objects.filter(is_archived=False).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'manager'
        return context

@method_decorator([login_required, manager_required], name='dispatch')
class ArchivedWarehouseListView(ListView):
    model = Warehouse
    template_name = 'manager/warehouse/list.html'
    context_object_name = 'warehouse'
    paginate_by = 10

    def get_queryset(self):
        return Warehouse.objects.filter(is_archived=True).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'manager'
        return context

@method_decorator([login_required, manager_required], name='dispatch')
class WarehouseArchiveView(UpdateView):
    model = Warehouse
    template_name = 'manager/warehouse/delete.html'
    success_url = reverse_lazy('warehouse_list')

    def post(self, request, *args, **kwargs):
        warehouse = self.get_object()
        warehouse.is_archived = True
        warehouse.save()
        return HttpResponseRedirect(self.success_url)

@method_decorator([login_required, manager_required], name='dispatch')
class WarehouseUnArchiveView(UpdateView):
    model = Warehouse
    template_name = 'manager/warehouse/delete.html'
    success_url = reverse_lazy('warehouse_list')

    def post(self, request, *args, **kwargs):
        warehouse = self.get_object()
        warehouse.is_archived = False
        warehouse.save()
        return HttpResponseRedirect(self.success_url)

@method_decorator([login_required, manager_required], name='dispatch')
class WarehouseCreateView(CreateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'manager/warehouse/create.html'
    success_url = reverse_lazy('warehouse_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'manager'
        return context

@method_decorator([login_required, manager_required], name='dispatch')
class WarehouseDetailView(DetailView):
    model = Warehouse
    template_name = 'manager/warehouse/detail.html'
    context_object_name = 'warehouse'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'manager'

        # Group stock by model
        stocks = self.object.stocks.all()
        grouped_stocks = {}
        for stock in stocks:
            model_name = stock.model.name
            if model_name not in grouped_stocks:
                grouped_stocks[model_name] = []
            grouped_stocks[model_name].append(stock)
        
        context['grouped_stocks'] = grouped_stocks
        return context

@method_decorator([login_required, manager_required], name='dispatch')
class WarehouseUpdateView(UpdateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'manager/warehouse/edit.html'
    success_url = reverse_lazy('warehouse_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'manager'
        return context

@method_decorator([login_required, manager_required], name='dispatch')
class WarehouseDeleteView(DeleteView):
    model = Warehouse
    template_name = 'manager/warehouse/delete.html'
    success_url = reverse_lazy('warehouse_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'manager'
        return context
    
@require_POST
@login_required
@manager_required
def update_piece_manager(request, piece_id):
    try:
        # Parse request body
        data = json.loads(request.body)
        status = data.get('status')
        defect_type = data.get('defectType', None)

        # Validate status
        valid_statuses = {
            'Sold': ProductionPiece.StageChoices.SOLD,
            'Defect': ProductionPiece.StageChoices.DEFECT,
        }
        if status not in valid_statuses:
            return JsonResponse({'success': False, 'message': 'Invalid status provided.'}, status=400)

        # Fetch the piece and related size_quantity
        piece = ProductionPiece.objects.select_related('passport_size__size_quantity').get(pk=piece_id)
        size_quantity = piece.passport_size.size_quantity

        # Update piece status and defect type
        piece.stage = valid_statuses[status]
        if status == 'Defect':
            if defect_type in [choice[0] for choice in ProductionPiece.DefectType.choices]:
                piece.defect_type = defect_type
            else:
                return JsonResponse({'success': False, 'message': 'Invalid defect type provided for defect status.'}, status=400)
        else:
            piece.defect_type = None  # Clear defect type if not defect
        piece.save()

        # If status is "Sold," update the stock
        if status == 'Sold':
            try:
                # Find the Stock entry for this size_quantity
                stock = Stock.objects.get(size_quantity=size_quantity)

                # Update stock quantities
                if stock.available_quantity > 0:
                    stock.available_quantity -= 1
                    stock.sold_quantity += 1
                    stock.save()
                else:
                    return JsonResponse({'success': False, 'message': 'No stock available to sell.'}, status=400)
            except Stock.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'No stock found for the size_quantity.'}, status=404)

        message = f"Piece status updated to {status}."
        if status == 'Defect':
            message += f" Defect type: {defect_type}."
        return JsonResponse({'success': True, 'message': message})

    except ProductionPiece.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Piece not found.'}, status=404)
    except KeyError:
        return JsonResponse({'success': False, 'message': 'Status or defect type not provided in request.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
@manager_required
def scan_manager_page(request):
    context = {
            'sidebar_type': 'manager'
            }
    return render(request, 'manager/scans/detail.html', context)