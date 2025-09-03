from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..models import UserProfile
from django.contrib.auth.views import LoginView
from ..forms import CustomLoginForm

class CustomLoginView(LoginView):
    authentication_form = CustomLoginForm
    template_name = 'login.html'
    
    def get_success_url(self):
        # If the user is a superuser, redirect to the admin index page.
        if self.request.user.is_superuser:
            return reverse('admin:index')
        # Otherwise, fall back to your default behavior.
        return super().get_success_url()

@login_required
def user_redirect(request):
    user_profile = request.user.userprofile
    if user_profile.type == UserProfile.ADMIN:
        return redirect('admin_page')
    elif user_profile.type == UserProfile.TECHNOLOGIST:
        return redirect('client_order_list')
    elif user_profile.type == UserProfile.EMPLOYEE:
        return redirect('employee_page')
    elif user_profile.type == UserProfile.CUTTER:
        return redirect('client_order_list_cutter')
    elif user_profile.type == UserProfile.QC:
        return redirect('client_order_list_qc')
    elif user_profile.type == UserProfile.PACKER:
        return redirect('client_order_list_packer')
    elif user_profile.type == UserProfile.KEEPER:
        return redirect('client_order_list_keeper')
    elif user_profile.type == UserProfile.ACCOUNTANT:
        return redirect('client_order_list_packer')
    elif user_profile.type == UserProfile.SUB_TECH:
        return redirect('client_order_list_sub')
    else:
        return redirect('index')
    
def set_client_scope(request):
    if request.method == "POST":
        request.session["client_scope_id"] = request.POST.get("client_id", "all")
    return redirect(request.META.get("HTTP_REFERER") or reverse("admin_page"))