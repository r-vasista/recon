from django.contrib import admin
from .models import (
    Portal, PortalCategory, MasterCategory, MasterCategoryMapping, Group, MasterNewsPost, NewsDistribution, PortalPrompt
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
    list_display = ['id', 'master_category', 'portal_category', 'use_default_content']
    search_fields = ['id', 'master_category', 'portal_category', 'use_default_content']
    list_filter = ['id', 'master_category', 'portal_category', 'use_default_content']


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']
    search_fields = ['id', 'name']
    list_filter = ['id', 'name']
    

@admin.register(MasterNewsPost)
class MasterNewsPostAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'created_by']
    search_fields = ['id', 'title', 'created_by']
    list_filter = ['id', 'title', 'created_by']


@admin.register(NewsDistribution)
class NewsDistributionAdmin(admin.ModelAdmin):
    list_display = ['id', 'news_post', 'portal', 'portal_category', 'status']
    search_fields = ['id', 'news_post', 'portal', 'portal_category']
    list_filter = ['id', 'news_post', 'portal', 'portal_category']


@admin.register(PortalPrompt)
class PortalPromptAdmin(admin.ModelAdmin):
    list_display = ['id', 'portal', 'prompt_text']
    search_fields = ['id', 'portal', 'prompt_text']
    list_filter = ['id', 'portal', 'prompt_text']
