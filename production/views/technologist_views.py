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
from django.db.models.functions import Cast

from ..decorators import technologist_required
from ..forms import *
from ..mixins import *
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
            branch=self.request.user.userprofile.branch,
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
class EmployeeCreateView(AssignBranchForEmployeeMixin, CreateView):
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
    user_profile = get_object_or_404(UserProfile, pk=pk, branch=request.user.userprofile.branch)
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
class EmployeeDeleteView(RestrictBranchMixin, DeleteView):
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
            branch=self.request.user.userprofile.branch,
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
            with transaction.atomic():
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    branch_id, first_name, last_name, username, employee_id, type, station, password = row
                    branch = Branch.objects.get(id=branch_id)
                    try:
                        # Attempt to find an existing UserProfile with given employee_id and branch
                        profile = UserProfile.objects.get(employee_id=employee_id, branch=branch)
                        
                    except UserProfile.DoesNotExist:
                        # If it does not exist, create User and UserProfile
                        user = User.objects.create(username=username, first_name=first_name, last_name=last_name)
                        user.set_password(password)
                        user.save()
                        profile = UserProfile.objects.create(
                            user=user, 
                            branch=branch, 
                            employee_id=employee_id, 
                            type=type, 
                            station=station, 
                            status=False
                        )
                    else:
                        # If UserProfile exists, update both User and UserProfile
                        user = profile.user
                        user.first_name = first_name
                        user.last_name = last_name
                        user.username = username
                        user.set_password(password)
                        user.save()
                        
                        profile.type = type
                        profile.station = station
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
class ClientOrderListView(RestrictBranchMixin, ListView):
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
        self.object.branch = self.request.user.userprofile.branch
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
class ClientOrderUpdateView(RestrictBranchMixin, UpdateView):
    model = ClientOrder
    form_class = ClientOrderForm
    template_name = 'technologist/client/orders/edit.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

    def get_success_url(self):
        return reverse('client_order_detail', kwargs={'pk': self.object.pk, 'sidebar_type': 'technology'})
    
@method_decorator([login_required, technologist_required], name='dispatch')
class ClientOrderDeleteView(RestrictBranchMixin, DeleteView):
    model = ClientOrder
    template_name = 'technologist/client/orders/delete.html'
    success_url = reverse_lazy('client_order_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ClientOrderArchiveView(RestrictBranchMixin, UpdateView):
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
class ClientOrderUnArchiveView(RestrictBranchMixin, UpdateView):
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
class ArchivedClientOrderListView(RestrictBranchMixin, ListView):
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
@technologist_required
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
class OrderListView(RestrictOrderBranchMixin, ListView):
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

        # ----- Other context data (pass along your existing context) -----
        associated_cuts = order.cuts.all().order_by('number')
        passports = Passport.objects.filter(cut__in=associated_cuts).order_by('cut__number', 'number')
        size_data = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'passport_size_id': None, 'stage': None, 'extra': None}))
        total_per_size = defaultdict(int)
        for passport in passports:
            passport_number = passport.id
            for passport_size in passport.passport_sizes.all():
                size = passport_size.size_quantity.size
                extra_key = f"{size}-{passport_size.extra}" if passport_size.extra else size
                size_data[extra_key][passport_number]['quantity'] += passport_size.quantity
                size_data[extra_key][passport_number]['passport_size_id'] = passport_size.id
                size_data[extra_key][passport_number]['stage'] = passport_size.stage
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
        # Process the dynamic table data
        self.handle_size_quantities(self.object, self.request.POST)
        return redirect('client_order_detail', pk=self.object.client_order.pk)

    def handle_size_quantities(self, order, post_data):
        """
        Expected post_data keys:
          - header_0, header_1, …      (the size for each column)
          - row-0_color, row-0_fabric    (color and fabric for row 0)
          - cell_0_0, cell_0_1, …        (quantity for row 0, for each size column)
          - row-1_color, row-1_fabric, cell_1_0, cell_1_1, etc.
          
        For each row and column where quantity > 0, a SizeQuantity object is created and
        associated with the order. Additionally, the color and fabric used for each row
        are collected and saved to the order's many-to-many fields.
        """
        used_colors = set()
        used_fabrics = set()
        sizes = []
        # Get the number of columns from the header row inputs
        col = 0
        while f'header_{col}' in post_data:
            sizes.append(post_data[f'header_{col}'])
            col += 1

        row = 0
        while f'row-{row}_color' in post_data:
            color_id = post_data.get(f'row-{row}_color')
            fabric_id = post_data.get(f'row-{row}_fabric')
            # Lookup the color and fabric objects:
            color = Color.objects.filter(pk=color_id).first() if color_id else None
            fabric = Fabrics.objects.filter(pk=fabric_id).first() if fabric_id else None

            # Collect these for saving later on the order
            if color:
                used_colors.add(color)
            if fabric:
                used_fabrics.add(fabric)

            # Process each column for the current row
            for col_index, size in enumerate(sizes):
                quantity = post_data.get(f'cell_{row}_{col_index}', 0)
                if quantity and int(quantity) > 0:
                    # Create and save the SizeQuantity object
                    size_qty = SizeQuantity.objects.create(
                        size=size,
                        quantity=int(quantity),
                        color=color,
                        fabrics=fabric
                    )
                    order.size_quantities.add(size_qty)
            row += 1

        # Save the collected colors and fabrics to the order
        if used_colors:
            order.colors.add(*used_colors)
        if used_fabrics:
            order.fabrics.add(*used_fabrics)

    def get_context_data(self, **kwargs):
        context = super(OrderCreateView, self).get_context_data(**kwargs)
        context['client_order_pk'] = self.kwargs.get('client_order_pk')
        context['sidebar_type'] = 'technology'
        # Pass available colors and fabrics (and sizes) for use in the template.
        context['colors'] = Color.objects.all().order_by('name')
        context['fabrics'] = Fabrics.objects.all().order_by('name')
        return context
    
