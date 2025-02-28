from django.contrib import admin
from .models import UserProfile
from .models import Company

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'user_first_name', 'company_name')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.model._base_manager.all()
        qs = qs.filter(type=UserProfile.ADMIN)
        return qs

    def user_first_name(self, obj):
        return obj.user.first_name
    user_first_name.short_description = 'User First Name'

    def company_name(self, obj):
        return obj.company.name if obj.company else ''
    company_name.short_description = 'Company'

admin.site.register(Company)

# Register your models here.
