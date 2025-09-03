from .models import Client  # <- fix import to your project

def client_scope(request):
    current_id = request.session.get("client_scope_id", "all")
    return {
        "clients": Client.objects.all().order_by("name"),
        "current_client_id": str(current_id),
        "client_scope_key": "client_scope_id",  # used by the form
    }
