from django.urls import path
from .views import (
    CheckUsernameAcrossPortalsAPIView, PortalUserMappingCreateAPIView, UserRegistrationAPIView, UserPortalMappingsListAPIView,
    LoginView
)

urlpatterns = [
    path('login/', LoginView.as_view(), name='token_obtain_pair'),
    path('registration/', UserRegistrationAPIView.as_view()),
    path('check/username/', CheckUsernameAcrossPortalsAPIView.as_view()),
    path('portal/user/mapping/', PortalUserMappingCreateAPIView.as_view()),
    path('user/mapped/portals/', UserPortalMappingsListAPIView.as_view()),
]