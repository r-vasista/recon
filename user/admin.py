from django.contrib import admin
from .models import (
    PortalUserMapping
)

@admin.register(PortalUserMapping)
class PortalUserMappingAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'portal', 'portal_user_id', 'status']
    search_fields =['id', 'user', 'portal', 'portal_user_id', 'status']
    list_filter = ['id', 'user', 'portal', 'portal_user_id', 'status']