@require_POST
@login_required
@technologist_required
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
@technologist_required
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
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context
    def get_success_url(self):
        return reverse('order_detail', kwargs={'pk': self.object.pk})

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
class SizeQuantityCreateView(View):
    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = SizeQuantityForm(order=order)  # Pass the order to the form
        size_quantities = order.size_quantities.all()
        return render(request, 'technologist/orders/create_size_quantity.html', {
            'form': form,
            'size_quantities': size_quantities,
            'order': order,
            'sidebar_type': 'technology'
        })

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            form = SizeQuantityForm(request.POST, order=order)  # Pass the order to the form
            if form.is_valid():
                new_size_quantity = form.save(commit=False)
                new_size_quantity.save()
                order.size_quantities.add(new_size_quantity)

                # Retrieve size quantities with color names instead of IDs
                size_quantities = order.size_quantities.select_related('color').values(
                    'id', 'size', 'quantity', 'color__name'  # Use color__name instead of color ID
                )

                return JsonResponse({'success': True, 'sizeQuantities': list(size_quantities)})
            else:
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        return JsonResponse({'success': False, 'error': 'Non-AJAX request not allowed'}, status=400)
    
@login_required
@technologist_required
def edit_size_quantity(request, sq_id):
    size_quantity = get_object_or_404(SizeQuantity, id=sq_id)

    if request.method == 'POST':
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        form = SizeQuantityForm(data, instance=size_quantity)
        if form.is_valid():
            form.save()
            return JsonResponse({'status': 'success'}, status=200)
    
    return JsonResponse({'status': 'error'}, status=400)

@login_required
@technologist_required
def delete_size_quantity(request, sq_id):
    if request.method == 'POST':
        size_quantity = get_object_or_404(SizeQuantity, id=sq_id)
        size_quantity.delete()
        return JsonResponse({'status': 'success'}, status=200)
    return JsonResponse({'status': 'error'}, status=400)

    
