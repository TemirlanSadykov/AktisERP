# myapp/auth_backends.py
from django.contrib.auth.backends import ModelBackend
from .models import UserProfile

class CompanyEmployeeIDAuthBackend(ModelBackend):
    def authenticate(self, request, company=None, employee_id=None, password=None, **kwargs):
        try:
            profile = UserProfile.objects.get(company=company, employee_id=employee_id)
            user = profile.user
            if user.check_password(password):
                return user
        except UserProfile.DoesNotExist:
            return None
