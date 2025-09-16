from rest_framework import serializers
from .models import (
    Portal, PortalCategory, MasterCategory, MasterCategoryMapping,
)

class PortalSerializer(serializers.ModelSerializer):
    """
    Serializer for creating/updating Portal.
    Includes all fields, including API/Secret keys.
    """

    class Meta:
        model = Portal
        fields = ["id", "name", "base_url", "api_key", "secret_key"]

    # def validate_name(self, value):
    #     if Portal.objects.filter(name=value).exclude(id=self.instance.id if self.instance else None).exists():
    #         raise serializers.ValidationError("A portal with this name already exists.")
    #     return value


class PortalSafeSerializer(serializers.ModelSerializer):
    """
    Safe serializer for listing and retrieving portals.
    Hides sensitive fields (api_key, secret_key).
    """

    class Meta:
        model = Portal
        fields = ["id", "name", "base_url"]


class PortalCategorySerializer(serializers.ModelSerializer):
    portal_name = serializers.CharField(write_only=True)

    class Meta:
        model = PortalCategory
        fields = ["id", "portal_name", "external_id", "name"]

    def create(self, validated_data):
        portal_name = validated_data.pop("portal_name")
        portal = Portal.objects.get(name=portal_name)
        return PortalCategory.objects.create(portal=portal, **validated_data)

    def update(self, instance, validated_data):
        if "portal_name" in validated_data:
            portal_name = validated_data.pop("portal_name")
            portal = Portal.objects.get(name=portal_name)
            instance.portal = portal
        return super().update(instance, validated_data)


class MasterCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterCategory
        fields = ["id", "name", "description", "created_at", "updated_at"]


class MasterCategoryMappingSerializer(serializers.ModelSerializer):
    master_category_name = serializers.CharField(source="master_category.name", read_only=True)
    portal_name = serializers.CharField(source="portal_category.portal.name", read_only=True)
    portal_category_name = serializers.CharField(source="portal_category.name", read_only=True)

    class Meta:
        model = MasterCategoryMapping
        fields = ["id", "master_category", "master_category_name", "portal_category", "portal_name", "portal_category_name"]
