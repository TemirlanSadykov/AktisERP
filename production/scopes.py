from .constants import CLIENT_SCOPE_SESSION_KEY, WAREHOUSE_SCOPE_SESSION_KEY, SUPPLIER_SCOPE_SESSION_KEY
from .models import Stock, SizeQuantity

# ---------- Helpers ----------
def _get_client_scope(request, key=CLIENT_SCOPE_SESSION_KEY):
    """
    Reads the client scope you set via the sidebar form.
    Expected values you post: 'all', 'shared', or a client_id (as str/int).
    """
    val = request.session.get(key, 'all')
    # normalize:
    if val in ('all', 'shared'):
        return val
    try:
        return int(val)
    except (TypeError, ValueError):
        return 'all'

def _filter_by_client(qs, client_scope):
    """
    Filters the Stock queryset by client.
    Because Stock.content_object is heterogeneous (GFK), we keep a compact
    Python-side filter that mirrors your current logic—but scoped and fast.
    """
    if client_scope == 'all':
        return qs
    filtered_ids = []

    for stock in qs:
        content = stock.content_object
        # Direct .client
        if client_scope == 'shared':
            # unassigned / shared (no client on item)
            if hasattr(content, 'client') and getattr(content, 'client_id', None) is None:
                filtered_ids.append(stock.id)
            elif isinstance(content, SizeQuantity):
                # "shared" for FG if orders have no client?
                # If your domain defines shared FG differently, adjust here.
                has_any_client = False
                for order in content.orders.select_related('client_order__client'):
                    if getattr(order.client_order, 'client_id', None) is not None:
                        has_any_client = True
                        break
                if not has_any_client:
                    filtered_ids.append(stock.id)
            elif hasattr(content, 'order'):
                # If there is an order but no client on client_order, consider it shared
                client_id = getattr(getattr(content.order, 'client_order', None), 'client_id', None)
                if client_id is None:
                    filtered_ids.append(stock.id)

        elif isinstance(client_scope, int):
            # specific client id
            if hasattr(content, 'client') and getattr(content, 'client_id', None) == client_scope:
                filtered_ids.append(stock.id)
            elif isinstance(content, SizeQuantity):
                orders = content.orders.select_related('client_order__client')
                if any(o.client_order.client_id == client_scope for o in orders):
                    filtered_ids.append(stock.id)
            elif hasattr(content, 'order'):
                co = getattr(content.order, 'client_order', None)
                if getattr(co, 'client_id', None) == client_scope:
                    filtered_ids.append(stock.id)

    return qs.filter(id__in=filtered_ids)

# ===== WAREHOUSE (new) =====
def _get_warehouse_scope(request, key=WAREHOUSE_SCOPE_SESSION_KEY):
    """
    Reads the warehouse scope from session.
    Expected: 'all' (and optionally 'none') or a warehouse_id (str/int).
    """
    val = request.session.get(key, 'all')
    if val in ('all', 'none'):
        return val
    try:
        return int(val)
    except (TypeError, ValueError):
        return 'all'


def _filter_by_warehouse(qs, warehouse_scope):
    """
    Filters Stock by warehouse. Checks multiple shapes:
    - Stock.warehouse_id
    - content_object.warehouse_id / .warehouse.id
    - content_object.warehouses (M2M)
    'none' keeps items with no detectable warehouse.
    """
    if warehouse_scope == 'all':
        return qs

    filtered_ids = []

    for stock in qs:
        content = stock.content_object
        cand_ids = set()

        # Direct on Stock
        wid = getattr(stock, 'warehouse_id', None)
        if isinstance(wid, int):
            cand_ids.add(wid)
        else:
            wobj = getattr(stock, 'warehouse', None)
            if getattr(wobj, 'id', None) is not None:
                cand_ids.add(wobj.id)

        # FK on content_object
        cw_id = getattr(content, 'warehouse_id', None)
        if isinstance(cw_id, int):
            cand_ids.add(cw_id)
        else:
            cw_obj = getattr(content, 'warehouse', None)
            if getattr(cw_obj, 'id', None) is not None:
                cand_ids.add(cw_obj.id)

        # M2M on content_object
        if hasattr(content, 'warehouses'):
            try:
                for w in content.warehouses.all():
                    if getattr(w, 'id', None) is not None:
                        cand_ids.add(w.id)
            except Exception:
                pass

        if warehouse_scope == 'none':
            if not cand_ids:
                filtered_ids.append(stock.id)
        elif isinstance(warehouse_scope, int):
            if warehouse_scope in cand_ids:
                filtered_ids.append(stock.id)

    return qs.filter(id__in=filtered_ids)


# ===== SUPPLIER (new) =====
def _get_supplier_scope(request, key=SUPPLIER_SCOPE_SESSION_KEY):
    """
    Reads the supplier scope from session.
    Expected: 'all' (and optionally 'none') or a supplier_id (str/int).
    """
    val = request.session.get(key, 'all')
    if val in ('all', 'none'):
        return val
    try:
        return int(val)
    except (TypeError, ValueError):
        return 'all'


def _filter_by_supplier(qs, supplier_scope):
    """
    Filters Stock by supplier. Checks multiple shapes:
    - Stock.supplier_id
    - content_object.supplier_id / .supplier.id
    - content_object.suppliers (M2M)
    'none' keeps items with no detectable supplier.
    """
    if supplier_scope == 'all':
        return qs

    filtered_ids = []

    for stock in qs:
        content = stock.content_object
        cand_ids = set()

        # Direct on Stock
        sid = getattr(stock, 'supplier_id', None)
        if isinstance(sid, int):
            cand_ids.add(sid)
        else:
            sobj = getattr(stock, 'supplier', None)
            if getattr(sobj, 'id', None) is not None:
                cand_ids.add(sobj.id)

        # FK on content_object
        cs_id = getattr(content, 'supplier_id', None)
        if isinstance(cs_id, int):
            cand_ids.add(cs_id)
        else:
            cs_obj = getattr(content, 'supplier', None)
            if getattr(cs_obj, 'id', None) is not None:
                cand_ids.add(cs_obj.id)

        # M2M on content_object
        if hasattr(content, 'suppliers'):
            try:
                for s in content.suppliers.all():
                    if getattr(s, 'id', None) is not None:
                        cand_ids.add(s.id)
            except Exception:
                pass

        if supplier_scope == 'none':
            if not cand_ids:
                filtered_ids.append(stock.id)
        elif isinstance(supplier_scope, int):
            if supplier_scope in cand_ids:
                filtered_ids.append(stock.id)

    return qs.filter(id__in=filtered_ids)

def _get_category_filter(request):
    """
    Read ?category= from querystring.
    Returns 'all' or an int category_id.
    """
    val = request.GET.get('category', 'all')
    try:
        return int(val)
    except (TypeError, ValueError):
        return 'all'


def _filter_by_category(qs, category_filter):
    """
    Filters Stock queryset by Category when the content_object has `category_id`.
    Works for heterogeneous GFK content by doing a compact Python-side filter.
    """
    if category_filter == 'all':
        return qs

    filtered_ids = []
    for stock in qs:
        obj = stock.content_object
        cid = getattr(obj, 'category_id', None)
        if cid == category_filter:
            filtered_ids.append(stock.id)

    return qs.filter(id__in=filtered_ids)