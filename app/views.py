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


from .models import (
    Portal, PortalCategory, MasterCategory, MasterCategoryMapping, Group, MasterNewsPost, NewsDistribution
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

            paginated_queryset = self.paginate_queryset(queryset, request)

            serializer = PortalCategorySerializer(paginated_queryset, many=True)
            return self.get_paginated_response(serializer.data)

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
            queryset = MasterCategory.objects.all().order_by("name")
            serializer = MasterCategorySerializer(queryset, many=True)
            return Response(success_response(serializer.data, "Master categories fetched"), status=status.HTTP_200_OK)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
    POST /api/master-category-mappings/ → Create mapping
    GET /api/master-category-mappings/?master_category=1&portal=TOI → List mappings
    DELETE /api/master-category-mappings/{id}/ → Delete mapping
    """

    def post(self, request):
        """
        Example Payload:
        {
            "master_category": 1,
            "portal_categories": [5, 6, 7]
        }
        """
        try:
            master_category_id = request.data.get("master_category")
            portal_category_ids = request.data.get("portal_categories", [])

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
                    )
                    if created:
                        created_mappings.append(mapping)
                    else:
                        skipped_mappings.append(portal_cat_id)
                except Exception as e:
                    skipped_mappings.append({"id": portal_cat_id, "error": str(e)})

            serializer = MasterCategoryMappingSerializer(created_mappings, many=True)
            response_data = {
                "created": serializer.data,
                "skipped": skipped_mappings,
            }
            return Response(success_response(response_data,"Mappings processed"), status=status.HTTP_201_CREATED)

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
    Publishes a MasterNewsPost to all portals assigned to the requesting user.
    Skips if already SUCCESS, retries if FAILED/PENDING.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            user = request.user

            # 1. Get the MasterNewsPost
            news_post = get_object_or_404(MasterNewsPost, pk=pk)

            # 2. Find assignments linked to this user
            assignments = UserCategoryGroupAssignment.objects.filter(user=user)

            if not assignments.exists():
                return Response(
                    error_response("No assignments found for this user."),
                    status=status.HTTP_400_BAD_REQUEST
                )

            results = []

            # 3. Traverse all assignments → portals via mappings
            for assignment in assignments:
                for portal, portal_category in get_portals_from_assignment(assignment):
                    
                    # 3.a Check existing distribution
                    distribution = NewsDistribution.objects.filter(
                        news_post=news_post,
                        portal=portal
                    ).first()

                    if distribution and distribution.status == "SUCCESS":
                        results.append({
                            "portal": portal.name,
                            "category": portal_category.name if portal_category else None,
                            "success": True,
                            "response": "Skipped - already successfully distributed",
                        })
                        continue

                    # 4. Get portal-specific prompt
                    portal_prompt = getattr(portal, "prompt", None)
                    prompt_text = (
                        portal_prompt.prompt_text if portal_prompt else
                        "You are a news editor. Rewrite the given content slightly for clarity and engagement."
                    )

                    # 5. Run GPT rewriting
                    rewritten_title, rewritten_short, rewritten_content = generate_variation_with_gpt(
                        news_post.title,
                        news_post.short_description,
                        news_post.content,
                        prompt_text
                    )

                    # 6. Build payload
                    mapping = PortalUserMapping.objects.filter(
                        user=user, portal=portal, status="MATCHED"
                    ).first()
                    if not mapping or not mapping.portal_user_id:
                        return Response(
                            error_response("No valid portal user mapping found for this user."),
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    payload = {
                        "post_cat": portal_category.external_id if portal_category else None,
                        "post_title": rewritten_title,
                        "post_short_des": rewritten_short,
                        "post_des": rewritten_content,
                        "post_tag": news_post.post_tag or "#recon",
                        "author": mapping.portal_user_id,

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

                    # 7. Call portal API
                    api_url = f'{portal.base_url}/api/create-news/'
                    try:
                        response = requests.post(api_url, data=payload, files=files, timeout=10)
                        success = response.status_code in [200, 201]
                        response_msg = response.text
                    except Exception as e:
                        success = False
                        response_msg = str(e)

                    # 8. Handle distribution record
                    if distribution:
                        # Retry update
                        distribution.retry_count += 1
                        distribution.status = "SUCCESS" if success else "FAILED"
                        distribution.response_message = response_msg
                        distribution.ai_title = rewritten_title
                        distribution.ai_short_description = rewritten_short
                        distribution.ai_content = rewritten_content
                        distribution.save(update_fields=[
                            "retry_count", "status", "response_message",
                            "ai_title", "ai_short_description", "ai_content", "sent_at"
                        ])
                    else:
                        # New distribution
                        NewsDistribution.objects.create(
                            news_post=news_post,
                            portal=portal,
                            portal_category=portal_category,
                            group=assignment.group,
                            master_category=assignment.master_category,
                            ai_title=rewritten_title,
                            ai_short_description=rewritten_short,
                            ai_content=rewritten_content,
                            status="SUCCESS" if success else "FAILED",
                            response_message=response_msg,
                            retry_count=0,
                        )

                    results.append({
                        "portal": portal.name,
                        "category": portal_category.name if portal_category else None,
                        "success": success,
                        "response": response_msg,
                        "retried": bool(distribution),
                    })

            return Response(
                success_response(results, "News published to portals"),
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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
            # Basic stats
            stats = {
                "total_posts": MasterNewsPost.objects.count(),
                "total_users": User.objects.count(),
                "total_portals": Portal.objects.count(),
                "total_master_categories": MasterCategory.objects.count(),
            }

            # News Distribution stats
            total_distributions = NewsDistribution.objects.count()
            successful_distributions = NewsDistribution.objects.filter(status="SUCCESS").count()
            failed_distributions = NewsDistribution.objects.filter(status="FAILED").count()
            pending_distributions = NewsDistribution.objects.filter(status="PENDING").count()
            retry_counts = NewsDistribution.objects.aggregate(total=Sum("retry_count"))["total"] or 0

            # Portal wise distribution counts
            portal_distribution = (
                NewsDistribution.objects
                .values("portal__name")
                .annotate(total=Count("id"))
                .order_by("portal__name")
            )
            portal_distribution_dict = {
                item["portal__name"]: item["total"] for item in portal_distribution
            }

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
    def get(self, request, *args, **kwargs):
        try:
            domains = Portal.objects.all()
            stats = []

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

            return Response(
                success_response(stats, "Domain-wise distribution stats fetched successfully"),
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                error_response(str(e)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )