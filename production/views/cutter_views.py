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
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
import json
from decimal import Decimal

@login_required
@cutter_required
def cutter_page(request):
    return render(request, 'cutter_page.html')

@method_decorator([login_required, cutter_required], name='dispatch')
class OrderListCutterView(RestrictOrderBranchMixin, ListView):
    model = Order
    template_name = 'cutter/orders/list.html'
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

        context['orders_with_days_left'] = orders_with_days_left_sorted
        context['selected_status'] = self.request.GET.get('status', '')
        context['Order'] = Order
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
    
@method_decorator([login_required, cutter_required], name='dispatch')
class PassportCreateView(View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = PassportForm(data={'order': order.pk}) 
        if form.is_valid():
            passport = form.save()
            order.status = Order.IN_PROGRESS
            order.save()

            client_order = order.client_order
            if client_order.status != ClientOrder.COMPLETED: 
                client_order.status = ClientOrder.IN_PROGRESS
                client_order.save()

            return redirect('create_passport_roll', passport_id=passport.pk)

        return redirect('order_detail', pk=pk)

@method_decorator([login_required, cutter_required], name='dispatch')
class PassportRollCreateView(CreateView):
    model = PassportRoll
    form_class = PassportRollForm
    template_name = 'cutter/passports/create_passport_roll.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        passport_id = self.kwargs.get('passport_id')
        passport = get_object_or_404(Passport, pk=passport_id)
        context['passport'] = passport
        context['passport_rolls'] = PassportRoll.objects.filter(passport=passport)
        return context

    def form_valid(self, form):
        passport_id = self.kwargs['passport_id']
        passport = get_object_or_404(Passport, pk=passport_id)
        passport_roll = form.save(commit=False)
        passport_roll.passport = passport
        roll = passport_roll.roll
        meters_requested = passport_roll.meters

        if roll.available_meters is not None and roll.available_meters >= meters_requested:
            roll.used_meters += meters_requested 
            roll.save()
            passport_roll.save()
            return redirect(self.get_success_url())
        else:
            form.add_error('meters', 'Not enough fabric meters available.')
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('create_passport_roll', kwargs={'passport_id': self.kwargs['passport_id']})

@login_required
@cutter_required
@require_POST
def edit_passport_roll(request, pr_id):
    try:
        data = json.loads(request.body)
        new_meters = Decimal(data.get('meters'))
        
        passport_roll = PassportRoll.objects.get(id=pr_id)
        original_roll = passport_roll.roll
        old_meters = passport_roll.meters

        difference = new_meters - old_meters
        if original_roll.available_meters + difference >= 0:
            original_roll.used_meters += difference
            original_roll.save()
            passport_roll.meters = new_meters
            passport_roll.save()
            return JsonResponse({'status': 'success', 'message': 'Meters updated successfully'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Not enough fabric available'}, status=400)

    except PassportRoll.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'PassportRoll not found'}, status=404)
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@login_required
@cutter_required
@require_POST
def delete_passport_roll(request, pr_id):
    try:
        passport_roll = PassportRoll.objects.get(id=pr_id)
        original_roll = passport_roll.roll

        if original_roll.used_meters is not None:
            original_roll.used_meters -= passport_roll.meters
            original_roll.save()

        passport_roll.delete()

        return JsonResponse({'status': 'success', 'message': 'PassportRoll deleted successfully'})

    except PassportRoll.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'PassportRoll not found'}, status=404)
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

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
        context['passport_sizes'] = PassportSize.objects.filter(passport=passport).order_by('size_quantity__size')
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
    
@login_required
@cutter_required
@require_POST
def edit_passport_size_quantity(request, sq_id):
    try:
        # Convert JSON data to Python dictionary
        data = json.loads(request.body)
        quantity = int(data.get('quantity'))
        
        # Find the PassportSize instance
        passport_size = PassportSize.objects.get(id=sq_id)
        # Update the quantity
        passport_size.quantity = quantity
        passport_size.save()

        # Return success response
        return JsonResponse({'status': 'success', 'message': 'Quantity updated successfully'})
    
    except PassportSize.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'PassportSize not found'}, status=404)
    
    except Exception as e:
        # Handle unexpected errors
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@cutter_required
@require_POST
def delete_passport_size_quantity(request, sq_id):
    passport_size = get_object_or_404(PassportSize, id=sq_id)
    passport_size.delete()
    return JsonResponse({'status': 'success'}, status=200)

@method_decorator([login_required, cutter_required], name='dispatch')
class PassportDetailView(DetailView):
    model = Passport
    template_name = 'cutter/passports/detail.html'
    context_object_name = 'passport'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        passport = context['passport']
        context['passport_sizes'] = passport.passport_sizes.all().order_by('size_quantity__size')
        context['passport_rolls'] = passport.passport_rolls.all()
        return context

@login_required
@cutter_required
@require_POST
def passport_delete(request, pk):
    passport = get_object_or_404(Passport, pk=pk)
    order = passport.order
    client_order = order.client_order

    with transaction.atomic():
        if passport.is_completed:
            total_quantity = PassportSize.objects.filter(passport=passport).aggregate(Sum('quantity'))['quantity__sum'] or 0

            if order.completed_quantity is not None:
                order.completed_quantity -= total_quantity
                order.save()

        passport_rolls = PassportRoll.objects.filter(passport=passport)
        for passport_roll in passport_rolls:
            roll = passport_roll.roll
            if roll.used_meters is not None:
                roll.used_meters -= passport_roll.meters
                roll.save()

        passport.delete()
        messages.success(request, 'Passport deleted successfully.')

        remaining_passports = Passport.objects.filter(order=order).exists()
        if not remaining_passports:
            order.status = Order.NEW
            order.save()
            messages.info(request, 'Order status set to NEW due to no remaining passports.')

        other_in_progress_orders = Order.objects.filter(client_order=client_order, status=Order.IN_PROGRESS).exists()
        if not other_in_progress_orders:
            client_order.status = ClientOrder.NEW
            client_order.save()
            messages.info(request, 'ClientOrder status set to NEW as no other orders are IN PROGRESS.')

    return redirect(reverse('order_detail_cutter', args=[order.id]))

@login_required
@cutter_required
def mark_as_sewing(request, passport_size_id):
    try:
        passport_size = PassportSize.objects.get(id=passport_size_id)
        operations = Operation.objects.filter(node__type=Node.CUTTING)
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