from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from ..decorators import qc_required
from django.utils.decorators import method_decorator
from ..mixins import *
from ..models import *
from ..forms import *
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404

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
        return super().get_queryset().order_by('client_order__term')

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
        return context

@method_decorator([login_required, qc_required], name='dispatch')
class OrderDetailQcView(DetailView):
    model = Order
    template_name = 'qc/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']
        context['defects'] = Defects.objects.filter(order=order)
        context['size_quantities'] = order.size_quantities.all().order_by('size')
        today = timezone.localdate() 
        if order.client_order.term >= today:
            days_left = (order.client_order.term - today).days
        else:
            days_left = 0  
        context['days_left'] = days_left

        return context
    
@method_decorator([login_required, qc_required], name='dispatch')
class DefectCreateView(CreateView):
    model = Defects
    form_class = DefectForm
    template_name = 'qc/defects/create.html'

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
        return reverse_lazy('order_detail_qc', kwargs={'pk': order_pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order_pk = self.kwargs['order_pk']
        context['order'] = get_object_or_404(Order, pk=order_pk)
        return context

@method_decorator([login_required, qc_required], name='dispatch')
class DefectDetailView(DetailView):
    model = Defects
    template_name = 'qc/defects/detail.html'
    context_object_name = 'defect'

@method_decorator([login_required, qc_required], name='dispatch')
class DefectUpdateView(UpdateView):
    model = Defects
    form_class = DefectForm
    template_name = 'qc/defects/edit.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        order_pk = self.kwargs.get('order_pk')
        kwargs['order_pk'] = order_pk
        return kwargs

    def get_success_url(self):
        order_pk = self.kwargs['order_pk']
        return reverse_lazy('order_detail_qc', kwargs={'pk': order_pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        defect_pk = self.kwargs['pk']
        context['defect'] = get_object_or_404(Defects, pk=defect_pk)
        return context

@method_decorator([login_required, qc_required], name='dispatch')
class DefectDeleteView(DeleteView):
    model = Defects

    def get_success_url(self):
        order_pk = self.kwargs['order_pk']
        return reverse_lazy('order_detail_qc', kwargs={'pk': order_pk})