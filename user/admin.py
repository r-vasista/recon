from django.contrib import admin
from .models import (
    PortalUserMapping, UserCategoryGroupAssignment, UserRole, Role
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


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    ist_display = ['id', 'user', 'role']
    search_fields = ['id', 'user', 'role']
    list_filter = ['id', 'user', 'role']
    

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']
    search_fields = ['id', 'name']
    list_filter = ['id', 'name']