@method_decorator([login_required, technologist_required], name='dispatch')
class CutDetailTechnologistView(DetailView):
    model = Cut
    template_name = 'technologist/cuts/detail.html'
    context_object_name = 'cut'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cut_pk = self.kwargs.get('pk')
        cut = get_object_or_404(Cut, pk=cut_pk)

        # Get all passports related to the cut
        passports = cut.passports.all()

        # Get all production pieces related to the cut
        production_pieces = ProductionPiece.objects.filter(passport_size__passport__cut=cut)

        # Get all errors related to the production pieces
        errors = Error.objects.filter(piece__in=production_pieces)

        # Prepare the total quantities for each size in the cut
        total_quantity_per_size = defaultdict(int)
        for size_quantity in cut.size_quantities.all():
            total_quantity_per_size[f'{size_quantity.size} - {size_quantity.color}'] = size_quantity.quantity

        # Total quantity of layers (sum layers for all passports)
        total_layers = sum(passport.layers for passport in passports if passport.layers)

        context.update({
            'passports': passports,
            'total_quantity_per_size': dict(total_quantity_per_size),
            'total_layers': total_layers,
            'errors': errors,  # Add the errors to the context
            'sidebar_type': 'technology'
        })

        return context
    
@login_required
@technologist_required
def error_detail(request, pk):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        error = Error.objects.filter(pk=pk).values(
            'pk', 'piece_id', 'piece__piece_number', 'piece__passport_size__passport_id', 'piece__passport_size__passport__number', 
            'piece__passport_size__passport__cut', 'piece__passport_size__passport__cut__order__model',
            'piece__passport_size__size_quantity__size', 'piece__id', 'piece__passport_size__size_quantity_id',
            'error_type', 'piece__defect_type', 'cost', 'status',
            'reported_date', 'resolved_date'
        ).first()
        if error:
            error['reported_date'] = error['reported_date'].strftime('%Y-%m-%d %H:%M:%S')
            error['resolved_date'] = error['resolved_date'].strftime('%Y-%m-%d %H:%M:%S') if error['resolved_date'] else None
            error['status'] = Error.Status(error['status']).label
            if error['error_type'] == 'DEFECT':
                works = AssignedWork.objects.filter(
                    work__passport_size__size_quantity_id=error['piece__passport_size__size_quantity_id']
                ).select_related('employee')
                employee_ids = [work.employee.employee_id for work in works]
                error['responsible_employees'] = employee_ids
            
            return JsonResponse({'error': error}, status=200)
        else:
            return JsonResponse({'error': 'Error not found'}, status=404)
    else:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    
@login_required
@technologist_required
@require_POST
def error_update_status(request, pk):
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    
    valid_statuses = [choice[0] for choice in Error.Status.choices]
    if new_status not in valid_statuses:
        return JsonResponse({'status': 'error', 'message': 'Invalid status'}, status=400)

    try:
        error = Error.objects.get(pk=pk)
        error.status = new_status
        error.resolved_date = timezone.now() if new_status == Error.Status.RESOLVED else None
        error.save()

        return JsonResponse({'status': 'success', 'message': 'Error status updated successfully'})
    except Error.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Error not found'}, status=404)    

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

                    employee_profile = UserProfile.objects.filter(employee_id=employee_id_input, type=UserProfile.EMPLOYEE, branch=request.user.userprofile.branch).first()
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
                branch=request.user.userprofile.branch).first()

            if not employee_profile:
                continue

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

