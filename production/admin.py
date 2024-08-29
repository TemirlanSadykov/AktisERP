from django.contrib import admin
from .models import UserProfile
from .models import Branch

admin.site.register(UserProfile)
admin.site.register(Branch)

# Register your models here.
