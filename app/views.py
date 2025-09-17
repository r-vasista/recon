from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from .models import (
    Portal, PortalCategory, MasterCategory, MasterCategoryMapping
)
from .serializers import (
    PortalSerializer, PortalSafeSerializer, PortalCategorySerializer, MasterCategorySerializer, 
    MasterCategoryMappingSerializer
)
from .utils import success_response, error_response
from .pagination import PaginationMixin


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
    """POST /api/portal-categories/"""

    def post(self, request):
        try:
            serializer = PortalCategorySerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(success_response("Category created", serializer.data), status=status.HTTP_201_CREATED)
            return Response(error_response(serializer.errors), status=status.HTTP_400_BAD_REQUEST)
        except Portal.DoesNotExist:
            return Response(error_response("Portal not found"), status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(error_response(str(e)), status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
