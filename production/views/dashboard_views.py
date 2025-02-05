from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from ..decorators import admin_required
from django.http import JsonResponse
from django.db.models import Sum, F
from django.utils.dateformat import DateFormat
from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from django.forms.models import model_to_dict
from django.db.models import F, Value, CharField
from django.db.models.functions import Concat


from ..models import *

@login_required
@admin_required
def client_api(request, client_id):
    try:
        client = Client.objects.get(pk=client_id)

        # Gather all client_orders by this client
        client_orders = ClientOrder.objects.filter(client=client).order_by('created_at')

        # Calculate total spendings across all orders
        total_spendings = sum(order.payment * order.quantity for order in Order.objects.filter(client_order__in=client_orders))

        # Aggregate spendings per order and group by the date of the client order
        spendings_by_date = []
        for co in client_orders:
            orders = Order.objects.filter(client_order=co)
            total_spent = orders.aggregate(
                total_spent=Sum(F('payment') * F('quantity'))
            )['total_spent'] or 0

            # Format date and sum spendings
            date = DateFormat(co.created_at).format('Y-m-d')
            spendings_by_date.append({
                'date': date,
                'co': co.order_number,
                'spendings': total_spent
            })

        response_data = {
            'id': client.id,
            'name': client.name,
            'contact_info': client.contact_info,
            'total_spendings': total_spendings,
            'spendings_over_time': spendings_by_date
        }

        return JsonResponse(response_data)

    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)
    
@login_required
@admin_required
def employee_api(request, employee_id):
    employee = UserProfile.objects.get(pk=employee_id)
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # Fetch assigned works within the date range
    assigned_works = AssignedWork.objects.filter(
        employee=employee, 
        work__passport_size__passport__cut__date__range=[start_date, end_date]
    )

    # Extract unique orders
    orders = assigned_works.values_list(
        "work__passport_size__passport__cut__order__id",
        "work__passport_size__passport__cut__order__model__name"  # Include model name
    ).distinct()

    # Convert orders to dictionary format with both ID and model name
    orders_dict = {order_id: model_name for order_id, model_name in orders}

    # Group operations and calculate average time spent in seconds
    operation_summary = {}
    total_units = 0
    total_weighted_efficiency = 0

    # Operation-to-order distribution mapping
    operation_distribution = {}

    for work in assigned_works:
        operation_name = work.work.operation.name
        order_id = work.work.passport_size.passport.cut.order.id
        preferred_completion_time = work.work.operation.preferred_completion_time
        total_time = (work.end_time - work.start_time).total_seconds() if work.end_time and work.start_time else 0

        # Track total operation stats
        if operation_name not in operation_summary:
            operation_summary[operation_name] = {
                'operation': operation_name,
                'quantity': work.quantity,
                'total_time': total_time,
                'preferred_completion_time': preferred_completion_time,
            }
        else:
            operation_summary[operation_name]['quantity'] += work.quantity
            operation_summary[operation_name]['total_time'] += total_time

        # Track operation distribution across orders
        key = (operation_name, order_id)
        if key not in operation_distribution:
            operation_distribution[key] = work.quantity
        else:
            operation_distribution[key] += work.quantity

    operations_details = []
    total_time = 0

    for operation in operation_summary.values():
        total_time_spent = operation['preferred_completion_time'] * operation['quantity']
        average_time_per_unit = operation['total_time'] / operation['quantity'] if operation['quantity'] else 0
        efficiency = 100 if average_time_per_unit <= operation['preferred_completion_time'] else (operation['preferred_completion_time'] / average_time_per_unit) * 100
        total_units += operation['quantity']
        total_weighted_efficiency += efficiency * operation['quantity']
        total_time += total_time_spent
        operations_details.append({
            'operation': operation['operation'],
            'quantity': operation['quantity'],
            'total_time_spent': total_time_spent,
            'average_time_per_unit': average_time_per_unit,
            'preferred_completion_time': operation['preferred_completion_time']
        })

    overall_efficiency = total_weighted_efficiency / total_units if total_units else 100

    # Summarize units produced by day
    units_by_day = {}
    for work in assigned_works:
        date = work.start_time.date() if work.start_time else None
        if date:
            if date not in units_by_day:
                units_by_day[date] = work.quantity
            else:
                units_by_day[date] += work.quantity

    units_over_time = [{'date': date, 'units': units} for date, units in sorted(units_by_day.items())]

    # Calculate total defects
    total_defects = ErrorResponsibility.objects.filter(employee=employee).count()

    # Convert operation distribution to list format
    operation_distribution_list = [
        {'operation': op, 'order': order, 'quantity': quantity}
        for (op, order), quantity in operation_distribution.items()
    ]

    response_data = {
        'id': employee.id,
        'full_name': f"{employee.user.first_name} {employee.user.last_name}",
        'username': employee.user.username,
        'efficiency': overall_efficiency,
        'operations': operations_details,
        'orders': [{'id': order_id, 'model_name': model_name} for order_id, model_name in orders_dict.items()],
        'operation_distribution': operation_distribution_list,
        'total_time': total_time,
        'total_defects': total_defects,
        'units_over_time': units_over_time,
    }

    return JsonResponse(response_data)
    
