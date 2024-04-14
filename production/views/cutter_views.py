from django.contrib.auth.decorators import login_required
from ..decorators import cutter_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from ..forms import *
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.shortcuts import render, redirect, get_object_or_404
from ..models import *
from django.views import View
from ..mixins import *
from django.urls import reverse
from django.db import transaction
from collections import defaultdict
from django.db.models import Sum
from django.http import HttpResponseRedirect

@login_required
@cutter_required
def cutter_page(request):
    return render(request, 'cutter_page.html')

@method_decorator([login_required, cutter_required], name='dispatch')
class OrderListCutterView(RestrictBranchMixin, ListView):
    model = Order
    template_name = 'cutter/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 10

    def get_queryset(self):
        return super().get_queryset().order_by('term')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        orders_with_days_left = []

        for order in context['orders']:
            days_left = (order.term - today).days
            orders_with_days_left.append({
                'order': order,
                'days_left': days_left
            })

        orders_with_days_left_sorted = sorted(orders_with_days_left, key=lambda x: x['days_left'])

        context['orders_with_days_left'] = orders_with_days_left_sorted
        return context

@method_decorator([login_required, cutter_required], name='dispatch')
class OrderDetailCutterView(DetailView):
    model = Order
    template_name = 'cutter/orders/detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = context['order']
        passports = order.passports.all()

        size_data = defaultdict(lambda: defaultdict(int))
        total_per_size = defaultdict(int)

        for passport in passports:
            for passport_size in passport.passport_sizes.all():
                size = passport_size.size_quantity.size
                size_data[size][passport.id] += passport_size.quantity
                total_per_size[size] += passport_size.quantity

        required_missing = {sq.size: {'required': sq.quantity, 'missing': sq.quantity - total_per_size.get(sq.size, 0)}
                            for sq in order.size_quantities.all()}

        # Adjusting for sizes in passports not in order sizes
        for size in total_per_size:
            if size not in required_missing:
                required_missing[size] = {'required': 0, 'missing': -total_per_size[size]}

        context.update({
            'size_data': dict(size_data),
            'total_per_size': dict(total_per_size),
            'required_missing': required_missing,
            'passports': passports,
            'days_left': (order.term - timezone.now().date()).days if order.term >= timezone.now().date() else 0
        })

        return context
    
@method_decorator([login_required, cutter_required], name='dispatch')
class PassportCreateView(View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = PassportForm(data={'order': order.pk}) 
        if form.is_valid():
            passport = form.save()
            return redirect('create_passport_roll', passport_id=passport.pk)
        return redirect('order_detail', pk=pk)

@method_decorator([login_required, cutter_required], name='dispatch')
class PassportRollCreateView(CreateView):
    model = PassportRoll
    form_class = PassportRollForm
    template_name = 'cutter/passports/create_passport_roll.html'

    def form_valid(self, form):
        passport_id = self.kwargs['passport_id']
        passport = get_object_or_404(Passport, pk=passport_id)
        roll = form.cleaned_data['roll']
        meters = form.cleaned_data['meters']

        if roll.meters is not None and roll.meters >= meters:
            roll.meters -= meters
            roll.save()

            passport_roll = form.save(commit=False)
            passport_roll.passport = passport
            passport_roll.save()
            return redirect(self.get_success_url())
        else:
            form.add_error('meters', 'Not enough fabric meters available.')
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('create_passport_size', kwargs={'passport_id': self.kwargs['passport_id']})

@method_decorator([login_required, cutter_required], name='dispatch')
class PassportSizeCreateView(CreateView):
    model = PassportSize
    form_class = PassportSizeForm
    template_name = 'cutter/passports/create_passport_size_quantity.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        passport_id = self.kwargs.get('passport_id')
        passport = get_object_or_404(Passport, pk=passport_id)
        context['passport'] = passport
        context['passport_sizes'] = PassportSize.objects.filter(passport=passport)
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        passport_id = self.kwargs.get('passport_id')
        kwargs['passport_id'] = passport_id
        return kwargs

    def form_valid(self, form):
        passport_id = self.kwargs['passport_id']
        passport = get_object_or_404(Passport, pk=passport_id)
        passport_size = form.save(commit=False)
        passport_size.passport = passport
        passport_size.save()
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('create_passport_size', kwargs={'passport_id': self.kwargs['passport_id']})



# @method_decorator([login_required, technologist_required], name='dispatch')
# class SizeQuantityCreateView(View):
#     def get(self, request, passport_id):
#         passport = get_object_or_404(Passport, pk=passport_id)
#         form = SizeQuantityForm()
#         size_quantities = passport.size_quantities.all()
#         return render(request, 'technologist/passports/create_size_quantity.html', {
#             'form': form,
#             'size_quantities': size_quantities,
#             'passport': passport
#         })
#     def post(self, request, passport_id):
#         if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
#             form = SizeQuantityForm(request.POST)
#             if form.is_valid():
#                 new_size_quantity = form.save(commit=False)
#                 new_size_quantity.save()
#                 passport = get_object_or_404(Passport, pk=passport_id)
#                 passport.size_quantities.add(new_size_quantity)
#                 size_quantities = passport.size_quantities.values('id', 'size', 'quantity')
#                 return JsonResponse({'success': True, 'sizeQuantities': list(size_quantities)})
#             else:
#                 return JsonResponse({'success': False, 'errors': form.errors}, status=400)
#         return JsonResponse({'success': False, 'error': 'Non-AJAX request not allowed'}, status=400)
    
# @login_required
# @technologist_required
# def edit_size_quantity(request, sq_id):
#     size_quantity = get_object_or_404(SizeQuantity, id=sq_id)

#     if request.method == 'POST':
#         data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
#         form = SizeQuantityForm(data, instance=size_quantity)
#         if form.is_valid():
#             form.save()
#             return JsonResponse({'status': 'success'}, status=200)
    
#     return JsonResponse({'status': 'error'}, status=400)

# @login_required
# @technologist_required
# def delete_size_quantity(request, sq_id):
#     if request.method == 'POST':
#         size_quantity = get_object_or_404(SizeQuantity, id=sq_id)
#         size_quantity.delete()
#         return JsonResponse({'status': 'success'}, status=200)
#     return JsonResponse({'status': 'error'}, status=400)

@method_decorator([login_required, cutter_required], name='dispatch')
class PassportDetailView(DetailView):
    model = Passport
    template_name = 'cutter/passports/detail.html'
    context_object_name = 'passport'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        passport = context['passport']
        context['passport_sizes'] = passport.passport_sizes.all()
        context['passport_rolls'] = passport.passport_rolls.all()
        return context

@method_decorator([login_required], name='dispatch')
class PassportDeleteView(DeleteView):
    model = Passport

    def get_success_url(self):
        order_id = self.object.order.id
        return reverse('order_detail_cutter', args=[order_id])

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        passport = self.get_object()
        passport_rolls = PassportRoll.objects.filter(passport=passport)

        for passport_roll in passport_rolls:
            roll = passport_roll.roll
            roll.meters += passport_roll.meters  # Add back the meters used
            roll.save()

        response = super().delete(request, *args, **kwargs)
        messages.success(request, 'Passport deleted successfully.')
        return response