from .models import Client, Warehouse, Supplier

def client_scope(request):
    current_id = request.session.get("client_scope_id", "all")
    return {
        "clients": Client.objects.all().order_by("name"),
        "current_client_id": str(current_id),
        "client_scope_key": "client_scope_id",  # used by the form
    }

def warehouse_scope(request):
    current_id = request.session.get("warehouse_scope_id", "all")
    return {
        "warehouses": Warehouse.objects.all().order_by("name"),
        "current_warehouse_id": str(current_id),
        "warehouse_scope_key": "warehouse_scope_id",
    }

def supplier_scope(request):
    current_id = request.session.get("supplier_scope_id", "all")
    return {
        "suppliers": Supplier.objects.all().order_by("name"),
        "current_supplier_id": str(current_id),
        "supplier_scope_key": "supplier_scope_id",
    }