@login_required
@admin_required
def order_api(request, order_id):
    try:
        order = Order.objects.get(pk=order_id)
        # Calculate the production cost per piece
        production_cost_per_piece = order.model.operations.aggregate(
            total_cost=Sum('payment')
        )['total_cost'] or 0

        passports_data = [
            {
                'passport_id': passport.id,
                'passport_number': passport.number,
                'cut_number': passport.cut.number,
                'size_range': f"{passport.size_quantities.first().size} - {passport.size_quantities.last().size}",
                'rolls': [
                    {
                        'roll_name': passport.roll.name,
                        'meters': passport.meters
                    }
                ]
            } for cut in order.cuts.all() for passport in cut.passports.all()
        ]

        # Convert the ManyToMany 'colors' field to a list of color names
        colors = list(order.colors.values_list('name', flat=True))
        fabrics = list(order.fabrics.values_list('name', flat=True))

        response_data = {
            'model_name': order.model.name,
            'quantity': order.quantity,
            'price_per_piece': float(order.payment),
            'production_cost_per_piece': float(production_cost_per_piece),
            'status': order.get_status_display(),
            'assortment': order.model.assortment.name if order.model.assortment else 'N/A',
            'color': colors,  # Colors is now a list of names
            'fabrics': fabrics,
            'passports': passports_data
        }

        return JsonResponse(response_data)

    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)
    
@login_required
@admin_required
def roll_api(request, roll_id):
    try:
        roll = Roll.objects.get(pk=roll_id)
        passport_data = [
            {
                'passport_id': passport.id,
                'passport_number': passport.number,
                'cut_number': passport.cut.number,
                'meters_used': float(passport.meters),
                'passport_details': {
                    'date': passport.cut.date,
                    'is_completed': passport.is_completed,
                    'order': passport.cut.order.model.name if passport.cut.order else None
                }
            } for passport in roll.passport_rolls.all()
        ]
        
        data = {
            'name': roll.name,
            'color': roll.color.name,
            'fabrics': roll.fabrics.name,
            'meters': float(roll.meters),
            'used_meters': float(roll.used_meters),
            'available_meters': float(roll.available_meters),
            'passports_used': passport_data
        }
        
        return JsonResponse(data)

    except Roll.DoesNotExist:
        return JsonResponse({'error': 'Roll not found'}, status=404)

@login_required
@admin_required
def client_order_api(request, client_order_id):
    try:
        order = ClientOrder.objects.get(pk=client_order_id)
        orders = order.orders.all().select_related('model')
        orders_list = [{
            'order_id': ord.id,
            'model_name': ord.model.name,
            'assortment': ord.model.assortment.name,
            'completed_percentage': (ord.completed_quantity / ord.quantity) * 100 if ord.quantity else 0
        } for ord in orders]

        response_data = {
            'order_number': order.order_number,
            'client': order.client.name,
            'status': order.get_status_display(),
            'term': order.term,
            'orders': orders_list,
        }

        return JsonResponse(response_data)

    except ClientOrder.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

@login_required
@admin_required
def fetch_model_records(request):
    model_type = request.GET.get('model_type')
    # Fetching data based on model type
    if model_type == 'UserProfile':
        data = list(UserProfile.objects.values('id', 'user__username'))
    elif model_type == 'Client':
        data = list(Client.objects.values('id', 'name'))
    elif model_type == 'Roll':
        data = list(Roll.objects.values('id', 'name'))
    elif model_type == 'Equipment':
        data = list(Equipment.objects.values('id', 'name'))
    elif model_type == 'Node':
        data = list(Node.objects.values('id', 'name'))
    elif model_type == 'Operation':
        data = list(Operation.objects.values('id', 'name'))
    elif model_type == 'Assortment':
        data = list(Assortment.objects.values('id', 'name'))
    elif model_type == 'Model':
        data = list(Model.objects.values('id', 'name'))
    elif model_type == 'ClientOrder':
        data = list(ClientOrder.objects.values('id', 'order_number'))
    elif model_type == 'Order':
        data = list(Order.objects.values('id', 'model__name'))
    elif model_type == 'Error':
        data = Error.objects.annotate(
            custom_error=Concat(
                F('error_type'), Value(': '),
                F('piece__passport_size__passport__order'), Value(' - '),
                F('piece__passport_size__passport__id'), Value(' - '),
                F('piece__passport_size__size_quantity__size'), Value(' - '),
                F('piece__id'),
                output_field=CharField()
            )
        ).values('id', 'custom_error')
        data = list(data)
    elif model_type == 'Passport':
        data = 'input_required'  # Special handling
    elif model_type == 'ProductionPiece':
        data = 'input_required'  # Special handling
    else:
        data = []
    return JsonResponse(data, safe=False)

def serialize_instance(instance):
    """ Serializes a Django model instance including following foreign keys and handling complex types like ManyToMany fields. """
    data = model_to_dict(instance, fields=[field.name for field in instance._meta.fields if not field.is_relation])
    
    # Handle foreign key and one-to-one relations
    for field in instance._meta.fields:
        if field.is_relation and not field.many_to_many:
            related_object = getattr(instance, field.name, None)
            if related_object is not None:
                data[field.name] = str(related_object)
    
    # Handle many-to-many relations
    for field in instance._meta.many_to_many:
        if hasattr(instance, field.name):
            related_objects = getattr(instance, field.name).all()
            data[field.name] = [str(obj) for obj in related_objects]
    
    return data

@login_required
@admin_required
def fetch_record_details(request):
    model_type = request.GET.get('model_type')
    record_id = request.GET.get('record_id')

    # Get model class from the model type
    try:
        model = apps.get_model('production', model_type)
    except LookupError:
        return JsonResponse({'error': 'Invalid model type'}, status=400)

    # Fetch the record from the model
    try:
        record = model.objects.get(id=record_id)
        data = serialize_instance(record)
    except model.DoesNotExist:
        return JsonResponse({'error': 'Record not found'}, status=404)
    except ValueError:
        return JsonResponse({'error': 'Invalid ID format'}, status=400)

    # Return the serialized data
    return JsonResponse(data)