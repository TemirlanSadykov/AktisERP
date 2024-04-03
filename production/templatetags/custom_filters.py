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