@login_required
@technologist_required
def get_reassigned_works(request, assigned_work_id):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        reassigned_works = ReassignedWork.objects.filter(original_assigned_work_id=assigned_work_id)
        data = list(reassigned_works.values('id', 'new_employee__employee_id', 'reassigned_quantity', 'reason', 'is_completed', 'is_success'))
        return JsonResponse({'reassigned_works': data})
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
@require_POST
def reassign_work(request):
    data = json.loads(request.body)
    work_id = data.get('work_id')
    new_employee_id = data.get('new_employee_id')
    quantity = data.get('quantity')
    reason = data.get('reason')
    # Validation
    if not all([work_id, new_employee_id, quantity, reason]):
        return JsonResponse({'message': 'Missing required data'}, status=400)

    try:
        with transaction.atomic():
            assigned_work = get_object_or_404(AssignedWork, id=work_id)
            new_employee_profile = get_object_or_404(UserProfile, employee_id=new_employee_id, branch=request.user.userprofile.branch)

            # Attempt to retrieve an existing reassigned work
            reassigned_work, created = ReassignedWork.objects.get_or_create(
                original_assigned_work=assigned_work,
                new_employee=new_employee_profile,
                defaults={'reassigned_quantity': quantity, 'reason': reason}
            )

            if not created:
                # If the reassigned work is being updated, adjust the assigned_work.quantity
                # by adding the old reassigned quantity before setting the new one
                assigned_work.quantity += reassigned_work.reassigned_quantity
                reassigned_work.reassigned_quantity = quantity
                reassigned_work.reason = reason
                reassigned_work.is_success = False
            
            if quantity <= 0 or quantity > assigned_work.quantity:
                return JsonResponse({'message': 'Invalid quantity'}, status=400)

            # Adjust the assigned work quantity by subtracting the new reassigned quantity
            assigned_work.quantity -= quantity
            reassigned_work.save()
            assigned_work.save()

            return JsonResponse({"message": "Work reassigned successfully"}, status=200)
    
    except AssignedWork.DoesNotExist:
        return JsonResponse({'message': 'Assigned work not found'}, status=404)
    except UserProfile.DoesNotExist:
        return JsonResponse({'message': 'Employee profile not found'}, status=404)
    except Exception as e:
        return JsonResponse({'message': 'An error occurred: ' + str(e)}, status=500)
    
@login_required
@require_POST
def complete_reassigned_work(request):
    reassigned_work_id = request.POST.get('reassigned_work_id')
    try:
        reassigned_work = ReassignedWork.objects.get(id=reassigned_work_id)
        if reassigned_work.is_success:
            reassigned_work.is_success = False
            reassigned_work.is_completed = False
        else:
            reassigned_work.is_success = True

        reassigned_work.save()
        return JsonResponse({'message': 'Reassigned work status updated successfully'}, status=200)
    except ReassignedWork.DoesNotExist:
        return JsonResponse({'message': 'Reassigned work not found'}, status=404)
    except Exception as e:
        return JsonResponse({'message': 'An error occurred: ' + str(e)}, status=500)

# @login_required
# @technologist_required
# def download_passport_excel(request, passport_id):
#     # Fetch the Passport and related data
#     passport = get_object_or_404(Passport, pk=passport_id)
#     passport_sizes = PassportSize.objects.filter(passport=passport)
#     passport_rolls = PassportRoll.objects.filter(passport=passport)

#     # Create a workbook and initialize a worksheet
#     wb = Workbook()
#     ws = wb.active

#     # First row headers
#     headers = [
#         'заказч', 'модель', 'ассортимент', '', '№ рулона', 'цвет', 'Ткань', 'дата кроя'
#     ]
#     ws.append(headers)

#     # Set headers style
#     for cell in ws[1]:
#         cell.font = Font(bold=True)
#         cell.alignment = Alignment(horizontal='center')

#     # Insert data in the second row
#     passport_roll = passport_rolls.first() if passport_rolls else None
#     second_row_data = [
#         passport.order.client_order.client.name, passport.order.model.name, passport.order.assortment.name,
#         '', passport_roll.roll.name if passport_roll else '',
#         passport_roll.roll.color if passport_roll else '',
#         passport_roll.roll.fabrics if passport_roll else '',
#         passport.date.strftime("%m/%d/%Y") if passport.date else ''
#     ]
#     ws.append(second_row_data)

#     # Define the operation headers
#     operation_headers = [
#         '№', 'Операции', 'Оборуд.', 'тех-процесс', 'расценки', 'трудоемкость'
#     ]

#     # Add size columns based on size_quantities in the order
#     sizes = [size.size for size in passport.order.size_quantities.all()]
#     operation_headers.extend(sizes)

#     # Append operation headers
#     ws.append(operation_headers)

#     # Set style for operation headers
#     for cell in ws[3]:
#         cell.font = Font(bold=True)
#         cell.alignment = Alignment(horizontal='center')

#     model_operations = ModelOperation.objects.filter(
#         model=passport.order.model
#     ).select_related('operation').order_by('order')
#     operations = [model_op.operation for model_op in model_operations]

