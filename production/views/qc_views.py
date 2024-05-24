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

from ..decorators import qc_required
from ..forms import *
from ..mixins import *
from ..models import *

CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@qc_required
def qc_page(request):
    return render(request, 'qc_page.html')

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

        # Initialize size_data as a defaultdict where each passport.id is another defaultdict
        size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'passport_size_id': None, 'stage': None}))
        total_per_size = defaultdict(int)

        for passport in passports:
            for passport_size in passport.passport_sizes.all():
                size = passport_size.size_quantity.size
                size_data[size][passport.id]['quantity'] += passport_size.quantity
                size_data[size][passport.id]['passport_size_id'] = passport_size.id
                size_data[size][passport.id]['stage'] = passport_size.stage
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
            'days_left': (order.client_order.term - timezone.now().date()).days if order.client_order.term >= timezone.now().date() else 0
        })

        return context
    
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