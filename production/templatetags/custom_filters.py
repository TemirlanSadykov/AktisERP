from django import template

register = template.Library()

@register.filter(name='zip')
def zip_lists(a, b):
    return zip(a, b)

@register.simple_tag
def get_work(work_by_op_and_size, operation_id, size_quantity_id):
    # Return the work or None if the key is not found
    return work_by_op_and_size.get((operation_id, size_quantity_id))

@register.filter
def get_work_edit(work_by_op_and_size, work_key):
    operation_id, size_quantity_id = work_key.split('_')
    return work_by_op_and_size.get((int(operation_id), int(size_quantity_id)))

@register.filter
def percentage_of(value, total):
    try:
        return 100 * float(value) / float(total)
    except (ValueError, ZeroDivisionError):
        return 0
    
@register.filter
def duration(start_time, end_time):
    if start_time and end_time:
        delta = end_time - start_time
        minutes, remainder = divmod(delta.total_seconds(), 60)
        seconds = int(remainder)
        return f"{int(minutes)} min {seconds} sec"
    return ""

@register.filter
def get_item(dictionary, key):
    if dictionary is None:
        return None
    return dictionary.get(key, None)

@register.filter(name='default_if_none')
def default_if_none(value, default):
    """Return the default value if the input value is None."""
    return value if value is not None else default

@register.filter(name='get_attr')
def get_attr(obj, attr):
    """Return the attribute of an object dynamically."""
    return getattr(obj, attr, None)

@register.filter
def subtract(required, produced):
    """Subtract produced amount from the required amount."""
    try:
        return max(0, required - produced)
    except TypeError:
        return required
    
@register.filter(name='available_meters')
def available_meters(roll):
    return roll.meters - roll.used_meters

@register.filter(name='status_color')
def status_color(value):
    colors = {
        'RESOLVED': 'green',
        'REPORTED': 'red',
        'UNRESOLVABLE': 'blue'
    }
    return colors.get(value, 'default_color')

@register.filter(name='get_stage')
def get_stage(key):
    stages = {
        0: 'Раскрой',
        1: 'Шитье',
        2: 'ОТК',
        3: 'Упаковка',
        4: 'Готово'
    }
    return stages.get(key, 'default_stage')

@register.filter(name='size_range')
def size_range(order):
    size_quantities = order.size_quantities.all().order_by('size')
    if size_quantities.exists():
        first_size = size_quantities.first().size
        last_size = size_quantities.last().size
        return f"{first_size} - {last_size}"
    return "No sizes"

@register.filter(name='display_over')
def display_over(value):
    try:
        value = int(value)
        if value < 0:
            return f"Избыток {abs(value)}"
        return value
    except (ValueError, TypeError):
        return value