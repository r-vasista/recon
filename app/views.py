import requests
import json
import time
import logging
from collections import defaultdict
from django.utils import timezone
from django.utils.timezone import now
from django.db.models.functions import Coalesce
from datetime import date
from urllib.parse import urljoin
from datetime import timedelta
from types import SimpleNamespace
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Count, Sum, F, Avg, FloatField, Max
from django.db.models.functions import TruncHour, TruncDay
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.contrib.auth import get_user_model
from django.utils.text import slugify



from .models import (
    Portal, PortalCategory, MasterCategory, MasterCategoryMapping, Group, MasterNewsPost, NewsDistribution, PortalPrompt
)
from .serializers import (
    PortalSerializer, PortalSafeSerializer, PortalCategorySerializer, MasterCategorySerializer, 
    MasterCategoryMappingSerializer, GroupSerializer, GroupListSerializer, MasterNewsPostSerializer, MasterNewsPostListSerializer,
    NewsDistributionListSerializer, NewsDistributionSerializer
)
from .utils import (
    success_response, error_response, generate_variation_with_gpt, get_portals_from_assignment
)
from .pagination import PaginationMixin
from user.models import (
    UserCategoryGroupAssignment, PortalUserMapping
)

User = get_user_model()

logger = logging.getLogger("news_publish")

REQUEST_TIMEOUT_SECS = 60

