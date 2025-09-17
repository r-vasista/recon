from django.contrib import admin
from .models import (
    Portal, PortalCategory, MasterCategory, MasterCategoryMapping, Group
)

@admin.register(Portal)
class PortalAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'base_url']
    search_fields = ['id', 'name', 'base_url']
    list_filter = ['id', 'name', 'base_url']
    

@admin.register(PortalCategory)
class PortalCategoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'portal', 'name', 'external_id']
    search_fields =['id', 'name', 'portal', 'external_id']
    list_filter = ['id', 'name', 'portal', 'external_id']


@admin.register(MasterCategory)
class MasterCategoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'description']
    search_fields = ['id', 'name', 'description']
    list_filter = ['id', 'name', 'description']


@admin.register(MasterCategoryMapping)
class MasterCategoryMappingAdmin(admin.ModelAdmin):
    list_display = ['id', 'master_category', 'portal_category']
    search_fields = ['id', 'master_category', 'portal_category']
    list_filter = ['id', 'master_category', 'portal_category']


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']
    search_fields = ['id', 'name']
    list_filter = ['id', 'name']