#     for index, operation in enumerate(operations, start=1):
#         # Assume 'get_operation_details' is a method to fetch needed details
#         # You will need to implement this based on your application's specific data
#         operation_details = get_operation_details(operation, passport_sizes)
#         row_data = [index] + operation_details
#         ws.append(row_data)


#     # Autosize column widths
#     for column_cells in ws.columns:
#         length = max(len(str(cell.value)) for cell in column_cells)
#         ws.column_dimensions[get_column_letter(column_cells[0].column)].width = length

#     # Apply bold font style to headers and sizes
#     bold_font = Font(bold=True)
#     header_rows = [1, 3]  # Rows which contain the headers you mentioned

#     # Apply bold font to all cells in the header rows
#     for row in header_rows:
#         for cell in ws[row]:
#             cell.font = bold_font

#     # Additionally, bold the size headers individually in case they are not in the above rows
#     size_header_row = 3  # Assuming the size headers are in the third row
#     for size_col in range(7, 7 + len(sizes)):  # Adjust 7 if your size columns start from a different index
#         ws.cell(row=size_header_row, column=size_col).font = bold_font

#     # Define border style
#     thin_border = Border(
#         left=Side(style='thin'),
#         right=Side(style='thin'),
#         top=Side(style='thin'),
#         bottom=Side(style='thin')
#     )

#     # Apply borders to the first two rows, creating a box effect
#     for row in ws.iter_rows(min_row=1, max_row=2, min_col=1, max_col=ws.max_column):
#         for cell in row:
#             cell.border = thin_border

#     # Insert an empty row after the first two rows
#     ws.insert_rows(3)

#     # Now adjust your other rows accordingly since you inserted a new row
#     # You might need to update the `header_rows` and `size_header_row` if you used the previous code snippet
#     header_rows = [1, 4]  # Updated to reflect the new empty row
#     size_header_row = 4   # Updated to reflect the new empty row

#     # Apply bold font to all cells in the updated header rows
#     for row in header_rows:
#         for cell in ws[row]:
#             cell.font = bold_font

#     # Additionally, bold the size headers individually
#     for size_col in range(7, 7 + len(sizes)):  # Adjust 7 if your size columns start from a different index
#         ws.cell(row=size_header_row, column=size_col).font = bold_font

#     ws.column_dimensions['D'].width = 50

#     # Set the HTTP response with a content-type for Excel file
#     response = HttpResponse(
#         content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
#     )
#     response['Content-Disposition'] = f'attachment; filename="Passport_{passport_id}_Details.xlsx"'

#     # Save the workbook to the response
#     wb.save(response)
#     return response

def get_operation_details(operation, passport_sizes):
    details = [
        operation.node.name,
        operation.equipment.name,
        operation.name,
        operation.payment,
        operation.preferred_completion_time
    ]

    # Ensure the sizes are sorted consistently
    sorted_sizes = sorted(passport_sizes, key=lambda x: x.size_quantity.size)
    
    # Fetch and accumulate details for each sorted size
    for passport_size in sorted_sizes:
        assigned_works = AssignedWork.objects.filter(
            work__operation=operation,
            work__passport_size=passport_size
        ).select_related('employee')

        reassigned_works = ReassignedWork.objects.filter(
            original_assigned_work__work__operation=operation,
            original_assigned_work__work__passport_size=passport_size
        ).select_related('new_employee')

        employee_ids = set(aw.employee.employee_id for aw in assigned_works)
        employee_ids.update(rw.new_employee.employee_id for rw in reassigned_works)

        details.append(', '.join(employee_ids))

    return details



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

    for operation in Operation.objects.all().order_by('number'):
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
class AssortmentListView(RestrictBranchMixin, ListView):
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
class ArchivedAssortmentListView(RestrictBranchMixin, ListView):
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
class AssortmentArchiveView(RestrictBranchMixin, UpdateView):
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
class AssortmentCreateView(AssignBranchMixin, CreateView):
    model = Assortment
    form_class = AssortmentForm
    template_name = 'technologist/assortments/create.html'
    def get_success_url(self):
        return reverse('model_list', kwargs={'a_id': self.object.id})
    
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
class AssortmentUpdateView(RestrictBranchMixin, UpdateView):
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
class AssortmentDeleteView(RestrictBranchMixin, DeleteView):
    model = Assortment
    template_name = 'technologist/assortments/delete.html'
    success_url = reverse_lazy('assortment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidebar_type'] = 'technology'
        return context



