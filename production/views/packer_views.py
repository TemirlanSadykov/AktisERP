from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from ..decorators import packer_required
from django.utils.decorators import method_decorator
from ..mixins import *
from ..models import *
from ..forms import *
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from collections import defaultdict
from django.http import JsonResponse
from django.db import transaction

@login_required
@packer_required
def packer_page(request):
    return render(request, 'packer_page.html')

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
            context['discrepancies'] = Discrepancy.objects.filter(passport=passport)
        else:
            context['discrepancies'] = Discrepancy.objects.none()

        today = timezone.localdate()
        if order.client_order.term >= today:
            days_left = (order.client_order.term - today).days
        else:
            days_left = 0
        context['days_left'] = days_left

        passports = order.passports.all()

        # Initialize size_data as a defaultdict where each passport.id is another defaultdict
        size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'passport_size_id': None}))
        total_per_size = defaultdict(int)

        for passport in passports:
            for passport_size in passport.passport_sizes.all():
                size = passport_size.size_quantity.size
                size_data[size][passport.id]['stage'] = passport_size.stage  # Include the stage
                size_data[size][passport.id]['quantity'] += passport_size.quantity
                size_data[size][passport.id]['passport_size_id'] = passport_size.id
                total_per_size[size] += passport_size.quantity

        # Calculate required and missing quantities
        required_missing = {sq.size: {'required': sq.quantity, 'missing': sq.quantity - total_per_size.get(sq.size, 0)}
                            for sq in order.size_quantities.all().order_by('size')}

        for size in total_per_size:
            if size not in required_missing:
                required_missing[size] = {'required': 0, 'missing': -total_per_size[size]}

        context.update({
            'size_data': {k: {k2: dict(v2) for k2, v2 in v.items()} for k, v in size_data.items()},
            'total_per_size': dict(total_per_size),
            'required_missing': required_missing,
            'passports': passports,
        })
        return context
    
@method_decorator([login_required, packer_required], name='dispatch')
class DiscrepancyCreateView(CreateView):
    model = Discrepancy
    form_class = DiscrepancyForm
    template_name = 'packer/discrepancies/create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        order_pk = self.kwargs.get('order_pk')
        kwargs['order_pk'] = order_pk
        return kwargs

    def form_valid(self, form):
        form.instance.order = get_object_or_404(Order, pk=self.kwargs['order_pk'])
        return super().form_valid(form)

    def get_success_url(self):
        order_pk = self.kwargs['order_pk']
        return reverse_lazy('order_detail_packer', kwargs={'pk': order_pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order_pk = self.kwargs['order_pk']
        context['order'] = get_object_or_404(Order, pk=order_pk)
        return context

@method_decorator([login_required, packer_required], name='dispatch')
class DiscrepancyDetailView(DetailView):
    model = Discrepancy
    template_name = 'packer/discrepancies/detail.html'
    context_object_name = 'discrepancy'

@method_decorator([login_required, packer_required], name='dispatch')
class DiscrepancyUpdateView(UpdateView):
    model = Discrepancy
    form_class = DiscrepancyForm
    template_name = 'packer/discrepancies/edit.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        order_pk = self.kwargs.get('order_pk')
        kwargs['order_pk'] = order_pk
        return kwargs

    def get_success_url(self):
        order_pk = self.kwargs['order_pk']
        return reverse_lazy('order_detail_packer', kwargs={'pk': order_pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        discrepancy_pk = self.kwargs['pk']
        context['discrepancy'] = get_object_or_404(Discrepancy, pk=discrepancy_pk)
        return context

@method_decorator([login_required, packer_required], name='dispatch')
class DiscrepancyDeleteView(DeleteView):
    model = Discrepancy

    def get_success_url(self):
        order_pk = self.kwargs['order_pk']
        return reverse_lazy('order_detail_packer', kwargs={'pk': order_pk})
    
@login_required
@packer_required
def mark_as_done(request, passport_size_id):
    try:
        passport_size = PassportSize.objects.get(id=passport_size_id)
        order = passport_size.passport.order
        operations = Operation.objects.filter(node__type=Node.PACKING)
        with transaction.atomic():
            if passport_size.stage == PassportSize.DONE:
                passport_size.stage = PassportSize.PACKING
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
                passport_size.stage = PassportSize.DONE
            passport_size.save()

        return JsonResponse({'success': True})

    except PassportSize.DoesNotExist:
        return JsonResponse({'error': 'PassportSize not found'}, status=404)