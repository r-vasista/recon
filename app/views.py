import requests
from urllib.parse import urljoin
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
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

            # paginated_queryset = self.paginate_queryset(queryset, request)

            # serializer = PortalCategorySerializer(paginated_queryset, many=True)
            # return self.get_paginated_response(serializer.data)
            serializer = PortalCategorySerializer(queryset, many=True)
            return Response(success_response(serializer.data), status=status.HTTP_200_OK)

        except Portal.DoesNotExist:
            return Response(error_response("Portal not found"), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MasterCategoryView(APIView):
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

            queryset = MasterCategory.objects.all().order_by("name")

            if mapped and mapped.lower() == "true":
                queryset = queryset.filter(mappings__isnull=False).distinct()

            serializer = MasterCategorySerializer(queryset, many=True)
            return Response(
                success_response(serializer.data, "Master categories fetched"),
                status=status.HTTP_200_OK
            )

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
    
    
class MasterCategoryMappingView(APIView):
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

            # Filtering by master_category id
            master_category_id = request.query_params.get("master_category")
            if master_category_id:
                queryset = queryset.filter(master_category_id=master_category_id)

            # Filtering by portal name
            portal_name = request.query_params.get("portal")
            if portal_name:
                queryset = queryset.filter(portal_category__portal__name__iexact=portal_name)

            serializer = MasterCategoryMappingSerializer(queryset, many=True)
            return Response(success_response("Mappings fetched", serializer.data), status=status.HTTP_200_OK)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
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
    """

    def get(self, request, master_category_id):
        try:
            # Validate master category exists
            try:
                master_category = MasterCategory.objects.get(id=master_category_id)
            except MasterCategory.DoesNotExist:
                raise Http404("Master Category not found")

            # Fetch all mappings
            mappings = MasterCategoryMapping.objects.filter(
                master_category=master_category
            ).select_related("portal_category", "portal_category__portal")

            # Paginate
            paginated_queryset = self.paginate_queryset(mappings, request)
            serializer = MasterCategoryMappingSerializer(paginated_queryset, many=True)

            return self.get_paginated_response(serializer.data)

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
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            user = request.user
            master_category_id = request.data.get("master_category_id")

            if not master_category_id:
                return Response(
                    error_response("Please provide master_category_id."),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 1. Validate MasterNewsPost
            news_post = get_object_or_404(MasterNewsPost, pk=pk)

            # 2. Check if user has that master category assigned
            assignment = UserCategoryGroupAssignment.objects.filter(
                user=user, master_category_id=master_category_id
            ).first()

            if not assignment:
                return Response(
                    error_response("You are not assigned to this master category."),
                    status=status.HTTP_403_FORBIDDEN,
                )

            # 3. Get mappings (portals under this master category)
            
            # If no master_category_id provided, try to fetch default mapping for this portal
            if not master_category_id:
                default_mapping = MasterCategoryMapping.objects.filter(
                    portal=portal, is_default=True
                ).select_related("master_category").first()

                if not default_mapping:
                    return Response(
                        error_response(
                            "No default master category is mapped for this portal. Please provide master_category_id."
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Use default master category from mapping
                master_category_id = default_mapping.master_category.id

            # Now fetch all portal mappings under this master category
            mappings = MasterCategoryMapping.objects.filter(
                master_category_id=master_category_id
            ).select_related("portal_category", "portal_category__portal")

            if not mappings.exists():
                return Response(
                    error_response("No portals mapped for this master category."),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            excluded_portals = request.data.get("excluded_portals", [])
            if not isinstance(excluded_portals, list):
                excluded_portals = []

            results = []

            # 4. Iterate through mapped portals
            for mapping in mappings:
                portal = mapping.portal_category.portal
                portal_category = mapping.portal_category

                # Skip excluded ones
                if portal.id in excluded_portals or portal.name in excluded_portals:
                    results.append({
                        "portal": portal.name,
                        "category": portal_category.name,
                        "success": False,
                        "response": "Skipped manually by user",
                    })
                    continue

                # Rewriting logic same as before ↓
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
                    rewritten_title, rewritten_short, rewritten_content, rewritten_meta, rewritten_slug = generate_variation_with_gpt(
                        news_post.title,
                        news_post.short_description,
                        news_post.content,
                        prompt_text,
                        news_post.meta_title,
                        news_post.slug,
                        portal_name=portal.name,
                    )

                # Get portal user mapping
                portal_user = PortalUserMapping.objects.filter(
                    user=user, portal=portal, status="MATCHED"
                ).first()
                if not portal_user:
                    results.append({
                        "portal": portal.name,
                        "category": portal_category.name,
                        "success": False,
                        "response": "No valid portal user mapping found.",
                    })
                    continue

                payload = {
                    "post_cat": portal_category.external_id if portal_category else None,
                    "post_title": rewritten_title,
                    "post_short_des": rewritten_short,
                    "post_des": rewritten_content,
                    "meta_title": rewritten_meta,
                    "slug": rewritten_slug,
                    "post_tag": news_post.post_tag or "",
                    "author": portal_user.portal_user_id,
                    
                    # Dates
                    "Event_date": (news_post.Event_date or timezone.now().date()).isoformat(),
                    "Eventend_date": (news_post.Event_end_date or timezone.now().date()).isoformat(),
                    "schedule_date": (news_post.schedule_date or timezone.now()).isoformat(),

                    # Flags
                    "is_active": int(bool(news_post.latest_news)) if news_post.latest_news is not None else 0,
                    "Event": int(bool(news_post.upcoming_event)) if news_post.upcoming_event is not None else 0,
                    "Head_Lines": int(bool(news_post.Head_Lines)) if news_post.Head_Lines is not None else 0,
                    "articles": int(bool(news_post.articles)) if news_post.articles is not None else 0,
                    "trending": int(bool(news_post.trending)) if news_post.trending is not None else 0,
                    "BreakingNews": int(bool(news_post.BreakingNews)) if news_post.BreakingNews is not None else 0,
                    "post_status": news_post.counter or 0,
                }
                files = {"post_image": open(news_post.post_image.path, "rb")} if news_post.post_image else {}

                api_url = f"{portal.base_url}/api/create-news/"
                try:
                    response = requests.post(api_url, data=payload, files=files, timeout=10)
                    success = response.status_code in [200, 201]
                    response_msg = response.text
                except Exception as e:
                    success = False
                    response_msg = str(e)

                NewsDistribution.objects.update_or_create(
                    news_post=news_post,
                    portal=portal,
                    defaults={
                        "portal_category": portal_category,
                        "master_category_id": master_category_id,
                        "status": "SUCCESS" if success else "FAILED",
                        "response_message": response_msg,
                        "ai_title": rewritten_title,
                        "ai_short_description": rewritten_short,
                        "ai_content": rewritten_content,
                        "ai_meta_title": rewritten_meta,
                        "ai_slug": rewritten_slug,
                    },
                )

                results.append({
                    "portal": portal.name,
                    "category": portal_category.name,
                    "success": success,
                    "response": response_msg,
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

            serializer = MasterNewsPostSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(
                    success_response(
                        serializer.data,
                        "News post created successfully"
                    ),
                    status=status.HTTP_201_CREATED
                )
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
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            queryset = NewsDistribution.objects.select_related(
                "news_post", "portal", "master_category", "portal_category"
            ).order_by("-sent_at")

            # ---- Filters ----
            created_by = request.query_params.get("created_by")
            portal = request.query_params.get("portal")
            portal_category = request.query_params.get("portal_category")
            status_filter = request.query_params.get("status")

            if created_by:
                queryset = queryset.filter(news_post__created_by_id=created_by)
            if portal:
                queryset = queryset.filter(portal_id=portal)
            if portal_category:
                queryset = queryset.filter(portal_category_id=portal_category)
            if status_filter:
                queryset = queryset.filter(status=status_filter.upper())

            # ---- Pagination ----
            paginated_qs = self.paginate_queryset(queryset, request, view=self)
            serializer = NewsDistributionListSerializer(paginated_qs, many=True, context={"request": request})

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
        try:
            user = request.user
            role = getattr(user.role, "role", None)  # UserRole relation

            # If role is ADMIN → show global stats
            if role and role.name.upper() == "MASTER":
                stats = {
                    "total_posts": MasterNewsPost.objects.count(),
                    "total_users": User.objects.count(),
                    "total_portals": Portal.objects.count(),
                    "total_master_categories": MasterCategory.objects.count(),
                }

                # Global distribution stats
                total_distributions = NewsDistribution.objects.count()
                successful_distributions = NewsDistribution.objects.filter(status="SUCCESS").count()
                failed_distributions = NewsDistribution.objects.filter(status="FAILED").count()
                pending_distributions = NewsDistribution.objects.filter(status="PENDING").count()
                retry_counts = NewsDistribution.objects.aggregate(total=Sum("retry_count"))["total"] or 0

                portal_distribution = (
                    NewsDistribution.objects
                    .values("portal__name")
                    .annotate(total=Count("id"))
                    .order_by("portal__name")
                )
                portal_distribution_dict = {item["portal__name"]: item["total"] for item in portal_distribution}

                stats.update({
                    "news_distribution": {
                        "total_distributions": total_distributions,
                        "successful_distributions": successful_distributions,
                        "failed_distributions": failed_distributions,
                        "pending_distributions": pending_distributions,
                        "retry_counts": retry_counts,
                        "portal_distribution_counts": portal_distribution_dict
                    }
                })

            # If role is USER → show scoped stats
            elif role and role.name.upper() == "USER":
                # Posts created by this user
                user_posts = MasterNewsPost.objects.filter(created_by=user)

                # Assignments
                assignments = UserCategoryGroupAssignment.objects.filter(user=user)

                # Portals assigned (unique set)
                portals = set()
                master_categories = set()
                for assignment in assignments:
                    if assignment.master_category:
                        master_categories.add(assignment.master_category)
                    if assignment.group:
                        master_categories.update(assignment.group.master_categories.all())
                    for portal, _ in get_portals_from_assignment(assignment):
                        portals.add(portal)

                # NewsDistribution stats (only for user's posts)
                user_distributions = NewsDistribution.objects.filter(news_post__created_by=user)
                total_distributions = user_distributions.count()
                successful_distributions = user_distributions.filter(status="SUCCESS").count()
                failed_distributions = user_distributions.filter(status="FAILED").count()
                pending_distributions = user_distributions.filter(status="PENDING").count()
                retry_counts = user_distributions.aggregate(total=Sum("retry_count"))["total"] or 0

                portal_distribution = (
                    user_distributions
                    .values("portal__name")
                    .annotate(total=Count("id"))
                    .order_by("portal__name")
                )
                portal_distribution_dict = {item["portal__name"]: item["total"] for item in portal_distribution}

                stats = {
                    "total_posts": user_posts.count(),
                    "total_portals": len(portals),
                    "total_master_categories": len(master_categories),
                    "news_distribution": {
                        "total_distributions": total_distributions,
                        "successful_distributions": successful_distributions,
                        "failed_distributions": failed_distributions,
                        "pending_distributions": pending_distributions,
                        "retry_counts": retry_counts,
                        "portal_distribution_counts": portal_distribution_dict
                    }
                }

            else:
                return Response(
                    error_response("Role not recognized or not assigned"),
                    status=status.HTTP_403_FORBIDDEN
                )

            return Response(
                success_response(stats, "Stats fetched successfully"),
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DomainDistributionStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            user = request.user
            role = getattr(user.role, "role", None)  # UserRole relation

            stats = []

            # ADMIN → all portals
            if role and role.name.upper() == "MASTER":
                domains = Portal.objects.all()
                for domain in domains:
                    distributions = NewsDistribution.objects.filter(portal=domain)

                    domain_stats = {
                        "portal_id": domain.id,
                        "portal_name": domain.name,
                        "total_distributions": distributions.count(),
                        "successful_distributions": distributions.filter(status="SUCCESS").count(),
                        "failed_distributions": distributions.filter(status="FAILED").count(),
                        "pending_distributions": distributions.filter(status="PENDING").count(),
                        "retry_counts": distributions.aggregate(total=Sum("retry_count"))["total"] or 0,
                    }
                    stats.append(domain_stats)

            # USER → only assigned portals + their own posts
            elif role and role.name.upper() == "USER":
                assignments = UserCategoryGroupAssignment.objects.filter(user=user)

                # Collect unique portals assigned
                assigned_portals = set()
                for assignment in assignments:
                    for portal, _ in get_portals_from_assignment(assignment):
                        assigned_portals.add(portal)

                # Loop through only assigned portals
                for domain in assigned_portals:
                    distributions = NewsDistribution.objects.filter(
                        portal=domain,
                        news_post__created_by=user  # only user's posts
                    )

                    domain_stats = {
                        "portal_id": domain.id,
                        "portal_name": domain.name,
                        "total_distributions": distributions.count(),
                        "successful_distributions": distributions.filter(status="SUCCESS").count(),
                        "failed_distributions": distributions.filter(status="FAILED").count(),
                        "pending_distributions": distributions.filter(status="PENDING").count(),
                        "retry_counts": distributions.aggregate(total=Sum("retry_count"))["total"] or 0,
                    }
                    stats.append(domain_stats)

            else:
                return Response(
                    error_response("Role not recognized or not assigned"),
                    status=status.HTTP_403_FORBIDDEN
                )

            return Response(
                success_response(stats, "Domain-wise distribution stats fetched successfully"),
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
                response = requests.get(api_url, timeout=10)
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