class PortalListCreateView(APIView, PaginationMixin):
    """
    GET /api/portals/
    POST /api/portals/

    List all portals or create a new portal (super admin only).

    Query Params (for GET):
    - ?page=2&page_size=25

    Example GET Response:
    {
        "success": true,
        "pagination": {
            "count": 52,
            "page": 2,
            "page_size": 25,
            "total_pages": 3,
            "has_next": true,
            "has_previous": true
        },
        "data": [
            {
                "id": 1,
                "name": "News Portal A",
                "base_url": "https://portal-a.com"
            },
            ...
        ]
    }
    """

    def get(self, request):
        try:
            portals = Portal.objects.all().order_by("id")
            paginated_queryset = self.paginate_queryset(portals, request)
            serializer = PortalSafeSerializer(paginated_queryset, many=True)
            return self.get_paginated_response(serializer.data)

        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def post(self, request):
        try:
            serializer = PortalSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            with transaction.atomic():
                portal = serializer.save()

            return Response(success_response(PortalSerializer(portal).data), status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response(error_response(e.detail), status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PortalDetailView(APIView):
    """
    GET /api/portals/{id}/
    PUT /api/portals/{id}/
    DELETE /api/portals/{id}/

    Retrieve, update, or delete a portal.

    Example request (PUT):
    {
        "name": "Updated Portal A",
        "base_url": "https://new-portal-a.com",
        "api_key": "updated_api_key",
        "secret_key": "updated_secret_key"
    }

    Example response (GET):
    {
        "success": true,
        "data": {
            "id": 1,
            "name": "Updated Portal A",
            "base_url": "https://new-portal-a.com"
        }
    }
    """

    def get_object(self, pk):
        try:
            return Portal.objects.get(pk=pk)
        except Portal.DoesNotExist:
            raise Http404("Portal not found")

    def get(self, request, id):
        try:
            portal = self.get_object(id)
            serializer = PortalSerializer(portal)
            return Response(success_response(serializer.data), status=status.HTTP_200_OK)
        except Http404 as e:
            return Response(error_response(str(e)), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, id):
        try:
            portal = self.get_object(id)
            serializer = PortalSerializer(portal, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)

            with transaction.atomic():
                portal = serializer.save()

            return Response(success_response(PortalSerializer(portal).data), status=status.HTTP_200_OK)
        except Http404 as e:
            return Response(error_response(str(e)), status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response(error_response(e.detail), status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, id):
        try:
            portal = self.get_object(id)
            portal.delete()
            return Response(success_response("Portal deleted successfully"), status=status.HTTP_200_OK)
        except Http404 as e:
            return Response(error_response(str(e)), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PortalCategoryCreateView(APIView):
    """POST /api/portal/category/"""

    def post(self, request):
        try:
            serializer = PortalCategorySerializer(data=request.data)
            if serializer.is_valid():
                portal_name = serializer.validated_data["portal_name"]
                external_id = serializer.validated_data["external_id"]

                # Check if already exists
                portal = Portal.objects.get(name=portal_name)
                existing = PortalCategory.objects.filter(
                    portal=portal, external_id=external_id
                ).first()

                if existing:
                    return Response(
                        success_response(
                            {"id": existing.id, "name": existing.name},
                            "Category already exists"
                        ),
                        status=status.HTTP_200_OK
                    )

                # Else create new
                serializer.save()
                return Response(
                    success_response(serializer.data, "Category created"),
                    status=status.HTTP_201_CREATED
                )

            return Response(
                error_response(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST
            )

        except Portal.DoesNotExist:
            return Response(
                error_response("Portal not found"),
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PortalCategoryUpdateDeleteView(APIView):
    """
    PUT /api/portal-categories/{portal_name}/{external_id}/
    DELETE /api/portal-categories/{portal_name}/{external_id}/
    """

    def get_object(self, portal_name, external_id):
        try:
            portal = Portal.objects.get(name=portal_name)
            return PortalCategory.objects.get(portal=portal, external_id=external_id)
        except (Portal.DoesNotExist, PortalCategory.DoesNotExist):
            raise Http404
    
    def get(self, request, portal_name, external_id):
        """
        Retrieve a single portal category by portal_name + external_id.
        """
        try:
            category = self.get_object(portal_name, external_id)
            serializer = PortalCategorySerializer(category)
            return Response(success_response("Category retrieved", serializer.data), status=status.HTTP_200_OK)
        except Http404:
            return Response(error_response("Category not found"), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, portal_name, external_id):
        try:
            category = self.get_object(portal_name, external_id)
            serializer = PortalCategorySerializer(category, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(success_response("Category updated", serializer.data), status=status.HTTP_200_OK)
            return Response(error_response(serializer.errors), status=status.HTTP_400_BAD_REQUEST)
        except Http404:
            return Response(error_response("Category not found"), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, portal_name, external_id):
        try:
            category = self.get_object(portal_name, external_id)
            category.delete()
            return Response(success_response("Category deleted"), status=status.HTTP_204_NO_CONTENT)
        except Http404:
            return Response(error_response("Category not found"), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PortalCategoryListView(APIView, PaginationMixin):
    """
    GET /api/portals/categories/list/{portal_name}/?search=<query>&page=<n>&page_size=<m>
    """

    def get(self, request, portal_name):
        try:
            # Get portal
            portal = Portal.objects.get(name=portal_name)

            # Base queryset
            queryset = PortalCategory.objects.filter(portal=portal)

            # Apply search if given
            search = request.GET.get("search")
            if search:
                queryset = queryset.filter(Q(name__icontains=search))

            paginated_queryset = self.paginate_queryset(queryset, request)

            serializer = PortalCategorySerializer(paginated_queryset, many=True)
            return self.get_paginated_response(serializer.data)

        except Portal.DoesNotExist:
            return Response(error_response("Portal not found"), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MasterCategoryView(APIView, PaginationMixin):
    """
    POST /api/master-categories/      → Create master category
    GET /api/master-categories/       → List master categories
    PUT /api/master-categories/{id}/  → Update master category
    DELETE /api/master-categories/{id}/ → Delete master category
    payload: {
    "name":"genral",
    "description":"asdfsda"
    }
    """

    def get_object(self, pk):
        try:
            return MasterCategory.objects.get(id=pk)
        except MasterCategory.DoesNotExist:
            raise Http404

    def post(self, request):
        try:
            serializer = MasterCategorySerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(success_response("Master category created", serializer.data), status=status.HTTP_201_CREATED)
            return Response(error_response(serializer.errors), status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    
    def get(self, request):
        try:
            mapped = request.query_params.get("mapped")
            search = request.query_params.get("search")

            queryset = MasterCategory.objects.all().order_by("name")

            # Filter by mapped/unmapped
            if mapped and mapped.lower() == "true":
                queryset = queryset.filter(mappings__isnull=False).distinct()
            elif mapped and mapped.lower() == "false":
                queryset = queryset.filter(mappings__isnull=True).distinct()

            # Search by name
            if search:
                queryset = queryset.filter(name__icontains=search)

            # Pagination
            paginated_queryset = self.paginate_queryset(queryset, request)
            serializer = MasterCategorySerializer(paginated_queryset, many=True)
            return self.get_paginated_response(serializer.data, message="Master categories fetched successfully.")

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request, pk):
        try:
            master_category = self.get_object(pk)
            serializer = MasterCategorySerializer(master_category, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(success_response(serializer.data, "Master category updated"), status=status.HTTP_200_OK)
            return Response(error_response(serializer.errors), status=status.HTTP_400_BAD_REQUEST)
        except Http404:
            return Response(error_response("Master category not found"), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        try:
            master_category = self.get_object(pk)
            master_category.delete()
            return Response(success_response("Master category deleted"), status=status.HTTP_204_NO_CONTENT)
        except Http404:
            return Response(error_response("Master category not found"), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    
class MasterCategoryMappingView(APIView, PaginationMixin):
    """
    POST /api/master-category-mappings/ → Create mapping(s)
    GET /api/master-category-mappings/?master_category=1&portal=TOI → List mappings
    PATCH /api/master-category-mappings/{id}/ → Update mapping
    DELETE /api/master-category-mappings/{id}/ → Delete mapping
    """

    def post(self, request):
        """
        Example Payload:
        {
            "master_category": 1,
            "portal_categories": [5, 6, 7],
            "use_default_content": true,
            "is_default": true
        }
        """
        try:
            master_category_id = request.data.get("master_category")
            portal_category_ids = request.data.get("portal_categories", [])
            use_default_content = request.data.get("use_default_content", False)
            is_default = request.data.get("is_default", False)

            if not master_category_id or not portal_category_ids:
                return Response(
                    error_response("master_category and portal_categories are required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            created_mappings = []
            skipped_mappings = []

            for portal_cat_id in portal_category_ids:
                try:
                    mapping, created = MasterCategoryMapping.objects.get_or_create(
                        master_category_id=master_category_id,
                        portal_category_id=portal_cat_id,
                        defaults={
                            "use_default_content": use_default_content,
                            "is_default": is_default,
                        },
                    )

                    # If already exists, update fields if needed
                    if not created:
                        changed = False
                        if mapping.use_default_content != use_default_content:
                            mapping.use_default_content = use_default_content
                            changed = True
                        if mapping.is_default != is_default:
                            mapping.is_default = is_default
                            changed = True
                        if changed:
                            mapping.save(update_fields=["use_default_content", "is_default"])
                        skipped_mappings.append(portal_cat_id)
                    else:
                        created_mappings.append(mapping)

                    # If marked as default, unset others for same portal
                    if is_default:
                        MasterCategoryMapping.objects.filter(
                            portal_category__portal=mapping.portal_category.portal
                        ).exclude(id=mapping.id).update(is_default=False)

                except Exception as e:
                    skipped_mappings.append({"id": portal_cat_id, "error": str(e)})

            serializer = MasterCategoryMappingSerializer(created_mappings, many=True)
            response_data = {"created": serializer.data, "skipped": skipped_mappings}
            return Response(
                success_response(response_data, "Mappings processed successfully"),
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def get(self, request):
        try:
            queryset = MasterCategoryMapping.objects.all()

            master_category_id = request.query_params.get("master_category")
            if master_category_id:
                queryset = queryset.filter(master_category_id=master_category_id)

            portal_name = request.query_params.get("portal")
            if portal_name:
                queryset = queryset.filter(portal_category__portal__name__iexact=portal_name)

            queryset = queryset.order_by("master_category__name")

            paginated_queryset = self.paginate_queryset(queryset, request)
            serializer = MasterCategoryMappingSerializer(paginated_queryset, many=True)
            return self.get_paginated_response(serializer.data)
            
        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def patch(self, request, pk):
        """
        Example Payload:
        {
            "use_default_content": true,
            "is_default": true
        }
        """
        try:
            mapping = MasterCategoryMapping.objects.get(pk=pk)
            use_default_content = request.data.get("use_default_content")
            is_default = request.data.get("is_default")

            if use_default_content is not None:
                mapping.use_default_content = bool(use_default_content)

            if is_default is not None:
                mapping.is_default = bool(is_default)
                if mapping.is_default:
                    # Unset others for same portal
                    MasterCategoryMapping.objects.filter(
                        portal_category__portal=mapping.portal_category.portal
                    ).exclude(id=mapping.id).update(is_default=False)

            mapping.save()
            serializer = MasterCategoryMappingSerializer(mapping)
            return Response(
                success_response(serializer.data, "Mapping updated successfully"),
                status=status.HTTP_200_OK,
            )

        except MasterCategoryMapping.DoesNotExist:
            return Response(error_response("Mapping not found"), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        try:
            mapping = MasterCategoryMapping.objects.get(pk=pk)
            mapping.delete()
            return Response(success_response("Mapping deleted"), status=status.HTTP_204_NO_CONTENT)
        except MasterCategoryMapping.DoesNotExist:
            return Response(error_response("Mapping not found"), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MasterCategoryMappingsListView(APIView, PaginationMixin):
    """
    GET /api/master-categories/{master_category_id}/mappings/?page=1&page_size=10

    Lists all portal categories mapped to the given master category with pagination.
    Also includes data about users assigned to that master category,
    either directly or through a group that includes this category.
    """

    def get(self, request, master_category_id):
        try:
            # Validate master category exists
            try:
                master_category = MasterCategory.objects.get(id=master_category_id)
            except MasterCategory.DoesNotExist:
                raise Http404("Master Category not found")

            # --- Get mappings ---
            mappings = MasterCategoryMapping.objects.filter(
                master_category=master_category
            ).select_related("portal_category", "portal_category__portal")

            paginated_queryset = self.paginate_queryset(mappings, request)
            mapping_serializer = MasterCategoryMappingSerializer(paginated_queryset, many=True)

            # --- Get assigned users ---
            # 1️⃣ Direct assignments
            direct_users = UserCategoryGroupAssignment.objects.filter(
                master_category=master_category
            ).select_related("user")

            # 2️⃣ Indirect (via group)
            group_users = UserCategoryGroupAssignment.objects.filter(
                group__master_categories=master_category
            ).select_related("user", "group").distinct()

            # Combine both sets
            combined_users = set(list(direct_users.values_list("user_id", flat=True)) +
                                 list(group_users.values_list("user_id", flat=True)))

            # Fetch user details efficiently
            assigned_users = User.objects.filter(id__in=combined_users).values("id", "username", "email")

            response_data = {
                "master_category": {
                    "id": master_category.id,
                    "name": master_category.name,
                },
                "assigned_users": list(assigned_users),
                "mappings": mapping_serializer.data,
            }

            return self.get_paginated_response(response_data, message="Master category mappings and assigned users fetched successfully.")

        except Http404 as e:
            return Response(error_response(str(e)), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class GroupCreateListAPIView(APIView, PaginationMixin):
    """
    POST /api/groups/ → Create a group
    GET /api/groups/ → List all groups with pagination
    """

    def post(self, request):
        try:
            serializer = GroupSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            group = serializer.save()
            return Response(
                success_response(GroupSerializer(group).data, "Group created successfully"),
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        try:
            queryset = Group.objects.all().order_by("id")
            page = self.paginate_queryset(queryset, request)
            serializer = GroupListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data, message="Groups fetched successfully")
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GroupRetrieveUpdateDeleteAPIView(APIView):
    """
    GET /api/groups/{id}/ → Retrieve single group
    PUT /api/groups/{id}/ → Update group
    DELETE /api/groups/{id}/ → Delete group
    """

    def get_object(self, pk):
        return get_object_or_404(Group, pk=pk)

    def get(self, request, pk):
        try:
            group = self.get_object(pk)
            serializer = GroupListSerializer(group)
            return Response(success_response(serializer.data, "Group details fetched successfully"), status=status.HTTP_200_OK)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        try:
            group = self.get_object(pk)
            serializer = GroupSerializer(group, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(success_response(serializer.data, "Group updated successfully"), status=status.HTTP_200_OK)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            group = self.get_object(pk)
            group.delete()
            return Response(success_response({}, "Group deleted successfully"), status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GroupCategoriesListAPIView(APIView, PaginationMixin):
    """
    GET /api/group/categories/?group_id=<id>
    List all master categories in a group
    """
    def get(self, request):
        try:
            group_id = request.query_params.get("group_id")
            if not group_id:
                return Response(error_response("group_id is required"), status=status.HTTP_400_BAD_REQUEST)

            group = get_object_or_404(Group, pk=group_id)
            queryset = group.master_categories.all().order_by("id")
            page = self.paginate_queryset(queryset, request)
            # Return only name & id for categories
            data = [{"id": cat.id, "name": cat.name} for cat in page]
            return self.get_paginated_response(data, message=f"Master categories for group '{group.name}' fetched successfully")
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MasterNewsPostPublishAPIView(APIView):
    """
    POST /api/master-news/{id}/publish/
    Publishes a MasterNewsPost to portals mapped under the selected master category.
    Creates NewsDistribution entries upfront with status='PENDING'.
    If AI or posting fails, updates them with 'FAILED' and error message.
    {
    "master_category_id": 6,
    "portal_category_ids": [22, 23, 45],
    "exclude_portal_categories": [23]
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            user = request.user

            # 1. Validate MasterNewsPost
            news_post = get_object_or_404(MasterNewsPost, pk=pk)

            master_category_id = request.data.get("master_category_id") or getattr(news_post.master_category, "id", None)
            if not master_category_id:
                return Response(error_response("master_category_id is missing and not saved in post."), status=400)

            # 2. Validate user assignment
            assignment = UserCategoryGroupAssignment.objects.filter(
                user=user, master_category_id=master_category_id
            ).first()
            if not assignment:
                return Response(
                    error_response("You are not assigned to this master category."),
                    status=status.HTTP_403_FORBIDDEN,
                )

            # 3. Get portal mappings (from master category)
            mappings = list(
                MasterCategoryMapping.objects.filter(
                    master_category_id=master_category_id
                ).select_related("portal_category", "portal_category__portal")
            )

            # 3.1 Also include manually selected portal categories if provided
            manual_portal_category_ids = request.data.get("portal_category_ids", [])
            if isinstance(manual_portal_category_ids, str):
                try:
                    manual_portal_category_ids = json.loads(manual_portal_category_ids)
                except Exception:
                    manual_portal_category_ids = []

            if manual_portal_category_ids:
                extra_portal_categories = (
                    PortalCategory.objects.filter(id__in=manual_portal_category_ids)
                    .select_related("portal")
                    .exclude(id__in=[m.portal_category_id for m in mappings])
                )

                # Wrap manual ones in temporary mapping-like objects
                for portal_cat in extra_portal_categories:
                    fake_mapping = SimpleNamespace(
                        portal_category=portal_cat,
                        use_default_content=False,
                    )
                    mappings.append(fake_mapping)

            # 4. Handle excluded portal categories
            excluded_portal_category_ids = request.data.get("exclude_portal_categories") or news_post.excluded_portals or []

            # Convert JSON string to list if needed
            if isinstance(excluded_portal_category_ids, str):
                try:
                    excluded_portal_category_ids = json.loads(excluded_portal_category_ids)
                except Exception:
                    excluded_portal_category_ids = []

            # Ensure it's a clean list of integers
            excluded_portal_category_ids = [
                int(x) for x in excluded_portal_category_ids if str(x).isdigit()
            ]

            results = []

            # 5. Process each portal mapping
            for mapping in mappings:
                portal = mapping.portal_category.portal
                portal_category = mapping.portal_category

                # Skip manually excluded
                if portal_category.id in excluded_portal_category_ids:
                    results.append({
                        "portal": portal.name,
                        "category": portal_category.name,
                        "success": False,
                        "response": "Skipped manually (portal category excluded)",
                    })
                    continue

                # Existing distribution or create pending
                dist, created = NewsDistribution.objects.get_or_create(
                    news_post=news_post,
                    portal=portal,
                    defaults={
                        "portal_category": portal_category,
                        "master_category_id": master_category_id,
                        "status": "PENDING",
                        "response_message": "Queued for publishing",
                        "started_at": timezone.now(),
                    },
                )

                # Skip if already successful
                if dist.status == "SUCCESS":
                    results.append({
                        "portal": portal.name,
                        "category": portal_category.name,
                        "success": True,
                        "response": "Already published successfully, skipped.",
                    })
                    continue

                # Increment retry if failed previously
                if dist.status == "FAILED":
                    dist.retry_count += 1
                    dist.status = "PENDING"
                    dist.response_message = "Retrying..."
                    dist.save(update_fields=["retry_count", "status", "response_message"])

                start_time = time.perf_counter()

                # 6. AI generation
                try:
                    if mapping.use_default_content:
                        rewritten_title = news_post.title
                        rewritten_short = news_post.short_description
                        rewritten_content = news_post.content
                        rewritten_meta = news_post.meta_title or news_post.title
                        rewritten_slug = news_post.slug or slugify(news_post.meta_title or news_post.title)
                    else:
                        portal_prompt = (
                            PortalPrompt.objects.filter(portal=portal, is_active=True).first()
                            or PortalPrompt.objects.filter(portal__isnull=True, is_active=True).first()
                        )
                        prompt_text = (
                            portal_prompt.prompt_text
                            if portal_prompt
                            else "Rewrite the content slightly for clarity and engagement."
                        )

                        result = generate_variation_with_gpt(
                            news_post.title,
                            news_post.short_description,
                            news_post.content,
                            prompt_text,
                            news_post.meta_title,
                            news_post.slug,
                            portal_name=portal.name,
                        )

                        if not result:
                            raise ValueError("AI generation failed — no data returned")

                        rewritten_title, rewritten_short, rewritten_content, rewritten_meta, rewritten_slug = result

                except Exception as e:    
                    dist.status = "FAILED"
                    dist.response_message = f"AI generation failed: {str(e)}"
                    dist.completed_at = timezone.now()
                    dist.save(update_fields=["status", "response_message", "completed_at"])

                    results.append({
                        "portal": portal.name,
                        "category": portal_category.name,
                        "success": False,
                        "response": f"AI generation failed: {str(e)}",
                    })
                    continue  # skip posting for this portal

                # 7. Get portal user mapping
                portal_user = PortalUserMapping.objects.filter(user=user, portal=portal, status="MATCHED").first()
                if not portal_user:
                    dist.status = "FAILED"
                    dist.response_message = "No valid portal user mapping found."
                    dist.completed_at = timezone.now()
                    dist.save(update_fields=["status", "response_message", "completed_at"])

                    results.append({
                        "portal": portal.name,
                        "category": portal_category.name,
                        "success": False,
                        "response": "No valid portal user mapping found.",
                    })
                    continue                

                # 8. Prepare payload
                payload = {
                    "post_cat": portal_category.external_id if portal_category else None,
                    "post_title": rewritten_title,
                    "post_short_des": rewritten_short,
                    "post_des": rewritten_content,
                    "meta_title": rewritten_meta,
                    "slug": rewritten_slug,
                    "post_tag": news_post.post_tag or "",
                    "author": portal_user.portal_user_id,
                    "Event_date": (news_post.Event_date or timezone.now().date()).isoformat(),
                    "Eventend_date": (news_post.Event_end_date or timezone.now().date()).isoformat(),
                    "schedule_date": (news_post.schedule_date or timezone.now()).isoformat(),
                    "is_active": int(bool(news_post.latest_news)) if news_post.latest_news is not None else 0,
                    "Event": int(bool(news_post.upcoming_event)) if news_post.upcoming_event is not None else 0,
                    "Head_Lines": int(bool(news_post.Head_Lines)) if news_post.Head_Lines is not None else 0,
                    "articles": int(bool(news_post.articles)) if news_post.articles is not None else 0,
                    "trending": int(bool(news_post.trending)) if news_post.trending is not None else 0,
                    "BreakingNews": int(bool(news_post.BreakingNews)) if news_post.BreakingNews is not None else 0,
                    "post_status": news_post.counter or 0,
                }
                files = {"post_image": open(news_post.post_image.path, "rb")} if news_post.post_image else {}

                # 9. Call portal API
                try:
                    api_url = f"{portal.base_url}/api/create-news/"
                    response = requests.post(api_url, data=payload, files=files, timeout=90)
                    success = response.status_code in [200, 201]
                    response_msg = response.text
                except Exception as e:
                    success = False
                    response_msg = str(e)

                elapsed_time = round(time.perf_counter() - start_time, 2)

                # 10. Update distribution
                dist.status = "SUCCESS" if success else "FAILED"
                dist.response_message = response_msg
                dist.ai_title = rewritten_title
                dist.ai_short_description = rewritten_short
                dist.ai_content = rewritten_content
                dist.ai_meta_title = rewritten_meta
                dist.ai_slug = rewritten_slug
                dist.time_taken = elapsed_time
                dist.started_at = timezone.now() - timezone.timedelta(seconds=elapsed_time)
                dist.completed_at = timezone.now()
                dist.save()

                results.append({
                    "portal": portal.name,
                    "category": portal_category.name,
                    "success": success,
                    "response": response_msg,
                    "time_taken": elapsed_time,
                })

            return Response(success_response(results, "News published successfully."))

        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)       
   
        
class NewsPostCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            data = request.data.copy()
            data["created_by"] = request.user.id
            data["status"] = data.get("status", "PUBLISHED")

            # Convert excluded_portals to list if provided as string (common case in JSON)
            excluded_portals = data.get("excluded_portals")
            if isinstance(excluded_portals, str):
                try:
                    data["excluded_portals"] = json.loads(excluded_portals)
                except Exception:
                    data["excluded_portals"] = []

            serializer = MasterNewsPostSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                msg = (
                    "News post saved as draft successfully."
                    if data["status"] == "DRAFT"
                    else "News post created successfully."
                )
                return Response(success_response(serializer.data, msg), status=status.HTTP_201_CREATED)
            return Response(error_response(serializer.errors), status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PortalCreateAPIView(APIView):
    """
    POST /api/portals/create/
    Create a new Portal.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            serializer = PortalSerializer(data=request.data)
            if serializer.is_valid():
                portal = serializer.save()
                return Response(
                    success_response(
                        PortalSerializer(portal).data,
                        "Portal created successfully"
                    ),
                    status=status.HTTP_201_CREATED
                )
            return Response(
                error_response(serializer.errors),
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserPostsListAPIView(APIView, PaginationMixin):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            username = request.query_params.get("username")
            if not username:
                return Response(error_response("username query param is required"))

            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return Response(error_response("User not found"))

            queryset = MasterNewsPost.objects.filter(created_by=user).order_by("-created_at")
            paginated_qs = self.paginate_queryset(queryset, request, view=self)
            serializer = MasterNewsPostListSerializer(paginated_qs, many=True)

            return self.get_paginated_response(serializer.data)

        except Exception as e:
            return Response(error_response(str(e)))


class AllNewsPostsAPIView(APIView, PaginationMixin):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            queryset = MasterNewsPost.objects.all().order_by("-created_at")

            # Filters
            created_by = request.query_params.get("created_by")
            if created_by:
                queryset = queryset.filter(created_by_id=created_by)

            is_active = request.query_params.get("is_active")
            if is_active is not None:
                if is_active.lower() in ["true", "1"]:
                    queryset = queryset.filter(is_active=True)
                elif is_active.lower() in ["false", "0"]:
                    queryset = queryset.filter(is_active=False)

            # Search
            search = request.query_params.get("search")
            if search:
                queryset = queryset.filter(
                    Q(title__icontains=search) | Q(short_description__icontains=search)
                )

            paginated_qs = self.paginate_queryset(queryset, request, view=self)
            serializer = MasterNewsPostListSerializer(paginated_qs, many=True)

            return self.get_paginated_response(
                serializer.data, 
                message="News posts fetched successfully"
            )

        except Exception as e:
            return Response(error_response(str(e)), status=500)


class NewsDistributionListAPIView(APIView, PaginationMixin):
    """
    GET /api/news-distributions/

    Fetch paginated list of NewsDistribution records with filters and search.

    Query Params:
    - search: search by title, ai_title, slug, ai_slug, or author username
    - status: filter by distribution status (SUCCESS, FAILED, PENDING)
    - portal: filter by portal id
    - portal_name: filter by portal name (case-insensitive)
    - portal_category: filter by portal_category id
    - portal_category_name: filter by portal_category name (case-insensitive)
    - master_category_name: filter by master category name (case-insensitive)
    - created_by: filter by creator user id
    - date_from, date_to: filter by sent_at range (YYYY-MM-DD)
    - news_post_id: filter all distributions of a specific master news post
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            queryset = NewsDistribution.objects.select_related(
                "news_post", "portal", "master_category", "portal_category", "news_post__created_by"
            ).order_by("-sent_at")

            # ---- Search ----
            search = request.query_params.get("search")
            if search:
                queryset = queryset.filter(
                    Q(news_post__title__icontains=search)
                    | Q(ai_title__icontains=search)
                    | Q(news_post__slug__icontains=search)
                    | Q(ai_slug__icontains=search)
                    | Q(news_post__created_by__username__icontains=search)
                )

            # ---- Filters ----
            created_by = request.query_params.get("created_by")
            portal = request.query_params.get("portal")
            portal_name = request.query_params.get("portal_name")
            portal_category = request.query_params.get("portal_category")
            portal_category_name = request.query_params.get("portal_category_name")
            status_filter = request.query_params.get("status")
            master_category_name = request.query_params.get("master_category_name")
            date_from = request.query_params.get("date_from")
            date_to = request.query_params.get("date_to")
            news_post_id = request.query_params.get("news_post_id")

            if created_by:
                queryset = queryset.filter(news_post__created_by_id=created_by)
            if portal:
                queryset = queryset.filter(portal_id=portal)
            if portal_name:
                queryset = queryset.filter(portal__name__icontains=portal_name)
            if portal_category:
                queryset = queryset.filter(portal_category_id=portal_category)
            if portal_category_name:
                queryset = queryset.filter(portal_category__name__icontains=portal_category_name)
            if status_filter:
                queryset = queryset.filter(status=status_filter.upper())
            if master_category_name:
                queryset = queryset.filter(master_category__name__icontains=master_category_name)
            if news_post_id:
                queryset = queryset.filter(news_post_id=news_post_id)

            # ---- Date Range Filter ----
            if date_from:
                parsed_from = parse_date(date_from)
                if parsed_from:
                    queryset = queryset.filter(sent_at__date__gte=parsed_from)

            if date_to:
                parsed_to = parse_date(date_to)
                if parsed_to:
                    queryset = queryset.filter(sent_at__date__lte=parsed_to)

            # ---- Pagination ----
            paginated_qs = self.paginate_queryset(queryset, request, view=self)
            serializer = NewsDistributionListSerializer(
                paginated_qs, many=True, context={"request": request}
            )

            return self.get_paginated_response(
                serializer.data,
                message="News distribution list fetched successfully"
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class NewsDistributionDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        try:
            try:
                distribution = NewsDistribution.objects.select_related(
                    "news_post", "portal", "master_category", "portal_category"
                ).get(pk=pk)
            except NewsDistribution.DoesNotExist:
                return Response(
                    error_response("News distribution not found"),
                    status=status.HTTP_404_NOT_FOUND
                )

            serializer = NewsDistributionSerializer(distribution, context={"request": request})
            return Response(
                success_response(serializer.data, "News distribution detail fetched successfully"),
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class AdminStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """
        GET /api/admin/stats/?today=true
        GET /api/admin/stats/?start_date=2025-10-01&end_date=2025-10-05

        Returns admin/user-specific KPIs for posts and news distributions.

        - MASTER role: shows all posts and distributions.
        - USER role: shows only user's own posts and distributions.
        """
        try:
            user = request.user
            role = getattr(user.role, "role", None)

            today_param = request.query_params.get("today")
            start_date = request.query_params.get("start_date")
            end_date = request.query_params.get("end_date")

            date_filter = {}
            today = timezone.now().date()

            # --- Date Filtering ---
            if today_param and today_param.lower() == "true":
                date_filter["created_at__date"] = today
            elif start_date and end_date:
                date_filter["created_at__date__range"] = [start_date, end_date]

            # --- MASTER ADMIN STATS ---
            if role and role.name.upper() == "MASTER":
                posts_qs = MasterNewsPost.objects.filter(**date_filter)
                total_posts = posts_qs.count()
                total_draft_posts = posts_qs.filter(status="DRAFT").count()
                total_published_posts = posts_qs.filter(status="PUBLISHED").count()

                today_posts_qs = MasterNewsPost.objects.filter(created_at__date=today)
                today_total_posts = today_posts_qs.count()
                today_draft_posts = today_posts_qs.filter(status="DRAFT").count()

                total_users = (
                    User.objects.filter(**date_filter).count()
                    if date_filter else User.objects.count()
                )
                total_portals = Portal.objects.filter(**date_filter).count()
                total_master_categories = MasterCategory.objects.filter(**date_filter).count()

                distributions = NewsDistribution.objects.filter(**date_filter)

                stats = {
                    "total_posts": total_posts,
                    "draft_posts": total_draft_posts,
                    "published_posts": total_published_posts,
                    "today_total_posts": today_total_posts,
                    "today_draft_posts": today_draft_posts,
                    "total_users": total_users,
                    "total_portals": total_portals,
                    "total_master_categories": total_master_categories,
                }
                stats.update(self._get_distribution_stats(distributions, today))

            # --- USER STATS ---
            elif role and role.name.upper() == "USER":
                posts_qs = MasterNewsPost.objects.filter(created_by=user, **date_filter)
                total_posts = posts_qs.count()
                total_draft_posts = posts_qs.filter(status="DRAFT").count()
                total_published_posts = posts_qs.filter(status="PUBLISHED").count()

                today_posts_qs = MasterNewsPost.objects.filter(
                    created_by=user, created_at__date=today
                )
                today_total_posts = today_posts_qs.count()
                today_total_drafts = today_posts_qs.filter(status="DRAFT").count()

                assignments = UserCategoryGroupAssignment.objects.filter(user=user)
                portals = set()
                master_categories = set()

                for assignment in assignments:
                    if assignment.master_category:
                        master_categories.add(assignment.master_category)
                    if assignment.group:
                        master_categories.update(assignment.group.master_categories.all())
                    for portal, _ in get_portals_from_assignment(assignment):
                        portals.add(portal)

                user_distributions = NewsDistribution.objects.filter(
                    news_post__created_by=user, **date_filter
                )

                stats = {
                    "total_posts": total_posts,
                    "draft_posts": total_draft_posts,
                    "published_posts": total_published_posts,
                    "today_total_posts": today_total_posts,
                    "today_total_drafts": today_total_drafts,
                    "total_portals": len(portals),
                    "total_master_categories": len(master_categories),
                }
                stats.update(self._get_distribution_stats(user_distributions, today))

            else:
                return Response(
                    error_response("Role not recognized or not assigned"),
                    status=status.HTTP_403_FORBIDDEN,
                )

            return Response(
                success_response(stats, "Stats fetched successfully"),
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --- Helper Function ---
    def _get_distribution_stats(self, queryset, today):
        total_distributions = queryset.count()
        successful_distributions = queryset.filter(status="SUCCESS").count()
        failed_distributions = queryset.filter(status="FAILED").count()
        pending_distributions = queryset.filter(status="PENDING").count()
        retry_counts = queryset.aggregate(total=Sum("retry_count"))["total"] or 0

        # --- Today’s stats ---
        today_distributions = queryset.filter(created_at__date=today)
        today_total = today_distributions.count()
        today_successful = today_distributions.filter(status="SUCCESS").count()
        today_failed = today_distributions.filter(status="FAILED").count()

        # --- Average Time Taken ---
        valid_times = queryset.filter(time_taken__gt=0)
        today_valid_times = today_distributions.filter(time_taken__gt=0)
        avg_time = round(valid_times.aggregate(avg=Avg("time_taken"))["avg"] or 0, 2)
        today_avg_time = round(today_valid_times.aggregate(avg=Avg("time_taken"))["avg"] or 0, 2)

        # --- Throughput per Hour (Average) ---
        throughput_per_hour = 0
        if total_distributions > 0:
            earliest = queryset.order_by("created_at").first().created_at
            latest = queryset.order_by("-created_at").first().created_at
            total_hours = (latest - earliest).total_seconds() / 3600
            if total_hours > 0:
                throughput_per_hour = round(total_distributions / total_hours, 2)

        return {
            "news_distribution": {
                "total_distributions": total_distributions,
                "successful_distributions": successful_distributions,
                "failed_distributions": failed_distributions,
                "pending_distributions": pending_distributions,
                "retry_counts": retry_counts,
                "average_time_taken": avg_time,
                "today_average_time_taken": today_avg_time,
                "throughput_per_hour": throughput_per_hour,
                "today": {
                    "total": today_total,
                    "successful": today_successful,
                    "failed": today_failed,
                },
            }
        }

      
        
class DomainDistributionStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            user = request.user
            role = getattr(getattr(user, "role", None), "role", None)
            today = timezone.now().date()
            stats = []

            # ---------------- MASTER ROLE ----------------
            if role and role.name.upper() == "MASTER":
                domains = Portal.objects.all().order_by("name")

                for domain in domains:
                    distributions = NewsDistribution.objects.filter(portal=domain)
                    today_distributions = distributions.filter(created_at__date=today)

                    # Filter out time_taken = 0 for average calculations
                    valid_times = distributions.filter(time_taken__gt=0)
                    today_valid_times = today_distributions.filter(time_taken__gt=0)

                    total_distributions = distributions.count()
                    successful_distributions = distributions.filter(status="SUCCESS").count()
                    today_total_distributions = today_distributions.count()
                    today_successful_distributions = today_distributions.filter(status="SUCCESS").count()

                    # Calculate success percentages
                    success_percentage = (
                        round((successful_distributions / total_distributions) * 100, 2)
                        if total_distributions > 0 else 0.0
                    )
                    today_success_percentage = (
                        round((today_successful_distributions / today_total_distributions) * 100, 2)
                        if today_total_distributions > 0 else 0.0
                    )

                    domain_stats = {
                        "portal_id": domain.id,
                        "portal_name": domain.name,

                        # --- Overall Counts ---
                        "total_distributions": total_distributions,
                        "successful_distributions": successful_distributions,
                        "failed_distributions": distributions.filter(status="FAILED").count(),
                        "pending_distributions": distributions.filter(status="PENDING").count(),
                        "retry_counts": distributions.aggregate(total=Sum("retry_count"))["total"] or 0,

                        # --- Overall Metrics ---
                        "success_percentage": success_percentage,
                        "average_time_taken": round(valid_times.aggregate(avg=Avg("time_taken"))["avg"] or 0, 2),

                        # --- Today's Counts ---
                        "today_total_distributions": today_total_distributions,
                        "today_successful_distributions": today_successful_distributions,
                        "today_failed_distributions": today_distributions.filter(status="FAILED").count(),
                        "today_pending_distributions": today_distributions.filter(status="PENDING").count(),
                        "today_retry_counts": today_distributions.aggregate(total=Sum("retry_count"))["total"] or 0,

                        # --- Today's Metrics ---
                        "today_success_percentage": today_success_percentage,
                        "today_average_time_taken": round(today_valid_times.aggregate(avg=Avg("time_taken"))["avg"] or 0, 2),
                    }

                    stats.append(domain_stats)

            # ---------------- USER ROLE ----------------
            elif role and role.name.upper() == "USER":
                assignments = UserCategoryGroupAssignment.objects.filter(user=user)
                assigned_portals = set()

                for assignment in assignments:
                    for portal, _ in get_portals_from_assignment(assignment):
                        assigned_portals.add(portal)

                for domain in assigned_portals:
                    distributions = NewsDistribution.objects.filter(
                        portal=domain,
                        news_post__created_by=user,
                    )
                    today_distributions = distributions.filter(created_at__date=today)

                    valid_times = distributions.filter(time_taken__gt=0)
                    today_valid_times = today_distributions.filter(time_taken__gt=0)

                    total_distributions = distributions.count()
                    successful_distributions = distributions.filter(status="SUCCESS").count()
                    today_total_distributions = today_distributions.count()
                    today_successful_distributions = today_distributions.filter(status="SUCCESS").count()

                    success_percentage = (
                        round((successful_distributions / total_distributions) * 100, 2)
                        if total_distributions > 0 else 0.0
                    )
                    today_success_percentage = (
                        round((today_successful_distributions / today_total_distributions) * 100, 2)
                        if today_total_distributions > 0 else 0.0
                    )

                    domain_stats = {
                        "portal_id": domain.id,
                        "portal_name": domain.name,

                        # --- Overall Counts ---
                        "total_distributions": total_distributions,
                        "successful_distributions": successful_distributions,
                        "failed_distributions": distributions.filter(status="FAILED").count(),
                        "pending_distributions": distributions.filter(status="PENDING").count(),
                        "retry_counts": distributions.aggregate(total=Sum("retry_count"))["total"] or 0,

                        # --- Overall Metrics ---
                        "success_percentage": success_percentage,
                        "average_time_taken": round(valid_times.aggregate(avg=Avg("time_taken"))["avg"] or 0, 2),

                        # --- Today's Counts ---
                        "today_total_distributions": today_total_distributions,
                        "today_successful_distributions": today_successful_distributions,
                        "today_failed_distributions": today_distributions.filter(status="FAILED").count(),
                        "today_pending_distributions": today_distributions.filter(status="PENDING").count(),
                        "today_retry_counts": today_distributions.aggregate(total=Sum("retry_count"))["total"] or 0,

                        # --- Today's Metrics ---
                        "today_success_percentage": today_success_percentage,
                        "today_average_time_taken": round(today_valid_times.aggregate(avg=Avg("time_taken"))["avg"] or 0, 2),
                    }

                    stats.append(domain_stats)

            else:
                return Response(
                    error_response("Role not recognized or not assigned"),
                    status=status.HTTP_403_FORBIDDEN,
                )

            # --- Sort (Leaderboard) by Total Distributions ---
            stats = sorted(stats, key=lambda x: x["total_distributions"], reverse=True)

            # --- Assign Ranks ---
            for rank, item in enumerate(stats, start=1):
                item["rank"] = rank

            return Response(
                success_response(stats, "Domain leaderboard & distribution stats fetched successfully"),
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AllPortalsTagsLiveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        portals = Portal.objects.all()
        all_tags = {}
        # Use dict with slug as key to automatically deduplicate

        for portal in portals:
            try:
                api_url = f"{portal.base_url}/api/tags/"
                response = requests.get(api_url, timeout=90)
                if response.status_code == 200:
                    res_json = response.json()
                    # adapt to actual response structure
                    tags = res_json.get("data") or []  # <-- extract the list
                    for tag in tags:
                        slug = tag.get("slug") or tag.get("name", "").lower().replace(" ", "-")
                        if slug not in all_tags:
                            all_tags[slug] = {
                                "name": tag.get("name"),
                                "slug": slug,
                                "portals": [portal.name]  # keep track of portals that have this tag
                            }
                        else:
                            all_tags[slug]["portals"].append(portal.name)
            except Exception as e:
                # optional: log portal fetch error, skip failing portal
                continue

        # convert dict values to list
        unique_tags = list(all_tags.values())

        return Response({"status": True, "tags": unique_tags})


class NewsPostUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def put(self, request, pk):
        """
        PUT /api/news-posts/{pk}/
        Update a news post (including draft -> published transition)
        """
        try:
            post = get_object_or_404(MasterNewsPost, pk=pk, created_by=request.user)

            serializer = MasterNewsPostSerializer(post, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(
                    success_response(
                        serializer.data,
                        "News post updated successfully"
                    ),
                    status=status.HTTP_200_OK
                )
            return Response(error_response(serializer.errors), status=status.HTTP_400_BAD_REQUEST)
        except Http404:
            return Response(error_response("Post not found or unauthorized"), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MyPostsListAPIView(APIView, PaginationMixin):
    """
    GET /api/my-posts/?status=DRAFT&distribution_status=FAILED&portal=1&search=abc&master_category=3
        &date_filter=today|yesterday|7d|custom&start_date=2025-10-01&end_date=2025-10-05&sort=publish_date_desc&user_id=12

    Returns posts for:
      - USER → only their own posts.
      - MASTER → all users' posts, with optional `user_id` filter.

    Includes total counts for:
      - MasterNewsPost
      - NewsDistribution

    Supported query params:
      - user_id (MASTER only)
      - status: DRAFT / PUBLISHED
      - distribution_status: SUCCESS / FAILED / PENDING
      - portal: integer
      - search: string (title, slug, category)
      - master_category: integer
      - date_filter: today | yesterday | 7d | custom
      - start_date / end_date: required if custom
      - sort: publish_date_desc | publish_date_asc | category
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            user = request.user
            params = request.query_params

            # --- Role detection ---
            user_role = getattr(getattr(user, "role", None), "role", None)
            role_name = getattr(user_role, "name", "").upper() if user_role else None

            # --- Query params ---
            status_filter = params.get("status")
            distribution_status = params.get("distribution_status")
            portal_id = params.get("portal")
            search = params.get("search")
            master_category_id = params.get("master_category")
            sort_option = params.get("sort", "publish_date_desc")
            selected_user_id = params.get("user_id")
            date_filter = params.get("date_filter", "today")  # today | yesterday | 7d | custom

            start_date = params.get("start_date")
            end_date = params.get("end_date")

            # --- Base queryset ---
            if role_name == "MASTER":
                queryset = MasterNewsPost.objects.all()
                if selected_user_id:
                    queryset = queryset.filter(created_by_id=selected_user_id)
            else:
                queryset = MasterNewsPost.objects.filter(created_by=user)

            queryset = queryset.order_by("-created_at")

            # ----- Date filter handling -----
            now = timezone.now()
            today = now.date()

            if date_filter == "today":
                queryset = queryset.filter(created_at__date=today)
            elif date_filter == "yesterday":
                queryset = queryset.filter(created_at__date=today - timedelta(days=1))
            elif date_filter == "7d":
                queryset = queryset.filter(created_at__gte=now - timedelta(days=7))
            elif date_filter == "custom":
                parsed_start = parse_date(start_date)
                parsed_end = parse_date(end_date)
                if not parsed_start or not parsed_end:
                    return Response(
                        error_response("For 'custom' date_filter, both start_date and end_date are required (YYYY-MM-DD)."),
                        status=status.HTTP_400_BAD_REQUEST
                    )
                queryset = queryset.filter(created_at__date__range=[parsed_start, parsed_end])

            # ----- Other filters -----
            if status_filter:
                queryset = queryset.filter(status__iexact=status_filter)

            if portal_id:
                queryset = queryset.filter(news_distribution__portal_id=portal_id)
                if distribution_status:
                    valid_statuses = ["SUCCESS", "FAILED", "PENDING"]
                    if distribution_status.upper() not in valid_statuses:
                        return Response(
                            error_response("Invalid distribution_status. Use SUCCESS, FAILED, or PENDING."),
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    queryset = queryset.filter(
                        news_distribution__portal_id=portal_id,
                        news_distribution__status__iexact=distribution_status
                    ).distinct()
            elif distribution_status:
                valid_statuses = ["SUCCESS", "FAILED", "PENDING"]
                if distribution_status.upper() not in valid_statuses:
                    return Response(
                        error_response("Invalid distribution_status. Use SUCCESS, FAILED, or PENDING."),
                        status=status.HTTP_400_BAD_REQUEST
                    )
                queryset = queryset.filter(
                    news_distribution__status__iexact=distribution_status
                ).distinct()

            if search:
                queryset = queryset.filter(
                    Q(title__icontains=search)
                    | Q(slug__icontains=search)
                    | Q(master_category__name__icontains=search)
                ).distinct()

            if master_category_id:
                queryset = queryset.filter(master_category_id=master_category_id)

            # ----- Sorting -----
            if sort_option == "publish_date_asc":
                queryset = queryset.order_by("created_at")
            elif sort_option == "publish_date_desc":
                queryset = queryset.order_by("-created_at")
            elif sort_option == "category":
                queryset = queryset.order_by(
                    F("master_category__name").asc(nulls_last=True),
                    "-created_at"
                )

            # ----- Count summaries -----
            distribution_qs = NewsDistribution.objects.filter(news_post__in=queryset)

            # Apply portal filter if present
            if portal_id:
                distribution_qs = distribution_qs.filter(portal_id=portal_id)

            # Apply distribution_status filter if present
            if distribution_status:
                valid_statuses = ["SUCCESS", "FAILED", "PENDING"]
                if distribution_status.upper() in valid_statuses:
                    distribution_qs = distribution_qs.filter(status__iexact=distribution_status)

            total_posts = queryset.count()
            total_distributions = distribution_qs.count()

            # ----- Pagination -----
            paginated_qs = self.paginate_queryset(queryset, request, view=self)
            serializer = MasterNewsPostSerializer(paginated_qs, many=True)

            response_data = {
                "counts": {
                    "total_master_news_posts": total_posts,
                    "total_news_distributions": total_distributions
                },
                "results": serializer.data
            }

            return self.get_paginated_response(
                response_data,
                message=f"Posts fetched successfully for {'all users' if role_name == 'MASTER' else user.username}"
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
            
class NewsReportAPIView(APIView, PaginationMixin):
    """
    GET /api/news/report/
    Returns news production summary and filtered results with pagination.

    Query Params:
    - date_filter: today | 7days | custom
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    - portal_id
    - master_category_id
    - username
    - search (title, slug, ai_title, ai_slug)
    - post_status: DRAFT | PUBLISHED
    - distribution_status: SUCCESS | FAILED | PENDING
    - page
    - page_size
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            params = request.query_params
            date_filter = params.get("date_filter", "today")
            start_date = params.get("start_date")
            end_date = params.get("end_date")
            portal_id = params.get("portal_id")
            master_category_id = params.get("master_category_id")
            username = params.get("username")
            search = params.get("search")
            post_status = params.get("post_status")
            distribution_status = params.get("distribution_status")

            today = timezone.now().date()
            start_dt, end_dt = None, None

            # --- Handle date filters ---
            if date_filter == "today":
                start_dt = today
                end_dt = today
            elif date_filter == "7days":
                start_dt = today - timedelta(days=7)
                end_dt = today
            elif date_filter == "custom" and start_date and end_date:
                start_dt = timezone.datetime.fromisoformat(start_date)
                end_dt = timezone.datetime.fromisoformat(end_date)
            else:
                start_dt = today
                end_dt = today

            # --- Base querysets ---
            master_posts = MasterNewsPost.objects.all()
            distributions = NewsDistribution.objects.select_related(
                "news_post", "portal", "master_category", "news_post__created_by"
            )

            # --- Apply date filters ---
            if start_dt and end_dt:
                master_posts = master_posts.filter(created_at__date__range=[start_dt, end_dt])
                distributions = distributions.filter(sent_at__date__range=[start_dt, end_dt])

            # --- Filter: Master Post Status ---
            if post_status:
                valid_post_statuses = ["DRAFT", "PUBLISHED"]
                if post_status.upper() not in valid_post_statuses:
                    return Response(
                        error_response("Invalid post_status. Use DRAFT or PUBLISHED."),
                        status=status.HTTP_400_BAD_REQUEST
                    )
                master_posts = master_posts.filter(status__iexact=post_status)

            # --- Filter: Distribution Status ---
            if distribution_status:
                valid_dist_statuses = ["SUCCESS", "FAILED", "PENDING"]
                if distribution_status.upper() not in valid_dist_statuses:
                    return Response(
                        error_response("Invalid distribution_status. Use SUCCESS, FAILED, or PENDING."),
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Only include master posts that have at least one distribution with this status
                master_posts = master_posts.filter(
                    news_distribution__status__iexact=distribution_status
                ).distinct()

                distributions = distributions.filter(status__iexact=distribution_status)

            # --- Filter: Portal ---
            if portal_id:
                # Only include master posts that have been distributed to this portal
                distributions = distributions.filter(portal_id=portal_id)
                master_posts = master_posts.filter(news_distribution__portal_id=portal_id).distinct()

            # --- Filter: Master Category ---
            if master_category_id:
                master_posts = master_posts.filter(master_category_id=master_category_id)
                distributions = distributions.filter(master_category_id=master_category_id)

            # --- Filter: Username ---
            if username:
                master_posts = master_posts.filter(created_by__username__icontains=username)
                distributions = distributions.filter(news_post__created_by__username__icontains=username)

            # --- Filter: Search ---
            if search:
                search_q = (
                    Q(title__icontains=search) |
                    Q(slug__icontains=search) |
                    Q(news_distribution__ai_title__icontains=search) |
                    Q(news_distribution__ai_slug__icontains=search)
                )
                master_posts = master_posts.filter(search_q).distinct()

            # --- Aggregations ---
            total_master_posts = master_posts.count()
            total_distributions = distributions.count()

            # --- Group by user ---
            user_stats = (
                master_posts.values("created_by", "created_by__username")
                .annotate(master_posts_count=Count("id"))
            )

            data = []
            for stat in user_stats:
                user_id = stat["created_by"]
                user_name = stat["created_by__username"]

                user_dists = distributions.filter(news_post__created_by_id=user_id)
                user_posts = master_posts.filter(created_by_id=user_id)
                latest_post = user_posts.order_by("-created_at").first()

                data.append({
                    "user_id": user_id,
                    "username": user_name,
                    "master_posts_count": stat["master_posts_count"],
                    "distribution_count": user_dists.count(),
                    "latest_post_date": latest_post.created_at if latest_post else None,
                    "master_posts": [
                        {
                            "id": p.id,
                            "title": p.title,
                            "slug": p.slug,
                            "status": p.status,
                            "master_category": p.master_category.name if p.master_category else None,
                            "excluded_portals": p.excluded_portals,
                            "created_at": p.created_at,
                        }
                        for p in user_posts
                    ],
                })

            # --- Paginate final data ---
            paginated_data = self.paginate_queryset(data, request, view=self)

            return self.get_paginated_response(
                {
                    "summary": {
                        "total_master_posts": total_master_posts,
                        "total_distributions": total_distributions,
                    },
                    "results": paginated_data,
                },
                message="News production report fetched successfully."
            )

        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NewsKPIAPIView(APIView):
    """
    GET /api/news/kpi/

    Returns KPI statistics for master news posts and their distributions.

    - If user role = 'user' → show only their own posts.
    - If user role = 'master' → show overall stats.

    Example Response:
    ```
    {
        "status": true,
        "message": "KPI fetched successfully",
        "data": {
            "total_posts": 245,
            "total_distributed": 780,
            "success": 600,
            "failed": 120,
            "today": {
                "posts": 5,
                "distributed": 20,
                "success": 18,
                "failed": 2
            }
        }
    }
    ```
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user
            today_date = date.today()

            # Base queryset depending on user role
            if profile.role.role.name.lower() in ["master", "admin"]:
                master_posts_qs = MasterNewsPost.objects.all()
                distribution_qs = NewsDistribution.objects.all()
            else:
                master_posts_qs = MasterNewsPost.objects.filter(created_by=profile)
                distribution_qs = NewsDistribution.objects.filter(news_post__created_by=profile)

            # --- TOTALS ---
            total_posts = master_posts_qs.count()
            total_distributed = distribution_qs.count()
            success = distribution_qs.filter(status="SUCCESS").count()
            failed = distribution_qs.filter(status="FAILED").count()

            # --- TODAY'S STATS ---
            today_posts = master_posts_qs.filter(created_at__date=today_date).count()
            today_distributed = distribution_qs.filter(sent_at__date=today_date).count()
            today_success = distribution_qs.filter(status="SUCCESS", sent_at__date=today_date).count()
            today_failed = distribution_qs.filter(status="FAILED", sent_at__date=today_date).count()

            data = {
                "total_posts": total_posts,
                "total_distributed": total_distributed,
                "success": success,
                "failed": failed,
                "today": {
                    "posts": today_posts,
                    "distributed": today_distributed,
                    "success": today_success,
                    "failed": today_failed,
                },
            }

            return Response(
                success_response(data=data, message="KPI fetched successfully"),
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
            

class PortalStatsAPIView(APIView):
    """
    GET /api/portal-stats/?portal_id=1

    Returns:
    - Top Performing Categories (MasterCategory-wise post counts)
    - Weekly Performance (Success/Failed counts for each day)
    - Top Contributors (User-wise distribution count in this portal)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            portal_id = request.query_params.get("portal_id")
            if not portal_id:
                return Response(
                    {"success": False, "error": "portal_id is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            today = timezone.now().date()
            last_week = today - timedelta(days=6)

            # --- Base Queryset ---
            distributions = NewsDistribution.objects.filter(portal_id=portal_id)

            # --- 1️⃣ Top Performing Categories ---
            top_categories = (
                distributions.filter(master_category__isnull=False)
                .values("master_category__id", "master_category__name")
                .annotate(total_posts=Count("news_post", distinct=True))
                .order_by("-total_posts")[:10]
            )

            # --- 2️⃣ Weekly Performance (last 7 days success/fail per day) ---
            weekly_data = (
                distributions.filter(sent_at__date__range=[last_week, today])
                .values("sent_at__date", "status")
                .annotate(count=Count("id"))
            )

            # Build structured weekly response
            week_stats = defaultdict(lambda: {"SUCCESS": 0, "FAILED": 0})
            for entry in weekly_data:
                date = entry["sent_at__date"]
                status_val = entry["status"]
                count = entry["count"]
                if status_val in ["SUCCESS", "FAILED"]:
                    week_stats[date][status_val] = count

            weekly_performance = []
            for i in range(7):
                date = today - timedelta(days=i)
                weekly_performance.append({
                    "day": date.strftime("%a"),
                    "date": date,
                    "success": week_stats[date]["SUCCESS"],
                    "failed": week_stats[date]["FAILED"],
                })
            weekly_performance.reverse()

            # --- 3️⃣ Top Contributors (users who distributed most in this portal) ---
            top_contributors = (
                distributions
                .values("news_post__created_by__id", "news_post__created_by__username")
                .annotate(total_distributions=Count("id"))
                .order_by("-total_distributions")[:10]
            )

            response_data = {
                "portal_id": portal_id,
                "top_performing_categories": top_categories,
                "weekly_performance": weekly_performance,
                "top_contributors": top_contributors,
            }

            return Response(
                {"success": True, "message": "Portal stats fetched successfully", "data": response_data},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GlobalStatsAPIView(APIView):
    """
    GET /api/global-stats/

    Returns:
    - Top Performing Categories (MasterCategory-wise post counts)
    - Weekly Performance (Success/Failed counts for each day, last 7 days)
    - Top Contributors (User-wise total distributions across all portals)
    Role logic:
        - MASTER: weekly performance for all users
        - USER: weekly performance for their own posts only
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            user = request.user
            role_obj = getattr(user, "role", None)
            role_name = getattr(role_obj.role, "name", "").upper() if role_obj else None

            today = timezone.now().date()
            last_week = today - timedelta(days=6)

            # --- Base Queryset ---
            distributions = NewsDistribution.objects.select_related("portal", "master_category", "news_post")

            # --- 1️⃣ Top Performing Categories ---
            top_categories = (
                distributions.filter(master_category__isnull=False)
                .values("master_category__id", "master_category__name")
                .annotate(total_posts=Count("news_post", distinct=True))
                .order_by("-total_posts")[:10]
            )

            # --- 2️⃣ Weekly Performance (SUCCESS / FAILED for last 7 days) ---
            weekly_qs = distributions.filter(sent_at__date__range=[last_week, today])

            # Apply user-level filter if not MASTER
            if role_name != "MASTER":
                weekly_qs = weekly_qs.filter(news_post__created_by=user)

            weekly_data = (
                weekly_qs
                .values("sent_at__date", "status")
                .annotate(count=Count("id"))
            )

            week_stats = defaultdict(lambda: {"SUCCESS": 0, "FAILED": 0})
            for entry in weekly_data:
                date = entry["sent_at__date"]
                status_val = entry["status"]
                count = entry["count"]
                if status_val in ["SUCCESS", "FAILED"]:
                    week_stats[date][status_val] = count

            weekly_performance = []
            for i in range(7):
                date = today - timedelta(days=i)
                weekly_performance.append({
                    "day": date.strftime("%a"),
                    "date": date,
                    "success": week_stats[date]["SUCCESS"],
                    "failed": week_stats[date]["FAILED"],
                })
            weekly_performance.reverse()

            # --- 3️⃣ Top Contributors (Global distribution counts) ---
            top_contributors = (
                distributions
                .values("news_post__created_by__id", "news_post__created_by__username")
                .annotate(total_distributions=Count("id"))
                .order_by("-total_distributions")[:10]
            )

            response_data = {
                "top_performing_categories": top_categories,
                "weekly_performance": weekly_performance,
                "top_contributors": top_contributors,
            }

            return Response(
                {"success": True, "message": "Global stats fetched successfully", "data": response_data},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InactivityAlertsAPIView(APIView, PaginationMixin):
    """
    GET /api/admin/inactivity-alerts/?range=24h|48h|7d&page=1&page_size=10

    Returns a paginated list of master categories that have not had any
    published posts within the given time range.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            range_param = request.query_params.get("range", "24h").lower()
            now = timezone.now()

            # Determine cutoff date
            if range_param == "48h":
                cutoff = now - timezone.timedelta(hours=48)
            elif range_param == "7d":
                cutoff = now - timezone.timedelta(days=7)
            else:  # Default 24h
                cutoff = now - timezone.timedelta(hours=24)

            # Get last publish timestamp for each master category
            category_last_published = (
                MasterNewsPost.objects.filter(status="PUBLISHED")
                .values("master_category")
                .annotate(last_publish=Max("created_at"))
            )

            # Map category_id -> last_publish
            last_publish_map = {
                item["master_category"]: item["last_publish"]
                for item in category_last_published
                if item["master_category"]
            }

            inactive_categories = []

            for category in MasterCategory.objects.all():
                last_publish = last_publish_map.get(category.id)
                if not last_publish or last_publish < cutoff:
                    # Get assigned users and groups
                    assignments = UserCategoryGroupAssignment.objects.filter(
                        Q(master_category=category) | Q(group__master_categories=category)
                    ).select_related("user", "group")

                    assigned_users = []
                    assigned_groups = set()

                    for a in assignments:
                        if a.user:
                            assigned_users.append(a.user.email)
                        if a.group:
                            assigned_groups.add(a.group.name)

                    inactive_categories.append({
                        "master_category": category.name,
                        "last_publish": last_publish,
                        "assigned_users": assigned_users,
                        "assigned_groups": list(assigned_groups),
                    })

            # Apply pagination
            paginated_data = self.paginate_queryset(inactive_categories, request)
            if paginated_data is not None:
                return self.get_paginated_response(
                    paginated_data,
                    message=f"Inactivity data fetched successfully for {range_param.upper()} range"
                )

            # (Fallback if pagination disabled)
            data = {
                "range": range_param,
                "inactive_count": len(inactive_categories),
                "inactive_categories": inactive_categories,
            }
            return Response(
                success_response(data, "Inactivity data fetched successfully"),
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class NewsDistributionRateOverTimeAPIView(APIView):
    """
    GET /api/admin/success-rate/?mode=hourly|daily

    Returns success rate trends for news distributions.
    - MASTER role: shows system-wide stats.
    - USER role: shows only that user's posts' distributions.

    Query Params:
    - mode = hourly (last 7 hours) | daily (last 7 days)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            role = getattr(getattr(user, "role", None), "role", None)
            mode = request.query_params.get("mode", "daily").lower()

            now = timezone.now()
            if mode == "hourly":
                start_time = now - timezone.timedelta(hours=7)
                trunc_field = TruncHour("created_at")
            else:
                start_time = now - timezone.timedelta(days=7)
                trunc_field = TruncDay("created_at")

            # Role-based Query Selection
            if role and role.name.upper() == "MASTER":
                distributions_qs = NewsDistribution.objects.filter(created_at__gte=start_time)

            elif role and role.name.upper() == "USER":
                distributions_qs = NewsDistribution.objects.filter(
                    created_at__gte=start_time,
                    news_post__created_by=user
                )

            else:
                return Response(
                    error_response("Role not recognized or not assigned"),
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Aggregation
            qs = (
                distributions_qs
                .annotate(period=trunc_field)
                .values("period")
                .annotate(
                    total_attempts=Count("id"),
                    success_count=Count("id", filter=Q(status="SUCCESS")),
                    failed_count=Count("id", filter=Q(status="FAILED")),
                )
                .order_by("period")
            )

            data = []
            for record in qs:
                total_attempts = record["total_attempts"] or 0
                success_count = record["success_count"] or 0
                failed_count = record["failed_count"] or 0

                success_rate = (
                    round((success_count / total_attempts) * 100, 2)
                    if total_attempts > 0
                    else 0.0
                )

                label = (
                    record["period"].strftime("%Y-%m-%d %H:00")
                    if mode == "hourly"
                    else record["period"].strftime("%Y-%m-%d")
                )

                data.append({
                    "label": label,
                    "total_attempts": total_attempts,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "success_rate": success_rate,
                })

            return Response(
                success_response(data, "Success rate trend fetched successfully"),
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FailureReasonsStatsAPIView(APIView):
    """
    GET /api/analytics/failure-reasons/?range=24h|7d|all

    Returns aggregated failure reasons and their counts.

    Role-based:
    - MASTER: gets all data.
    - USER: gets only their own NewsDistributions.

    Example Response:
    {
        "success": true,
        "data": [
            {"reason": "Timeout", "count": 5},
            {"reason": "Invalid API Key", "count": 3},
            {"reason": "Category Mapping Missing", "count": 2}
        ]
    }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user

            # Get user role
            user_role = getattr(user.role.role, "name", None) if hasattr(user, "role") else None

            # Time range filter
            time_range = request.query_params.get("range", "24h")
            now = timezone.now()
            print(time_range)

            if time_range == "24h":
                start_time = now - timedelta(hours=24)
            elif time_range == "7d":
                start_time = now - timedelta(days=7)
            else:
                start_time = None  # all time

            filters = Q(status="FAILED")
            if start_time:
                filters &= Q(sent_at__gte=start_time)

            # Restrict by user role
            if user_role and user_role.upper() != "MASTER":
                # Only include NewsDistributions where the NewsPost was created by this user
                filters &= Q(news_post__created_by=user)

            # Aggregate by failure reason (based on response_message)
            queryset = (
                NewsDistribution.objects.filter(filters)
                .exclude(response_message__isnull=True)
                .exclude(response_message__exact="")
                .values("response_message")
                .annotate(count=Count("id"))
                .order_by("-count")
            )

            data = [
                {"reason": item["response_message"][:200], "count": item["count"]}
                for item in queryset
            ]

            return Response({"success": True, "data": data}, status=200)

        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=500)


class MasterCategoryHeatmapAPIView(APIView):
    """
    GET /api/analytics/master-category-heatmap/?range=1d|7d|30d

    Returns total postings per MasterCategory for the given range,
    compared with the previous same-length range.

    Role-based:
    - MASTER: sees all data
    - USER: sees only their own posts

    Example Response:
    {
        "success": true,
        "data": {
            "current_start": "2025-10-01",
            "current_end": "2025-10-07",
            "previous_start": "2025-09-24",
            "previous_end": "2025-10-01",
            "categories": [
                {
                    "master_category_id": 1,
                    "master_category_name": "Politics",
                    "current_period_posts": 120,
                    "previous_period_posts": 100,
                    "change_ratio": 20.0,
                    "trend": "increase"
                }
            ]
        }
    }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user

            # --- Role detection ---
            user_role = getattr(user.role.role, "name", None) if hasattr(user, "role") else None
            is_master = user_role and user_role.upper() == "MASTER"

            # --- Range parameter ---
            range_param = request.query_params.get("range", "7d").lower()
            now = timezone.now().date()

            if range_param == "1d":
                days = 1
            elif range_param == "30d":
                days = 30
            else:
                days = 7  # default

            current_start = now - timedelta(days=days)
            current_end = now
            previous_start = current_start - timedelta(days=days)
            previous_end = current_start

            # --- Base queryset ---
            base_qs = MasterNewsPost.objects.filter(master_category__isnull=False)
            if not is_master:
                base_qs = base_qs.filter(created_by=user)

            # --- Current period stats ---
            current_stats = (
                base_qs.filter(created_at__date__gte=current_start, created_at__date__lte=current_end)
                .values("master_category__id", "master_category__name")
                .annotate(current_posts=Count("id"))
            )

            # --- Previous period stats ---
            previous_stats = (
                base_qs.filter(created_at__date__gte=previous_start, created_at__date__lte=previous_end)
                .values("master_category__id")
                .annotate(previous_posts=Count("id"))
            )

            previous_map = {p["master_category__id"]: p["previous_posts"] for p in previous_stats}

            # --- Merge results and calculate ratios ---
            results = []
            for item in current_stats:
                cat_id = item["master_category__id"]
                cat_name = item["master_category__name"]

                # Skip categories that are still null (extra safeguard)
                if not cat_id or not cat_name:
                    continue

                current_count = item["current_posts"]
                previous_count = previous_map.get(cat_id, 0)

                if previous_count == 0:
                    ratio = 100.0 if current_count > 0 else 0.0
                else:
                    ratio = ((current_count - previous_count) / previous_count) * 100

                trend = "increase" if ratio > 0 else "decrease" if ratio < 0 else "same"

                results.append({
                    "master_category_id": cat_id,
                    "master_category_name": cat_name,
                    "current_period_posts": current_count,
                    "previous_period_posts": previous_count,
                    "change_ratio": round(ratio, 2),
                    "trend": trend,
                })

            return Response({
                "success": True,
                "data": {
                    "current_start": str(current_start),
                    "current_end": str(current_end),
                    "previous_start": str(previous_start),
                    "previous_end": str(previous_end),
                    "categories": results
                }
            }, status=200)

        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=500)
        

class UserPostStatsAPIView(APIView, PaginationMixin):
    """
    GET /api/master/users/post-stats/?user_id=5&date_filter=7d&start_date=2025-10-01&end_date=2025-10-10

    For MASTER users only.
    Returns posting and distribution statistics for all users (or a specific user).

    Query Params:
    - user_id (optional): Filter by specific user
    - date_filter: today | yesterday | 7d | 1m | custom
    - start_date / end_date: required if date_filter=custom

    Example Response:
    {
        "status": true,
        "pagination": {...},
        "data": [
            {
                "user_id": 3,
                "username": "editor_1",
                "num_master_posts": 12,
                "num_total_distributions": 28,
                "num_successful_distributions": 24,
                "num_failed_distributions": 4,
                "assigned_master_categories": ["Business", "Sports", "Politics"]
            },
            ...
        ],
        "message": "User posting stats fetched successfully"
    }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            role_obj = getattr(user, "role", None)
            role_name = getattr(role_obj.role, "name", "").upper() if role_obj else None

            # --- Restrict access to MASTER users only ---
            if role_name != "MASTER":
                return Response(
                    error_response("Access denied. Only MASTER users can access this endpoint."),
                    status=status.HTTP_403_FORBIDDEN,
                )

            # --- Query Parameters ---
            params = request.query_params
            selected_user_id = params.get("user_id")
            date_filter = params.get("range")  # today | yesterday | 7d | 1m | custom
            start_date = params.get("start_date")
            end_date = params.get("end_date")

            # --- Base Querysets ---
            posts_qs = MasterNewsPost.objects.select_related("created_by").all()
            dist_qs = NewsDistribution.objects.select_related("news_post", "news_post__created_by")

            # --- Apply Date Filters ---
            now = timezone.now()
            today = now.date()
            
            print(date_filter)

            if date_filter == "today":
                posts_qs = posts_qs.filter(created_at__date=today)
                dist_qs = dist_qs.filter(sent_at__date=today)
            elif date_filter == "yesterday":
                posts_qs = posts_qs.filter(created_at__date=today - timedelta(days=1))
                dist_qs = dist_qs.filter(sent_at__date=today - timedelta(days=1))
            elif date_filter == "7d":
                posts_qs = posts_qs.filter(created_at__gte=now - timedelta(days=7))
                dist_qs = dist_qs.filter(sent_at__gte=now - timedelta(days=7))
            elif date_filter == "1m":
                posts_qs = posts_qs.filter(created_at__gte=now - timedelta(days=30))
                dist_qs = dist_qs.filter(sent_at__gte=now - timedelta(days=30))
            elif date_filter == "custom":
                parsed_start = parse_date(start_date)
                parsed_end = parse_date(end_date)
                if not parsed_start or not parsed_end:
                    return Response(
                        error_response("For 'custom' date_filter, both start_date and end_date are required (YYYY-MM-DD)."),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                posts_qs = posts_qs.filter(created_at__date__range=[parsed_start, parsed_end])
                dist_qs = dist_qs.filter(sent_at__date__range=[parsed_start, parsed_end])

            # --- Optional: Filter by specific user ---
            if selected_user_id:
                posts_qs = posts_qs.filter(created_by_id=selected_user_id)
                dist_qs = dist_qs.filter(news_post__created_by_id=selected_user_id)

            # --- Aggregate Stats Per User ---
            users_data = (
                posts_qs.values("created_by_id", "created_by__username")
                .annotate(
                    num_master_posts=Count("id", distinct=True),
                    num_total_distributions=Coalesce(
                        Count("news_distribution", distinct=True), 0
                    ),
                    num_successful_distributions=Coalesce(
                        Count("news_distribution", filter=Q(news_distribution__status="SUCCESS"), distinct=True), 0
                    ),
                    num_failed_distributions=Coalesce(
                        Count("news_distribution", filter=Q(news_distribution__status="FAILED"), distinct=True), 0
                    ),
                )
                .order_by("created_by__username")
            )

            # --- Map Assigned Master Categories for Each User ---
            user_ids = [u["created_by_id"] for u in users_data]
            user_categories_map = (
                UserCategoryGroupAssignment.objects.filter(
                    user_id__in=user_ids, master_category__isnull=False
                )
                .values("user_id", "master_category__name")
            )

            # Build a mapping { user_id: [category names] }
            category_mapping = {}
            for entry in user_categories_map:
                category_mapping.setdefault(entry["user_id"], []).append(entry["master_category__name"])

            # --- Merge category data ---
            for user in users_data:
                user["assigned_master_categories"] = category_mapping.get(user["created_by_id"], [])

            # --- Pagination ---
            paginated_data = self.paginate_queryset(users_data, request)
            return self.get_paginated_response(
                paginated_data,
                message="User posting stats fetched successfully",
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
