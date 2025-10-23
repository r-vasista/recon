from django.urls import path
from .views import (
    PortalListCreateView, PortalDetailView, PortalCategoryCreateView, PortalCategoryUpdateDeleteView,
    PortalCategoryListView, MasterCategoryView, MasterCategoryMappingView, MasterCategoryMappingsListView,
    GroupCreateListAPIView, GroupRetrieveUpdateDeleteAPIView, GroupCategoriesListAPIView, MasterNewsPostPublishAPIView,
    NewsPostCreateAPIView, PortalCreateAPIView, UserPostsListAPIView, AllNewsPostsAPIView, NewsDistributionListAPIView,
    NewsDistributionDetailAPIView, AdminStatsAPIView, DomainDistributionStatsAPIView, AllPortalsTagsLiveAPIView, 
    NewsPostUpdateAPIView, MyPostsListAPIView
)

urlpatterns = [
    # Portals
    path('portals/list/', PortalListCreateView.as_view()),
    path('portal/detail/<int:id>/', PortalDetailView.as_view()),
    path('create/portal/', PortalCreateAPIView.as_view()),
    path('all/tags/', AllPortalsTagsLiveAPIView.as_view()),
    
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
    
    # News and Distribution
    path('news/create/', NewsPostCreateAPIView.as_view()),
    path('news/update/<int:pk>/', NewsPostUpdateAPIView.as_view()),
    path('publish/news/<int:pk>/', MasterNewsPostPublishAPIView.as_view()),
    path('user/news/posts/', UserPostsListAPIView.as_view()),
    path('my/news/posts/', MyPostsListAPIView.as_view()),
    path('all/posts/', AllNewsPostsAPIView.as_view()),
    path('news/distributed/list/', NewsDistributionListAPIView.as_view()),
    path('news/distributed/detail/<int:pk>/', NewsDistributionDetailAPIView.as_view()),
    
    # Stats 
    path('admin/stats/', AdminStatsAPIView.as_view()),
    path('domain/distribution/', DomainDistributionStatsAPIView.as_view()),
]
