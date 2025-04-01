from collections import defaultdict
import json
import openpyxl

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.db import transaction
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView 
from django.views import View
from openpyxl import Workbook
from openpyxl.styles import  Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from django.db.models import Q
from django.db.models import IntegerField
from decimal import Decimal
from django.db.models.functions import Cast

from ..decorators import technologist_required
from ..forms import *
from ..models import *


CACHE_TTL = getattr(settings, 'CACHE_TTL', DEFAULT_TIMEOUT)

# @cache_page(CACHE_TTL)
@login_required
@technologist_required
def technologist_page(request):
    context = {
               'sidebar_type': 'technology'
               }
    return render(request, 'technologist_page.html', context)

@method_decorator([login_required, technologist_required], name='dispatch')
class EmployeeListView(ListView):
    model = UserProfile
    template_name = 'technologist/employees/list.html'
    context_object_name = 'employees'
    paginate_by = 10

    def get_queryset(self):
        return UserProfile.objects.filter(
            is_archived=False
        ).exclude(user__username='admin').annotate(
            employee_id_int=Cast('employee_id', IntegerField())
        ).order_by('employee_id_int')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['upload_form'] = UploadFileForm()
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class EmployeeCreateView(CreateView):
    template_name = 'technologist/employees/create.html'
    form_class = UserWithProfileForm
    success_url = reverse_lazy('employee_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class EmployeeDetailView(DetailView):
    model = UserProfile
    template_name = 'technologist/employees/detail.html'
    context_object_name = 'employee'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@login_required
@technologist_required
def employee_edit(request, pk):
    user_profile = get_object_or_404(UserProfile, pk=pk)
    user = user_profile.user

    if request.method == 'POST':
        user_form = UserEditForm(request.POST, instance=user)
        if user_form.is_valid():
            user_form.save()
            messages.success(request, 'Employee details updated successfully.')
            return redirect('employee_list')
    else:
        user_form = UserEditForm(instance=user)

    context = {'user_form': user_form, 'user_profile': user_profile, 'sidebar_type': 'technology'}
    return render(request, 'technologist/employees/edit.html', context)

@method_decorator([login_required, technologist_required], name='dispatch')
class EmployeeDeleteView(DeleteView):
    model = UserProfile
    template_name = 'technologist/employees/delete.html'
    success_url = reverse_lazy('employee_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class EmployeeArchiveView(UpdateView):
    model = UserProfile
    template_name = 'technologist/employees/list.html'
    success_url = reverse_lazy('employee_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
    def post(self, request, *args, **kwargs):
        employee = self.get_object()
        employee.is_archived = True
        employee.save()
        return HttpResponseRedirect(self.success_url)
   
@method_decorator([login_required, technologist_required], name='dispatch')
class EmployeeUnArchiveView(UpdateView):
    model = UserProfile
    template_name = 'technologist/employees/list.html'
    success_url = reverse_lazy('employee_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
    def post(self, request, *args, **kwargs):
        employee = self.get_object()
        employee.is_archived = False
        employee.save()
        return HttpResponseRedirect(self.success_url)
     
@method_decorator([login_required, technologist_required], name='dispatch')
class ArchivedEmployeeListView(ListView):
    template_name = 'technologist/employees/list.html'
    context_object_name = 'employees'
    paginate_by = 10
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

    def get_queryset(self):
        return UserProfile.objects.filter(
            is_archived=True
            ).order_by('employee_id')
    

@login_required
@technologist_required
@require_POST
def employee_upload(request):
    form = UploadFileForm(request.POST, request.FILES)
    if form.is_valid():
        excel_file = request.FILES['excel_file']
        try:
            workbook = openpyxl.load_workbook(excel_file)
            sheet = workbook.active
            # Get the current company from thread-local storage.
            current_company = get_current_company()
            if current_company is None:
                messages.error(request, 'No company found in context.')
                return redirect(reverse_lazy('employee_list'))

            with transaction.atomic():
                # Iterate rows skipping the header (starting at row 2)
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    first_name, last_name, employee_id, emp_type, password = row
                    
                    # Generate username using current company ID and employee ID.
                    username = f"{current_company.id}-{employee_id}"
                    
                    try:
                        # Because of your custom manager, this lookup is already company-aware.
                        profile = UserProfile.objects.get(employee_id=employee_id)
                    except UserProfile.DoesNotExist:
                        # Create a new user and UserProfile.
                        user = User.objects.create(
                            username=username,
                            first_name=first_name,
                            last_name=last_name
                        )
                        user.set_password(password)
                        user.save()
                        print(user)
                        # The save method on CompanyAwareModel will assign the current company.
                        profile = UserProfile.objects.create(
                            user=user,
                            employee_id=employee_id,
                            type=int(emp_type) if emp_type is not None else UserProfile.EMPLOYEE
                        )
                    else:
                        # Update existing user and profile.
                        user = profile.user
                        user.first_name = first_name
                        user.last_name = last_name
                        user.username = username
                        user.set_password(password)
                        user.save()
                        
                        profile.type = int(emp_type) if emp_type is not None else UserProfile.EMPLOYEE
                        profile.save()

            messages.success(request, 'Employees uploaded successfully.')
            return redirect(reverse_lazy('employee_list'))
        except Exception as e:
            messages.error(request, f'Error processing the file: {e}')
            return redirect(reverse_lazy('employee_list'))
        finally:
            workbook.close()
    else:
        messages.error(request, 'Invalid file format.')
        return redirect(reverse_lazy('employee_list'))
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ClientListView(ListView):
    model = Client
    template_name = 'technologist/clients/list.html'
    context_object_name = 'clients'
    paginate_by = 10
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    def get_queryset(self):
        return Client.objects.filter(
            is_archived=False
            ).order_by('name')

@method_decorator([login_required, technologist_required], name='dispatch')
class ArchivedClientListView(ListView):
    template_name = 'technologist/clients/list.html'
    context_object_name = 'clients'
    paginate_by = 10
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    def get_queryset(self):
        return Client.objects.filter(            
            is_archived=True
            ).order_by('name')

@method_decorator([login_required, technologist_required], name='dispatch')
class ClientCreateView(CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'technologist/clients/create.html'
    success_url = reverse_lazy('client_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ClientDetailView(DetailView):
    model = Client
    template_name = 'technologist/clients/detail.html'
    context_object_name = 'client'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ClientUpdateView(UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'technologist/clients/edit.html'
    def get_success_url(self):
        return reverse('client_detail', kwargs={'pk': self.object.pk})
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ClientDeleteView(DeleteView):
    model = Client
    template_name = 'technologist/clients/delete.html'
    success_url = reverse_lazy('client_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ClientArchiveView(UpdateView):
    model = Client
    template_name = 'technologist/clients/delete.html'
    success_url = reverse_lazy('client_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    def post(self, request, *args, **kwargs):
        clien_order = self.get_object()
        clien_order.is_archived = True
        clien_order.save()
        return HttpResponseRedirect(self.success_url)


@method_decorator([login_required, technologist_required], name='dispatch')
class ClientUnArchiveView(UpdateView):
    model = Client
    template_name = 'technologist/clients/delete.html'
    success_url = reverse_lazy('client_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    def post(self, request, *args, **kwargs):
        clien_order = self.get_object()
        clien_order.is_archived = False
        clien_order.save()
        return HttpResponseRedirect(self.success_url)



@method_decorator([login_required, technologist_required], name='dispatch')
class ClientOrderListView(ListView):
    model = ClientOrder
    template_name = 'technologist/client/orders/list.html'
    context_object_name = 'orders'
    paginate_by = 10
    form_class = DateRangeForm 

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_archived=False)
        today = timezone.localdate()

        # Read the term filter from GET. Defaults to 'upcoming' if not provided.
        term_filter = self.request.GET.get('term', 'upcoming').lower()

        if term_filter == 'upcoming':
            # Upcoming orders: term is today or later; sort ascending (soonest first)
            queryset = queryset.filter(term__gte=today).order_by('term')
        elif term_filter == 'passed':
            # Passed orders: term is before today; sort descending (most recent first)
            queryset = queryset.filter(term__lt=today).order_by('-term')
        else:
            # Default to upcoming if unknown value is provided
            queryset = queryset.filter(term__gte=today).order_by('term')

        # Apply optional date range filtering
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
        orders_with_days_left = []

        # Calculate days_left for display. (Negative values for passed orders.)
        for order in context['orders']:
            days_left = (order.term - today).days
            orders_with_days_left.append({'order': order, 'days_left': days_left})
        context['orders_with_days_left'] = orders_with_days_left

        # Pass the current term filter for use in the template
        context['term_filter'] = self.request.GET.get('term', 'upcoming').lower()
        context['ClientOrder'] = ClientOrder
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ClientOrderCreateView(CreateView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'technologist/client/orders/create.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        form.save_m2m()
        redirect_url = reverse('client_order_detail', kwargs={'pk': self.object.pk})
        return HttpResponseRedirect(redirect_url)
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ClientOrderDetailView(DetailView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'technologist/client/orders/detail.html'
    context_object_name = 'client_order'

    def get_context_data(self, **kwargs):
        context = super(ClientOrderDetailView, self).get_context_data(**kwargs)
        client_order = context['client_order']
        context['orders'] = client_order.orders.all()
        today = timezone.localdate()
        if client_order.term >= today:
            days_left = (client_order.term - today).days
        else:
            days_left = 0
        context['days_left'] = days_left
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ClientOrderUpdateView(UpdateView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'technologist/client/orders/edit.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

    def get_success_url(self):
        return reverse('client_order_detail', kwargs={'pk': self.object.pk})
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ClientOrderDeleteView(DeleteView):
    model = ClientOrder
    template_name = 'technologist/client/orders/delete.html'
    success_url = reverse_lazy('client_order_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ClientOrderArchiveView(UpdateView):
    model = ClientOrder
    template_name = 'technologist/client/orders/delete.html'
    success_url = reverse_lazy('client_order_list')
        
    def post(self, request, *args, **kwargs):
        clien_order = self.get_object()
        clien_order.is_archived = True
        clien_order.save()
        return HttpResponseRedirect(self.success_url)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    

@method_decorator([login_required, technologist_required], name='dispatch')
class ClientOrderUnArchiveView(UpdateView):
    model = ClientOrder
    template_name = 'technologist/client/orders/delete.html'
    success_url = reverse_lazy('client_order_list')
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    def post(self, request, *args, **kwargs):
        clien_order = self.get_object()
        clien_order.is_archived = False
        clien_order.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ArchivedClientOrderListView(ListView):
    model = ClientOrder
    template_name = 'technologist/client/orders/list.html'  # Use a separate template if necessary
    context_object_name = 'archived_orders'
    paginate_by = 10
    form_class = DateRangeForm 

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_archived=True)
        today = timezone.localdate()

        # Read the term filter from GET. Defaults to 'upcoming' if not provided.
        term_filter = self.request.GET.get('term', 'upcoming').lower()

        if term_filter == 'upcoming':
            # Upcoming orders: term is today or later; sort ascending (soonest first)
            queryset = queryset.filter(term__gte=today).order_by('term')
        elif term_filter == 'passed':
            # Passed orders: term is before today; sort descending (most recent first)
            queryset = queryset.filter(term__lt=today).order_by('-term')
        else:
            # Default to upcoming if unknown value is provided
            queryset = queryset.filter(term__gte=today).order_by('term')

        # Apply optional date range filtering
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

        # Calculate days_left for display. (Negative values for passed orders.)
        orders_with_days_left = []
        for order in context['archived_orders']:
            days_left = (order.term - today).days
            orders_with_days_left.append({'order': order, 'days_left': days_left})
        context['orders_with_days_left'] = orders_with_days_left

        # Pass the current term filter for use in the template
        context['term_filter'] = self.request.GET.get('term', 'upcoming').lower()
        context['ClientOrder'] = ClientOrder
        context['sidebar_type'] = 'technology'
        return context
    
@login_required
@technologist_required
@require_POST
def client_order_complete(request, pk):
    client_order = get_object_or_404(ClientOrder, pk=pk)
    STATUSES = [ClientOrder.NEW, ClientOrder.IN_PROGRESS, ClientOrder.COMPLETED]

    # Get the index of the current status
    current_index = STATUSES.index(client_order.status)

    # Calculate the next index, cycling back to 0 if at the end
    next_index = (current_index + 1) % len(STATUSES)

    # Set the status to the next one
    client_order.status = STATUSES[next_index]

    client_order.save()

    return redirect('client_order_detail', pk=client_order.pk)

@require_POST
@login_required
def add_client_api(request):
    form = ClientForm(request.POST)
    if form.is_valid():
        client = form.save()
        data = {
            'success': True,
            'client_id': client.id,
            'client_name': client.name,
        }
        return JsonResponse(data)
    else:
        # Return form errors as JSON (status code 400)
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)



@method_decorator([login_required, technologist_required], name='dispatch')
class OrderListView(ListView):
    model = Order
    template_name = 'technologist/orders/list.html'
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
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class OrderDetailView(DetailView):
    model = Order
    template_name = 'technologist/orders/detail.html'
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

        # # ----- Other context data (pass along your existing context) -----
        associated_cuts = order.cuts.all().order_by('number')
        # passports = Passport.objects.filter(cut__in=associated_cuts).order_by('cut__number', 'number')
        # size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'passport_size_id': None, 'extra': None}))
        # total_per_size = defaultdict(int)
        # for passport in passports:
        #     passport_number = passport.id
        #     for passport_size in passport.passport_sizes.all():
        #         size = passport_size.size_quantity.size
        #         extra_key = f"{size}-{passport_size.extra}" if passport_size.extra else size
        #         size_data[extra_key][passport_number]['quantity'] += passport_size.quantity
        #         size_data[extra_key][passport_number]['passport_size_id'] = passport_size.id
        #         size_data[extra_key][passport_number]['extra'] = passport_size.extra
        #         total_per_size[size] += passport_size.quantity

        # required_missing = {sq.size: {'required': sq.quantity, 'missing': sq.quantity - total_per_size.get(sq.size, 0)}
        #                     for sq in order.size_quantities.all().order_by('size')}
        # for size in total_per_size:
        #     if size not in required_missing:
        #         required_missing[size] = {'required': 0, 'missing': -total_per_size[size]}

        # def sort_key(x):
        #     parts = x.split('-')
        #     try:
        #         return int(parts[0]), x
        #     except ValueError:
        #         return float('inf'), x
        # sorted_size_data_keys = sorted(size_data.keys(), key=sort_key)

        context.update({
            'pivot_data': pivot_data,  # Our new pivoted required data
            'all_sizes': all_sizes,    # List of sizes for the header row
            # (Include your other context items as before.)
            # 'size_data': {k: dict(size_data[k]) for k in sorted_size_data_keys},
            # 'total_per_size': dict(total_per_size),
            # 'required_missing': required_missing,
            'days_left': (order.client_order.term - timezone.now().date()).days if order.client_order.term >= timezone.now().date() else 0,
            'associated_cuts': associated_cuts,
            'sidebar_type': 'technology'
        })
        return context  

@method_decorator([login_required, technologist_required], name='dispatch')
class OrderCreateView(CreateView):
    model = Order
    form_class = OrderForm
    template_name = 'technologist/orders/create.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.client_order = get_object_or_404(ClientOrder, pk=self.kwargs['client_order_pk'])
        self.object.save()
        form.save_m2m()
        try:
            self.handle_size_quantities(self.object, self.request.POST)
        except ValidationError as e:
            # If a duplicate combination is found, delete the created order
            self.object.delete()
            form.add_error(None, e.message)
            return self.form_invalid(form)
        return redirect('order_detail', pk=self.object.pk)

    def handle_size_quantities(self, order, post_data):
        """
        Process the dynamic table data:
        - Ensures that each row's (color, fabric) combination is unique.
        - Sums up all provided quantities per cell.
        - Creates SizeQuantity objects (with SKU) and associates them with the order.
        - Updates the order's overall quantity based on the sum.
        """
        used_combinations = set()  # To track (color_id, fabric_id) per row
        used_colors = set()
        used_fabrics = set()
        sizes = []
        total_quantity = 0  # Running total of quantities

        # Retrieve the sizes from header inputs.
        col = 0
        while f'header_{col}' in post_data:
            sizes.append(post_data[f'header_{col}'])
            col += 1

        row = 0
        while f'row-{row}_color' in post_data:
            color_id = post_data.get(f'row-{row}_color')
            fabric_id = post_data.get(f'row-{row}_fabric')

            # Validate uniqueness of the color–fabric combination per row.
            combination_key = (color_id, fabric_id)
            if combination_key in used_combinations:
                raise ValidationError("Цвет-ткань должна быть уникальной.")
            used_combinations.add(combination_key)

            # Lookup the color and fabric objects.
            color = Color.objects.filter(pk=color_id).first() if color_id else None
            fabric = Fabrics.objects.filter(pk=fabric_id).first() if fabric_id else None

            if color:
                used_colors.add(color)
            if fabric:
                used_fabrics.add(fabric)

            # Process each size column for the current row.
            for col_index, size in enumerate(sizes):
                quantity = post_data.get(f'cell_{row}_{col_index}', 0)
                if quantity and int(quantity) > 0:
                    quantity_int = int(quantity)
                    total_quantity += quantity_int
                    # Get the SKU value; if SKU field is absent or empty, default to an empty string.
                    sku = post_data.get(f'sku_{row}_{col_index}', '').strip()
                    size_qty = SizeQuantity.objects.create(
                        size=size,
                        quantity=quantity_int,
                        sku=sku,  # Save SKU along with quantity.
                        color=color,
                        fabrics=fabric
                    )
                    order.size_quantities.add(size_qty)
            row += 1

        # Update the order's overall quantity with the calculated total.
        order.quantity = total_quantity
        order.save(update_fields=['quantity'])

        # Save the collected colors and fabrics to the order.
        if used_colors:
            order.colors.add(*used_colors)
        if used_fabrics:
            order.fabrics.add(*used_fabrics)

    def get_context_data(self, **kwargs):
        context = super(OrderCreateView, self).get_context_data(**kwargs)
        context['client_order_pk'] = self.kwargs.get('client_order_pk')
        context['sidebar_type'] = 'technology'
        # Pass available colors and fabrics (and sizes) for use in the template.
        context['colors'] = Color.objects.filter(is_archived=False).order_by('name')
        context['fabrics'] = Fabrics.objects.filter(is_archived=False).order_by('name')
        return context
    
@require_POST
@login_required
def add_color_api(request):
    form = ColorForm(request.POST)
    if form.is_valid():
        color = form.save()
        data = {
            'success': True,
            'color_id': color.id,
            'color_name': color.name,
        }
        return JsonResponse(data)
    else:
        # Return form errors as JSON (status code 400)
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    
@require_POST
@login_required
def add_fabric_api(request):
    form = FabricsForm(request.POST)
    if form.is_valid():
        fabric = form.save()
        data = {
            'success': True,
            'fabric_id': fabric.id,
            'fabric_name': fabric.name,
        }
        return JsonResponse(data)
    else:
        # Return form errors as JSON (status code 400)
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    
@method_decorator([login_required, technologist_required], name='dispatch')
class OrderUpdateView(UpdateView):
    model = Order
    form_class = OrderForm
    template_name = 'technologist/orders/edit.html'

    def get_context_data(self, **kwargs):
        context = super(OrderUpdateView, self).get_context_data(**kwargs)
        context['client_order_pk'] = self.object.client_order.pk
        context['sidebar_type'] = 'technology'
        context['colors'] = Color.objects.filter(is_archived=False).order_by('name')
        context['fabrics'] = Fabrics.objects.filter(is_archived=False).order_by('name')
        
        # --- Build the table header & rows from existing size quantities ---
        size_quantities = self.object.size_quantities.all()
        sizes = []
        for sq in size_quantities:
            if sq.size not in sizes:
                sizes.append(sq.size)
        if not sizes:
            sizes = ['']
        
        rows_dict = {}
        for sq in size_quantities:
            key = (sq.color_id, sq.fabrics_id)
            if key not in rows_dict:
                rows_dict[key] = {}
            # Include sku in the cell data.
            rows_dict[key][sq.size] = {
                'quantity': sq.quantity,
                'id': sq.pk,
                'sku': sq.sku  # Added SKU here.
            }
        
        table_rows = []
        for (color_id, fabric_id), cells in rows_dict.items():
            row_data = {
                'color_id': color_id,
                'fabric_id': fabric_id,
                'cells': []
            }
            for size in sizes:
                if size in cells:
                    row_data['cells'].append({
                        'size': size,
                        'quantity': cells[size]['quantity'],
                        'id': cells[size]['id'],
                        'sku': cells[size]['sku']  # Pass along any saved SKU.
                    })
                else:
                    row_data['cells'].append({
                        'size': size,
                        'quantity': '',
                        'id': '',
                        'sku': ''
                    })
            table_rows.append(row_data)
        
        if not table_rows:
            table_rows = [{
                'color_id': '',
                'fabric_id': '',
                'cells': [{'size': sizes[0], 'quantity': '', 'id': '', 'sku': ''}]
            }]
        
        context['table_sizes'] = sizes
        context['table_rows'] = table_rows
        context['row_count'] = len(table_rows)
        context['col_count'] = len(sizes)
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        form.save_m2m()
        try:
            self.handle_size_quantities_update(self.object, self.request.POST)
        except ValidationError as e:
            form.add_error(None, e.message)
            return self.form_invalid(form)
        return redirect('order_detail', pk=self.object.pk)

    def handle_size_quantities_update(self, order, post_data):
        """
        Process the dynamic table for editing:
          • Ensures that each (color, fabric) combination is unique.
          • Updates existing SizeQuantity objects, creates new ones as needed,
            or deletes ones where quantity is now 0/empty.
          • Sums up all provided quantities and updates order.quantity accordingly.
          • Updates the order's many-to-many colors and fabrics.
          • Also handles the SKU value for each cell.
        """
        used_combinations = set()  # Track (color_id, fabric_id) per row for uniqueness.
        used_colors = set()
        used_fabrics = set()
        sizes = []
        total_quantity = 0  # Running total of all quantities

        col = 0
        while f'header_{col}' in post_data:
            sizes.append(post_data[f'header_{col}'])
            col += 1

        processed_sq_ids = set()
        row = 0
        while f'row-{row}_color' in post_data:
            color_id = post_data.get(f'row-{row}_color')
            fabric_id = post_data.get(f'row-{row}_fabric')
            combination_key = (color_id, fabric_id)
            if combination_key in used_combinations:
                raise ValidationError("Цвет-ткань должна быть уникальной.")
            used_combinations.add(combination_key)

            # Lookup color and fabric objects.
            color = Color.objects.filter(pk=color_id).first() if color_id else None
            fabric = Fabrics.objects.filter(pk=fabric_id).first() if fabric_id else None

            if color:
                used_colors.add(color)
            if fabric:
                used_fabrics.add(fabric)
            
            # Process each cell in this row.
            for col_index, size in enumerate(sizes):
                cell_val = post_data.get(f'cell_{row}_{col_index}', '')
                cell_sq_id = post_data.get(f'cell_id_{row}_{col_index}', None)
                # Retrieve SKU value (if any) and strip whitespace.
                sku_val = post_data.get(f'sku_{row}_{col_index}', '').strip()
                if cell_val and cell_val.isdigit() and int(cell_val) > 0:
                    quantity_val = int(cell_val)
                    total_quantity += quantity_val
                    if cell_sq_id:
                        try:
                            sq_obj = SizeQuantity.objects.get(pk=cell_sq_id)
                            sq_obj.quantity = quantity_val
                            sq_obj.size = size  # Update header if changed.
                            sq_obj.color = color
                            sq_obj.fabrics = fabric
                            sq_obj.sku = sku_val  # Update SKU.
                            sq_obj.save()
                            processed_sq_ids.add(sq_obj.pk)
                        except SizeQuantity.DoesNotExist:
                            sq_obj = SizeQuantity.objects.create(
                                size=size,
                                quantity=quantity_val,
                                sku=sku_val,
                                color=color,
                                fabrics=fabric
                            )
                            order.size_quantities.add(sq_obj)
                            processed_sq_ids.add(sq_obj.pk)
                    else:
                        sq_obj = SizeQuantity.objects.create(
                            size=size,
                            quantity=quantity_val,
                            sku=sku_val,
                            color=color,
                            fabrics=fabric
                        )
                        order.size_quantities.add(sq_obj)
                        processed_sq_ids.add(sq_obj.pk)
                else:
                    # If cell is empty or 0 but an object existed, remove it.
                    if cell_sq_id:
                        try:
                            sq_obj = SizeQuantity.objects.get(pk=cell_sq_id)
                            order.size_quantities.remove(sq_obj)
                            sq_obj.delete()
                        except SizeQuantity.DoesNotExist:
                            pass
            row += 1

        # (Optional) Remove any SizeQuantity not present in the submitted data.
        for sq in order.size_quantities.all():
            if sq.pk not in processed_sq_ids:
                order.size_quantities.remove(sq)
                sq.delete()

        # Update order many-to-many fields.
        if used_colors:
            order.colors.set(list(used_colors))
        else:
            order.colors.clear()
        if used_fabrics:
            order.fabrics.set(list(used_fabrics))
        else:
            order.fabrics.clear()

        # Finally, update the order's overall quantity.
        order.quantity = total_quantity
        order.save(update_fields=['quantity'])

@method_decorator([login_required, technologist_required], name='dispatch')
class OrderDeleteView(DeleteView):
    model = Order
    template_name = 'technologist/orders/delete.html'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    def get_success_url(self):
        return reverse('client_order_detail', kwargs={'pk': self.object.client_order.pk})
    
@method_decorator([login_required, technologist_required], name='dispatch')
class CutDetailTechnologistView(DetailView):
    model = Cut
    template_name = 'technologist/cuts/detail.html'
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
            'sidebar_type': 'technology'
        })
        return context
    
@login_required
@technologist_required
def assign_operations(request, passport_id):
    passport = get_object_or_404(Passport, pk=passport_id)
    model_operations = ModelOperation.objects.filter(
        model=passport.cut.order.model
    ).select_related('operation').order_by('order')
    operations = [model_op.operation for model_op in model_operations]
    size_quantities = PassportSize.objects.filter(passport=passport).order_by('size_quantity__size')

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        data = json.loads(request.body)
        operation_id = data.get('operation_id')
        passport_size_id = data.get('passport_size_id')
        value = data.get('value')

        try:
            with transaction.atomic():
                passport_size = PassportSize.objects.get(id=passport_size_id)
                total_quantity = passport_size.quantity

                entries = value.split(',')
                for entry in entries:
                    if '(' in entry and ')' in entry:
                        employee_id_input, quantity = entry.split('(')
                        employee_id_input = employee_id_input.strip()
                        quantity = int(quantity.strip(' )'))
                    else:
                        employee_id_input = entry
                        quantity = total_quantity

                    employee_profile = UserProfile.objects.filter(employee_id=employee_id_input).first()
                    if not employee_profile:
                        continue

                    work, created = Work.objects.get_or_create(
                        operation_id=operation_id,
                        passport_size=passport_size,
                    )
                    AssignedWork.objects.create(
                        work=work,
                        employee=employee_profile,
                        quantity=quantity
                    )
                    
                return JsonResponse({'status': 'success'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    work_by_op_and_size = {}
    for assigned_work in AssignedWork.objects.filter(work__passport_size__passport=passport).select_related('employee', 'work__operation', 'work__passport_size'):
        # Key as a tuple of operation_id and passport_size_id
        key = (assigned_work.work.operation_id, assigned_work.work.passport_size_id)
        if key not in work_by_op_and_size:
            work_by_op_and_size[key] = [assigned_work]
        else:
            work_by_op_and_size[key].append(assigned_work)

    return render(request, 'technologist/passports/assign_operations.html', {
        'passport': passport,
        'operations': operations,
        'size_quantities': size_quantities,
        'work_by_op_and_size': work_by_op_and_size,
        'sidebar_type': 'technology'
    })

@login_required
@technologist_required
def assign_operations_by_cut(request, cut_id):
    cut = get_object_or_404(Cut, pk=cut_id)
    model_operations = ModelOperation.objects.filter(
        model=cut.order.model
    ).select_related('operation').order_by('order')
    operations = [model_op.operation for model_op in model_operations]

    # Get all passports for this cut, ordered by number (or creation order)
    passports = cut.passports.all().order_by('number')
    
    # For each passport, get its passport sizes ordered by size.
    passport_sizes_by_passport = {}
    for passport in passports:
        sizes = passport.passport_sizes.all().order_by('size_quantity__size')
        passport_sizes_by_passport[passport.id] = sizes

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        import json
        from django.db import transaction
        data = json.loads(request.body)
        operation_id = data.get('operation_id')
        passport_size_id = data.get('passport_size_id')
        value = data.get('value')

        try:
            with transaction.atomic():
                passport_size = PassportSize.objects.get(id=passport_size_id)
                total_quantity = passport_size.quantity

                entries = value.split(',')
                for entry in entries:
                    if '(' in entry and ')' in entry:
                        employee_id_input, quantity = entry.split('(')
                        employee_id_input = employee_id_input.strip()
                        quantity = int(quantity.strip(' )'))
                    else:
                        employee_id_input = entry.strip()
                        quantity = total_quantity

                    employee_profile = UserProfile.objects.filter(
                        employee_id=employee_id_input,
                        type=UserProfile.EMPLOYEE,
                        
                    ).first()
                    if not employee_profile:
                        raise Exception(f"Employee not found.")

                    work, created = Work.objects.get_or_create(
                        operation_id=operation_id,
                        passport_size=passport_size,
                    )
                    AssignedWork.objects.create(
                        work=work,
                        employee=employee_profile,
                        quantity=quantity
                    )
                return JsonResponse({'status': 'success'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    # Build a dictionary of already assigned works, keyed by (operation_id, passport_size_id)
    work_by_op_and_size = {}
    for aw in AssignedWork.objects.filter(work__passport_size__passport__in=passports).select_related('employee', 'work__operation', 'work__passport_size'):
        key = (aw.work.operation_id, aw.work.passport_size_id)
        work_by_op_and_size.setdefault(key, []).append(aw)

    return render(request, 'technologist/passports/assign_operations_by_cut.html', {
        'cut': cut,
        'operations': operations,
        'passports': passports,
        'passport_sizes_by_passport': passport_sizes_by_passport,
        'work_by_op_and_size': work_by_op_and_size,
        'sidebar_type': 'technology'
    })

@require_POST
@technologist_required
@login_required
def update_passport_quantity(request):
    """
    Updates the factual quantity for a given PassportSize and updates all 
    AssignedWork records related to that PassportSize.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON."}, status=400)
    
    passport_size_id = data.get("passport_size_id")
    new_quantity = data.get("new_quantity")
    
    if passport_size_id is None or new_quantity is None:
        return JsonResponse({"status": "error", "message": "Missing parameters."}, status=400)
    
    try:
        new_quantity = int(new_quantity)
    except ValueError:
        return JsonResponse({"status": "error", "message": "Invalid quantity."}, status=400)
    
    try:
        passport_size = PassportSize.objects.get(id=passport_size_id)
    except PassportSize.DoesNotExist:
        return JsonResponse({"status": "error", "message": "PassportSize not found."}, status=404)
    
    # Update the factual field of PassportSize.
    passport_size.factual = new_quantity
    passport_size.save()
    
    # Update all AssignedWork records related to this PassportSize.
    AssignedWork.objects.filter(work__passport_size=passport_size).update(quantity=new_quantity)
    
    return JsonResponse({"status": "success"})

@login_required
@technologist_required
@require_POST
def update_work(request):
    data = json.loads(request.body)
    assigned_work_id = data.get('work_id')
    value = data.get('value')

    try:
        current_assignment = AssignedWork.objects.get(id=assigned_work_id)
        work = Work.objects.get(id=current_assignment.work.id)

        if not value.strip():
            current_assignment.delete()
            remaining_assignments = AssignedWork.objects.filter(work=work).exists()
            if not remaining_assignments:
                work.delete()
            return JsonResponse({'status': 'success'})

        new_assignments_data = value.split(',')
        first = True  # Flag to track the first item

        for item in new_assignments_data:
            employee_id, quantity = item.split('(')
            employee_id = employee_id.strip()
            quantity = int(quantity.strip(' )'))

            employee_profile = UserProfile.objects.filter(
                employee_id=employee_id, type=UserProfile.EMPLOYEE,
                ).first()

            if not employee_profile:
                raise Exception(f"Employee not found.")

            # Handle the first item by updating existing assigned work
            if first:
                current_assignment.employee = employee_profile
                current_assignment.quantity = quantity
                current_assignment.save()
                first = False  # Update the flag after handling the first item
            else:
                # Create new assigned works for subsequent items
                AssignedWork.objects.create(
                    work=work,
                    employee=employee_profile,
                    quantity=quantity
                )

        return JsonResponse({'status': 'success'})

    except Work.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Work not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
@technologist_required
def update_work_success(request):
    work_id = request.POST.get('work_id')
    is_success = request.POST.get('is_success') == 'true'

    try:
        assigned_work = AssignedWork.objects.get(pk=work_id)
        assigned_work.is_success = is_success
        assigned_work.save()

        return JsonResponse({'status': 'success'})
    except AssignedWork.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Assigned work not found'}, status=404)

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationListView(ListView):
    model = Operation
    template_name = 'technologist/operations/list.html'
    context_object_name = 'operations'

    def get_paginate_by(self, queryset):
        node_id = self.request.GET.get('node', None)
        if node_id:
            return None
        return 15

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_archived=False).order_by('number')
        node_id = self.request.GET.get('node', None)
        if node_id:
            queryset = queryset.filter(node_id=node_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        nodes = Node.objects.filter(is_archived=False).order_by('name')
        context['nodes'] = nodes
        context['selected_node'] = self.request.GET.get('node', '')
        context['upload_form'] = UploadFileForm()
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationCreateView(CreateView):
    model = Operation
    form_class = OperationForm
    template_name = 'technologist/operations/create.html'
    success_url = reverse_lazy('operation_create')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationDetailView(DetailView):
    model = Operation
    template_name = 'technologist/operations/detail.html'
    context_object_name = 'operation'
    def get_context_data(self, **kwargs):
        context = super(OperationDetailView, self).get_context_data(**kwargs)
        operation = self.object
        models = Model.objects.filter(operations=operation)
        context['models'] = models
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationUpdateView(UpdateView):
    model = Operation
    form_class = OperationForm
    template_name = 'technologist/operations/edit.html'
    success_url = reverse_lazy('operation_list')  # Update this to your desired success URL

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class OperationDeleteView(DeleteView):
    model = Operation
    template_name = 'technologist/operations/delete.html'
    success_url = reverse_lazy('operation_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ArchivedOperationListView(ListView):
    model = Operation
    template_name = 'technologist/operations/list.html'
    context_object_name = 'operations'
    paginate_by = 10

    def get_queryset(self):
        return Operation.objects.filter(is_archived=True).order_by('number')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        context['archived'] = True
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationArchiveView(UpdateView):
    model = Operation
    template_name = 'technologist/operations/delete.html'
    success_url = reverse_lazy('operation_list')

    def post(self, request, *args, **kwargs):
        operation = self.get_object()
        operation.is_archived = True
        operation.save()
        return HttpResponseRedirect(self.success_url)

@method_decorator([login_required, technologist_required], name='dispatch')
class OperationUnArchiveView(UpdateView):
    model = Operation
    template_name = 'technologist/operations/delete.html'
    success_url = reverse_lazy('archived_operation_list')

    def post(self, request, *args, **kwargs):
        operation = self.get_object()
        operation.is_archived = False
        operation.save()
        return HttpResponseRedirect(self.success_url)

@login_required
@technologist_required
@require_POST
def operation_upload(request):
    form = UploadFileForm(request.POST, request.FILES)
    if form.is_valid():
        excel_file = request.FILES['excel_file']
        workbook = openpyxl.load_workbook(excel_file)
        sheet = workbook.active

        with transaction.atomic():
            for row in sheet.iter_rows(min_row=2, values_only=True):
                number, operation_name, node_name, equipment_name, time, price = row

                node, _ = Node.objects.get_or_create(name=node_name)
                equipment, _ = Equipment.objects.get_or_create(name=equipment_name)
                operation, created = Operation.objects.get_or_create(
                    number=number,
                    defaults={
                        'name': operation_name,
                        'equipment': equipment,
                        'node': node,
                        'preferred_completion_time': time,
                        'payment': price
                    }
                )
                if not created:
                    operation.name = operation_name
                    operation.equipment = equipment
                    operation.node = node
                    operation.preferred_completion_time = time
                    operation.payment = price
                    operation.save()
                print(operation)
        messages.success(request, 'Operations uploaded successfully.')
        return HttpResponseRedirect(reverse_lazy('operation_list'))
    else:
        messages.error(request, 'There was an error with the file upload.')
        return HttpResponseRedirect(reverse_lazy('operation_upload'))
    
@login_required
@technologist_required
def operation_download(request):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Operations"

    headers = ["№ПП (авто генерация)", "Тех-процесс", "Узел", "№ узла", "Оборудование", "Время", "Оплата"]
    sheet.append(headers)

    for operation in Operation.objects.filter(is_archived=False).order_by('number'):
        row = [
            operation.number,
            operation.name,
            operation.node.name if operation.node else "",
            operation.equipment.name if operation.equipment else "",
            operation.preferred_completion_time,
            operation.payment,
        ]
        sheet.append(row)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=operations.xlsx'
    workbook.save(response)
    return response
    
@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentListView(ListView):
    model = Assortment
    template_name = 'technologist/assortments/list.html'
    context_object_name = 'assortments'
    paginate_by = 10
    def get_queryset(self):
        return super().get_queryset().filter(is_archived=False).order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ArchivedAssortmentListView(ListView):
    model = Assortment
    template_name = 'technologist/assortments/list.html'
    context_object_name = 'assortments'
    paginate_by = 10
    def get_queryset(self):
        return super().get_queryset().filter(is_archived=True).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentArchiveView(UpdateView):
    model = Assortment
    template_name = 'technologist/assortments/delete.html'
    success_url = reverse_lazy('assortment_list')
    
    def post(self, request, *args, **kwargs):
        assortment = self.get_object()
        assortment.is_archived = True
        assortment.save()
        return HttpResponseRedirect(self.success_url)


@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentUnArchiveView(UpdateView):
    model = Assortment
    success_url = reverse_lazy('assortment_list')

    def post(self, request, *args, **kwargs):
        assortment = self.get_object()
        assortment.is_archived = False
        assortment.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentCreateView(CreateView):
    model = Assortment
    form_class = AssortmentForm
    template_name = 'technologist/assortments/create.html'
    def get_success_url(self):
        return reverse('assortment_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context


@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentDetailView(DetailView):
    model = Assortment
    template_name = 'technologist/assortments/detail.html'
    context_object_name = 'assortment'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentUpdateView(UpdateView):
    model = Assortment
    form_class = AssortmentForm
    template_name = 'technologist/assortments/edit.html'
    def get_success_url(self):
        return reverse('assortment_detail', kwargs={'pk': self.kwargs.get('pk')})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class AssortmentDeleteView(DeleteView):
    model = Assortment
    template_name = 'technologist/assortments/delete.html'
    success_url = reverse_lazy('assortment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@require_POST
@login_required
def add_assortment_api(request):
    form = AssortmentForm(request.POST)
    if form.is_valid():
        assortment = form.save()
        data = {
            'success': True,
            'assortment_id': assortment.id,
            'assortment_name': assortment.name,
        }
        return JsonResponse(data)
    else:
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)

@method_decorator([login_required, technologist_required], name='dispatch')
class ModelListView(ListView):
    model = Model
    template_name = 'technologist/models/list.html'
    context_object_name = 'models'
    paginate_by = 10

    def get_queryset(self):
        queryset = Model.objects.filter(is_archived=False).order_by('name')
        assortment = self.request.GET.get('assortment', None)
        if assortment:
            queryset = queryset.filter(assortment_id=assortment)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        # Assuming you have an Assortment model and you want only non-archived ones
        context['assortments'] = Assortment.objects.filter(is_archived=False).order_by('name')
        context['selected_assortment'] = self.request.GET.get('assortment', '')
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ArchivedModelListView(ListView):
    model = Model
    template_name = 'technologist/models/list.html'
    context_object_name = 'models'
    paginate_by = 10
    def get_queryset(self):
        return Model.objects.filter(is_archived=True).order_by('name')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ModelArchiveView(UpdateView):
    model = Model
    template_name = 'technologist/models/delete.html'

    def post(self, request, *args, **kwargs):
        model = self.get_object()
        model.is_archived = True
        model.save()
        return HttpResponseRedirect(reverse_lazy('model_list'))


@method_decorator([login_required, technologist_required], name='dispatch')
class ModelUnArchiveView(UpdateView):
    model = Model
    template_name = 'technologist/models/delete.html'

    def post(self, request, *args, **kwargs):
        model = self.get_object()
        model.is_archived = False
        model.save()
        return HttpResponseRedirect(reverse_lazy('model_list'))
        
@login_required
@technologist_required
def model_create(request, pk=None):
    copy_id = request.GET.get('copy')
    original = get_object_or_404(Model, pk=copy_id) if copy_id else None

    if request.method == 'POST':
        form = ModelCustomForm(request.POST, request.FILES, instance=None, copy_id=copy_id)
        if form.is_valid():
            model_instance = form.save()  # Save the new model instance
            # If we're copying from an existing model, copy its BOM entries too.
            if copy_id and original:
                for bom in original.bill_of_materials.all():
                    BillOfMaterials.objects.create(
                        model=model_instance,
                        stock=bom.stock,
                        quantity=bom.quantity
                    )
            # Redirect to BOM creation page (which will display the copied BOM entries)
            return redirect('bom_create', pk=model_instance.id)
    else:
        form = ModelCustomForm(instance=(original if copy_id else None), copy_id=copy_id)
        form.fields['operations'].queryset = Operation.objects.select_related('node').all().order_by(
            'node__name', 'name'
        )

    operations_order_json = ""
    if copy_id:
        operations_order = list(
            ModelOperation.objects.filter(model=original).order_by('order').values_list('operation_id', flat=True)
        )
        operations_order_json = json.dumps(operations_order)

    template_name = 'technologist/models/edit.html' if original else 'technologist/models/create.html'
    context = {
        'form': form,
        'is_copying': bool(copy_id),
        'copy_model': original if copy_id else None,
        'operations_order_json': operations_order_json,
        'sidebar_type': 'technology',
    }
    return render(request, template_name, context)

@method_decorator([login_required, technologist_required], name='dispatch')
class ModelDetailView(DetailView):
    model = Model
    template_name = 'technologist/models/detail.html'
    context_object_name = 'model'

    def get_context_data(self, **kwargs):
        context = super(ModelDetailView, self).get_context_data(**kwargs)
        model = context['model']
        context['ordered_operations'] = model.operations.all().order_by('modeloperation__order')
        context['bom_list'] = model.bill_of_materials.all()  # for the BOM tab
        context['sidebar_type'] = 'technology'
        return context

@login_required
@technologist_required
def model_edit(request, pk):
    model_instance = get_object_or_404(Model, pk=pk)
    
    if request.method == 'POST':
        form = ModelCustomForm(request.POST, request.FILES, instance=model_instance)
        if form.is_valid():
            form.save()
            return redirect('bom_create', pk=pk)
    else:
        form = ModelCustomForm(instance=model_instance)
        form.fields['operations'].queryset = Operation.objects.select_related('node').all().order_by('node__name', 'name')
    
    # Define operations_order_json regardless of the method
    operations_order = list(ModelOperation.objects.filter(model=model_instance).order_by('order').values_list('operation_id', flat=True))
    operations_order_json = json.dumps(operations_order)
    
    return render(request, 'technologist/models/edit.html', {
        'form': form,
        'model': model_instance,
        'operations_order_json': operations_order_json
    })

@method_decorator([login_required, technologist_required], name='dispatch')
class ModelDeleteView(DeleteView):
    model = Model
    template_name = 'technologist/models/delete.html'
    def get_success_url(self):
        return reverse('model_list')



@method_decorator([login_required, technologist_required], name='dispatch')
class NodeListVIew(ListView):
    model = Node
    template_name = 'technologist/nodes/list.html'
    context_object_name = 'nodes'
    paginate_by = 10
    
    def get_queryset(self):
        return Node.objects.filter(is_archived=False).order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context


@method_decorator([login_required, technologist_required], name='dispatch')
class ArchivedNodeListView(ListView):
    model = Node
    template_name = 'technologist/nodes/list.html'
    context_object_name = 'nodes'
    paginate_by = 10

    def get_queryset(self):
        return Node.objects.filter(is_archived=True).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeArchiveView(UpdateView):
    model = Node
    template_name = 'technologist/nodes/delete.html'
    success_url = reverse_lazy('node_list')

    def post(self, request, *args, **kwargs):
        node = self.get_object()
        node.is_archived = True
        node.save()
        return HttpResponseRedirect(self.success_url)

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeUnArchiveView(UpdateView):
    model = Node
    template_name = 'technologist/nodes/delete.html'
    success_url = reverse_lazy('node_list')

    def post(self, request, *args, **kwargs):
        node = self.get_object()
        node.is_archived = False
        node.save()
        return HttpResponseRedirect(self.success_url)

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeCreateView(CreateView):
    model = Node
    form_class = NodeForm
    template_name = 'technologist/nodes/create.html'
    success_url = reverse_lazy('node_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeDetailView(DetailView):
    model = Node
    template_name = 'technologist/nodes/detail.html'
    context_object_name = 'node'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeUpdateView(UpdateView):
    model = Node
    form_class = NodeForm
    template_name = 'technologist/nodes/edit.html'
    success_url = reverse_lazy('node_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class NodeDeleteView(DeleteView):
    model = Node
    template_name = 'technologist/nodes/delete.html'
    success_url = reverse_lazy('node_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@require_POST
@login_required
def add_node_api(request):
    form = NodeForm(request.POST)
    if form.is_valid():
        node = form.save()
        data = {
            'success': True,
            'node_id': node.id,
            'node_name': node.name,
        }
        return JsonResponse(data)
    else:
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


@require_POST
@login_required
def add_equipment_api(request):
    form = EquipmentForm(request.POST)
    if form.is_valid():
        equipment = form.save()
        data = {
            'success': True,
            'equipment_id': equipment.id,
            'equipment_name': equipment.name,
        }
        return JsonResponse(data)
    else:
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)

@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentListView(ListView):
    model = Equipment
    template_name = 'technologist/equipment/list.html'
    context_object_name = 'equipment'
    paginate_by = 10

    def get_queryset(self):
        return Equipment.objects.filter(is_archived=False).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ArchivedEquipmentListView(ListView):
    model = Equipment
    template_name = 'technologist/equipment/list.html'
    context_object_name = 'equipment'
    paginate_by = 10

    def get_queryset(self):
        return Equipment.objects.filter(is_archived=True).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentArchiveView(UpdateView):
    model = Equipment
    template_name = 'technologist/equipment/delete.html'
    success_url = reverse_lazy('equipment_list')

    def post(self, request, *args, **kwargs):
        equipment = self.get_object()
        equipment.is_archived = True
        equipment.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentUnArchiveView(UpdateView):
    model = Equipment
    template_name = 'technologist/equipment/delete.html'
    success_url = reverse_lazy('equipment_list')

    def post(self, request, *args, **kwargs):
        equipment = self.get_object()
        equipment.is_archived = False
        equipment.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentCreateView(CreateView):
    model = Equipment
    form_class = EquipmentForm
    template_name = 'technologist/equipment/create.html'
    success_url = reverse_lazy('equipment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentDetailView(DetailView):
    model = Equipment
    template_name = 'technologist/equipment/detail.html'
    context_object_name = 'equipment'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentUpdateView(UpdateView):
    model = Equipment
    form_class = EquipmentForm
    template_name = 'technologist/equipment/edit.html'
    success_url = reverse_lazy('equipment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class EquipmentDeleteView(DeleteView):
    model = Equipment
    template_name = 'technologist/equipment/delete.html'
    success_url = reverse_lazy('equipment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
@login_required
@technologist_required
def update_assortment_name(request, pk):
    if request.method == 'POST':
        data = json.loads(request.body)
        assortment = Assortment.objects.get(pk=pk)
        assortment.name = data['name']
        assortment.save()
        return JsonResponse({'status': 'success', 'message': 'Assortment name updated successfully'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

@method_decorator([login_required, technologist_required], name='dispatch')
class ColorListView(ListView):
    model = Color
    template_name = 'technologist/color/list.html'
    context_object_name = 'color'
    paginate_by = 10

    def get_queryset(self):
        return Color.objects.filter(is_archived=False).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ArchivedColorListView(ListView):
    model = Color
    template_name = 'technologist/color/list.html'
    context_object_name = 'color'
    paginate_by = 10

    def get_queryset(self):
        return Color.objects.filter(is_archived=True).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ColorArchiveView(UpdateView):
    model = Color
    template_name = 'technologist/color/delete.html'
    success_url = reverse_lazy('color_list')

    def post(self, request, *args, **kwargs):
        color = self.get_object()
        color.is_archived = True
        color.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ColorUnArchiveView(UpdateView):
    model = Color
    template_name = 'technologist/color/delete.html'
    success_url = reverse_lazy('color_list')

    def post(self, request, *args, **kwargs):
        color = self.get_object()
        color.is_archived = False
        color.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ColorCreateView(CreateView):
    model = Color
    form_class = ColorForm
    template_name = 'technologist/color/create.html'
    success_url = reverse_lazy('color_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ColorDetailView(DetailView):
    model = Color
    template_name = 'technologist/color/detail.html'
    context_object_name = 'color'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ColorUpdateView(UpdateView):
    model = Color
    form_class = ColorForm
    template_name = 'technologist/color/edit.html'
    success_url = reverse_lazy('color_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ColorDeleteView(DeleteView):
    model = Color
    template_name = 'technologist/color/delete.html'
    success_url = reverse_lazy('color_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context



@method_decorator([login_required, technologist_required], name='dispatch')
class FabricsListView(ListView):
    model = Fabrics
    template_name = 'technologist/fabrics/list.html'
    context_object_name = 'fabrics'
    paginate_by = 10

    def get_queryset(self):
        return Fabrics.objects.filter(is_archived=False).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ArchivedFabricsListView(ListView):
    model = Fabrics
    template_name = 'technologist/fabrics/list.html'
    context_object_name = 'fabrics'
    paginate_by = 10

    def get_queryset(self):
        return Fabrics.objects.filter(is_archived=True).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    
@method_decorator([login_required, technologist_required], name='dispatch')
class FabricsArchiveView(UpdateView):
    model = Fabrics
    template_name = 'technologist/fabrics/delete.html'
    success_url = reverse_lazy('fabrics_list')

    def post(self, request, *args, **kwargs):
        fabric = self.get_object()
        fabric.is_archived = True
        fabric.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, technologist_required], name='dispatch')
class FabricsUnArchiveView(UpdateView):
    model = Fabrics
    template_name = 'technologist/fabrics/delete.html'
    success_url = reverse_lazy('fabrics_list')

    def post(self, request, *args, **kwargs):
        fabric = self.get_object()
        fabric.is_archived = False
        fabric.save()
        return HttpResponseRedirect(self.success_url)
    
@method_decorator([login_required, technologist_required], name='dispatch')
class FabricsCreateView(CreateView):
    model = Fabrics
    form_class = FabricsForm
    template_name = 'technologist/fabrics/create.html'
    success_url = reverse_lazy('fabrics_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class FabricsDetailView(DetailView):
    model = Fabrics
    template_name = 'technologist/fabrics/detail.html'
    context_object_name = 'fabrics'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class FabricsUpdateView(UpdateView):
    model = Fabrics
    form_class = FabricsForm
    template_name = 'technologist/fabrics/edit.html'
    success_url = reverse_lazy('fabrics_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class FabricsDeleteView(DeleteView):
    model = Fabrics
    template_name = 'technologist/fabrics/delete.html'
    success_url = reverse_lazy('fabrics_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    

@login_required
@technologist_required
def bom_create(request, pk):
    model_instance = get_object_or_404(Model, pk=pk)
    if request.method == 'POST':
        # Remove all existing BOM entries for the model.
        model_instance.bill_of_materials.all().delete()
        row = 0
        # Loop over the rows that are sent in the POST data.
        while f'row-{row}_stock' in request.POST:
            stock_id = request.POST.get(f'row-{row}_stock')
            quantity = request.POST.get(f'row-{row}_quantity')
            if stock_id and quantity:
                stock_instance = get_object_or_404(Stock, pk=stock_id)
                BillOfMaterials.objects.create(
                    model=model_instance,
                    stock=stock_instance,
                    quantity=Decimal(quantity)
                )
            row += 1
        return redirect('model_detail', pk=pk)
    else:
        stocks = Stock.objects.filter(is_archived=False).order_by('name')
        # Load any existing BOM entries.
        boms = model_instance.bill_of_materials.all()
        context = {
            'model': model_instance,
            'stocks': stocks,
            'boms': boms,
            'sidebar_type': 'technology'
        }
        return render(request, 'technologist/models/bom_create.html', context)

@require_POST
@login_required
def add_stock_api(request):
    form = StockForm(request.POST)
    if form.is_valid():
        stock = form.save()
        data = {
            'success': True,
            'stock_id': stock.id,
            'stock_name': stock.name,
        }
        return JsonResponse(data)
    else:
        # Return form errors as JSON (status code 400)
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)
