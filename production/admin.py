from django.contrib import admin
from .models import UserProfile
from .models import Branch
from .models import Company

admin.site.register(UserProfile)
admin.site.register(Branch)
admin.site.register(Company)

# Register your models here.