@method_decorator([login_required, technologist_required], name='dispatch')
class ModelListView(ListView):
    model = Model
    template_name = 'technologist/models/list.html'
    context_object_name = 'models'
    paginate_by = 10
    def get_queryset(self):
        assortment_id = self.kwargs.get('a_id')
        return Model.objects.filter(assortment=assortment_id, is_archived=False).order_by('name')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['assortment'] = get_object_or_404(Assortment, pk=self.kwargs.get('a_id'))
        context['sidebar_type'] = 'technology'
        return context

@method_decorator([login_required, technologist_required], name='dispatch')
class ArchivedModelListView(ListView):
    model = Model
    template_name = 'technologist/models/list.html'
    context_object_name = 'models'
    paginate_by = 10
    def get_queryset(self):
        assortment_id = self.kwargs.get('a_id')
        return Model.objects.filter(assortment=assortment_id, is_archived=True).order_by('name')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['assortment'] = get_object_or_404(Assortment, pk=self.kwargs.get('a_id'))
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
        return HttpResponseRedirect(reverse_lazy('model_list', kwargs={'a_id': model.assortment.pk}))


@method_decorator([login_required, technologist_required], name='dispatch')
class ModelUnArchiveView(UpdateView):
    model = Model
    template_name = 'technologist/models/delete.html'

    def post(self, request, *args, **kwargs):
        model = self.get_object()
        model.is_archived = False
        model.save()
        return HttpResponseRedirect(reverse_lazy('model_list', kwargs={'a_id': model.assortment.pk}))
    

        
        
@login_required
@technologist_required
def model_create(request, a_id, pk=None):
    assortment = get_object_or_404(Assortment, pk=a_id)
    copy_id = request.GET.get('copy')
    original = get_object_or_404(Model, pk=copy_id) if copy_id else None

    if request.method == 'POST':
        form = ModelCustomForm(request.POST, request.FILES, instance=None, a_id=a_id, copy_id=copy_id)
        if form.is_valid():
            model_instance = form.save()  # Save the model instance
            return redirect('model_detail', a_id = model_instance.assortment.id, pk=model_instance.id)  # Redirect to accessories view
    else:
        form = ModelCustomForm(instance=(original if copy_id else None), a_id=a_id, copy_id=copy_id)
        # Order the operations queryset by node number (numerically) and operation name
        form.fields['operations'].queryset = Operation.objects.select_related('node').all().order_by(
            'name'
        )

    operations_order_json = ""
    if copy_id:
        operations_order = list(ModelOperation.objects.filter(model=original).order_by('order').values_list('operation_id', flat=True))
        operations_order_json = json.dumps(operations_order)

    template_name = 'technologist/models/edit.html' if original else 'technologist/models/create.html'
    context = {
        'form': form,
        'assortment': assortment,
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
        context['model_accessories'] = ModelAccessory.objects.filter(model=model)
        context['sidebar_type'] = 'technology'
        return context

@login_required
@technologist_required
def model_edit(request, a_id, pk):
    model_instance = get_object_or_404(Model, pk=pk)
    if request.method == 'POST':
        form = ModelCustomForm(request.POST, request.FILES, instance=model_instance)
        if form.is_valid():
            model_instance = form.save()  # Save the model instance
            return redirect('model_detail', a_id = model_instance.assortment.id, pk=model_instance.id)  # Redirect to accessories view
    else:
        form = ModelCustomForm(instance=model_instance)
        # Order the operations queryset by node number (numerically) and operation name
        form.fields['operations'].queryset = Operation.objects.select_related('node').all().order_by(
            'name'
        )
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
        return reverse('model_list', kwargs={'a_id': self.kwargs.get('a_id')})



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
@technologist_required
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
@technologist_required
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