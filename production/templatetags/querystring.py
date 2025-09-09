# app_name/templatetags/querystring.py
from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def qurl(context, **kwargs):
    """
    Build a URL to current path, merging current GET params with kwargs.
    Passing None as a value will remove that key from the querystring.
    """
    request = context['request']
    query = request.GET.copy()

    for k, v in kwargs.items():
        if v is None and k in query:
            query.pop(k, None)
        elif v is not None:
            query[k] = v

    path = request.path
    qs = query.urlencode()
    return f"{path}?{qs}" if qs else path
