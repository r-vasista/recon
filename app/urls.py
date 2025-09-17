from django.urls import path
from .views import (
    PortalListCreateView, PortalDetailView, PortalCategoryCreateView, PortalCategoryUpdateDeleteView,
    PortalCategoryListView, MasterCategoryView, MasterCategoryMappingView, MasterCategoryMappingsListView,
    GroupCreateListAPIView, GroupRetrieveUpdateDeleteAPIView, GroupCategoriesListAPIView
)

urlpatterns = [
    # Portals
    path('portals/list/', PortalListCreateView.as_view()),
    path('portal/detail/<int:id>/', PortalDetailView.as_view()),
    
    # Portal Category
    path('portal/category/', PortalCategoryCreateView.as_view()),
    path('portal/category/<str:portal_name>/<str:external_id>/', PortalCategoryUpdateDeleteView.as_view()),
    path('portals/categories/list/<str:portal_name>/', PortalCategoryListView.as_view()),
    
    # Master Category
    path('master/category/', MasterCategoryView.as_view()),
    path('master/category/<int:pk>/', MasterCategoryView.as_view()),
    path('master/category/mapping/', MasterCategoryMappingView.as_view()),
    path('master/category/mapping/<int:pk>/', MasterCategoryMappingView.as_view()),
    path('master/categories/mapped/<int:master_category_id>/', MasterCategoryMappingsListView.as_view()),
    
    # Groups
    path('group/', GroupCreateListAPIView.as_view()),
    path('group/<int:pk>/', GroupRetrieveUpdateDeleteAPIView.as_view()),
    path('group/categories/', GroupCategoriesListAPIView.as_view()),
]
