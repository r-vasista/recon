from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView

from django.http import Http404
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

import requests

from .models import (
    PortalUserMapping, UserCategoryGroupAssignment
)
from .serializers import (
    PortalCheckResultSerializer, UserRegistrationSerializer, PortalUserMappingListSerializer, CustomTokenObtainPairSerializer,
    UserAssignmentCreateSerializer, UserAssignmentListSerializer
)
from .utils import (
    map_user_to_portals
)
from app.models import (
    Portal
)
from app.utils import success_response, error_response
from app.pagination import PaginationMixin


User = get_user_model()


class UserRegistrationAPIView(APIView):
    """
    POST /api/register/
    {
        "username": "vasista",
        "email": "vasista@example.com",
        "password": "strongpassword123"
    }
    """

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(error_response(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        # Create user
        user = serializer.save()

        # Map across portals
        mappings = map_user_to_portals(user.id, user.username)

        response_data = {
            "user": serializer.data,
            "portal_mappings": mappings
        }

        return Response(
            success_response(response_data, "User registered and portal mappings created"),
            status=status.HTTP_201_CREATED
        )


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            return Response(
                success_response(serializer.validated_data, "Login successful"),
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_401_UNAUTHORIZED
            )
            
            
class CheckUsernameAcrossPortalsAPIView(APIView, PaginationMixin):
    """
    GET /api/user-portal/check-username/?username=<username>
    """

    def get(self, request):
        username = request.query_params.get("username")
        if not username:
            return Response(
                error_response("Username is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        not_found_portals = []

        for portal in Portal.objects.all():
            try:
                url = f"{portal.base_url}/api/check-username/"
                r = requests.get(url, params={"username": username}, timeout=5)

                if r.status_code == 200 and r.json().get("status"):
                    user_data = r.json().get("data", {})
                    results.append({
                        "portal": portal.name,
                        "found": True,
                        "user_id": user_data.get("id"),
                        "username": user_data.get("username"),
                    })
                else:
                    results.append({
                        "portal": portal.name,
                        "found": False,
                        "message": r.json().get("message", "User not found"),
                    })
                    not_found_portals.append(portal.name)

            except Exception as e:
                results.append({
                    "portal": portal.name,
                    "found": False,
                    "message": str(e),
                })
                not_found_portals.append(portal.name)

        # Decide final message
        if not not_found_portals:
            final_message = "User found in all portals"
        else:
            final_message = f"User not found in these portals: {', '.join(not_found_portals)}"

        # Serialize and paginate
        serializer = PortalCheckResultSerializer(results, many=True)
        page = self.paginate_queryset(serializer.data, request)
        if page is not None:
            return self.get_paginated_response(page, final_message)

        # If pagination not applied, return full results
        return Response(
            success_response(serializer.data, final_message),
            status=status.HTTP_200_OK,
        )


class PortalUserMappingCreateAPIView(APIView):
    """
    POST /api/user-portal/mappings/
    """

    def post(self, request):
        user_id = request.data.get("user_id")
        username = request.data.get("username")

        if not user_id or not username:
            return Response(
                error_response("user_id and username are required"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = map_user_to_portals(user_id, username)

        return Response(
            success_response(results, "User portal mappings processed"),
            status=status.HTTP_201_CREATED,
        )


class UserPortalMappingsListAPIView(APIView, PaginationMixin):
    """
    GET /api/user-portal/mappings/?username=<username>&page=1&page_size=10
    """

    def get(self, request):
        username = request.query_params.get("username")
        if not username:
            return Response(error_response("Username is required"), status=status.HTTP_400_BAD_REQUEST)

        user = get_object_or_404(User, username=username)

        queryset = PortalUserMapping.objects.filter(user=user).order_by("id")
        page = self.paginate_queryset(queryset, request)
        serializer = PortalUserMappingListSerializer(page, many=True)

        return self.get_paginated_response(serializer.data, message="Portal mappings fetched successfully")


class UserAssignmentCreateAPIView(APIView):
    """
    POST /api/user-assignments/
    Assign multiple groups OR multiple master categories to a user.
    """

    def post(self, request):
        try:
            serializer = UserAssignmentCreateSerializer(data=request.data)
            if serializer.is_valid():
                assignments = serializer.save()
                data = UserAssignmentListSerializer(assignments, many=True).data
                return Response(success_response(
                    data,
                    "Assignments created successfully"
                ), status=status.HTTP_201_CREATED)
            return Response(error_response(serializer.errors), status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserAssignmentListByUserAPIView(APIView, PaginationMixin):
    """
    GET /api/user-assignments/{username}/
    List assignments for a particular user
    """
    def get(self, request, username):
        try:
            user = get_object_or_404(User, username=username)
            queryset = UserCategoryGroupAssignment.objects.filter(user=user).order_by("-created_at")
            page = self.paginate_queryset(queryset, request)
            serializer = UserAssignmentListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data, message=f"Assignments for user {username}")
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserAssignmentListAPIView(APIView, PaginationMixin):
    """
    GET /api/user-assignments/
    List all assignments (admin view, with pagination & filters)
    Filters: ?group=1, ?master_category=2, ?username=john
    """
    def get(self, request):
        try:
            queryset = UserCategoryGroupAssignment.objects.all().order_by("-created_at")

            group = request.query_params.get("group")
            master_category = request.query_params.get("master_category")
            username = request.query_params.get("username")

            if group:
                queryset = queryset.filter(group_id=group)
            if master_category:
                queryset = queryset.filter(master_category_id=master_category)
            if username:
                queryset = queryset.filter(user__username=username)

            page = self.paginate_queryset(queryset, request)
            serializer = UserAssignmentListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data, message="All user assignments fetched successfully")
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)
