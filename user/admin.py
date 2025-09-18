from django.contrib import admin
from .models import (
    PortalUserMapping, UserCategoryGroupAssignment
)

@admin.register(PortalUserMapping)
class PortalUserMappingAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'portal', 'portal_user_id', 'status']
    search_fields =['id', 'user', 'portal', 'portal_user_id', 'status']
    list_filter = ['id', 'user', 'portal', 'portal_user_id', 'status']


@admin.register(UserCategoryGroupAssignment)
class UserCategoryGroupAssignmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'group', 'master_category']
    search_fields =['id', 'user', 'group', 'master_category']
    list_filter = ['id', 'user', 'group', 'master_category']
