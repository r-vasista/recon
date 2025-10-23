from rest_framework import serializers
from .models import (
    Portal, PortalCategory, MasterCategory, MasterCategoryMapping, Group, MasterNewsPost, NewsDistribution
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
        fields = ["id", "external_id", "name", "portal_name", "parent_name", "parent_external_id"]

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


class MasterCategoryListSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterCategory
        fields = ["id", "name"]
        

class MasterCategoryMappingSerializer(serializers.ModelSerializer):
    master_category_name = serializers.CharField(source="master_category.name", read_only=True)
    portal_name = serializers.CharField(source="portal_category.portal.name", read_only=True)
    portal_category_name = serializers.CharField(source="portal_category.name", read_only=True)
    portal_id = serializers.CharField(source="portal_category.portal.id", read_only=True)

    class Meta:
        model = MasterCategoryMapping
        fields = [
            "id",
            "master_category",
            "master_category_name",
            "portal_category",
            "portal_name",
            "portal_id",
            "portal_category_name",
            "use_default_content",
            "is_default",
        ]
        
class GroupSerializer(serializers.ModelSerializer):
    master_categories = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=MasterCategory.objects.all()
    )

    class Meta:
        model = Group
        fields = ['id', 'name', 'master_categories']


class GroupListSerializer(serializers.ModelSerializer):
    master_categories = MasterCategoryListSerializer(many=True)

    class Meta:
        model = Group
        fields = ['id', 'name', 'master_categories']


class MasterNewsPostSerializer(serializers.ModelSerializer):
    post_image = serializers.ImageField(required=False, allow_null=True, use_url=True)

    class Meta:
        model = MasterNewsPost
        fields = '__all__'
        read_only_fields = ["id", "created_at", "updated_at"]


class MasterNewsPostListSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = MasterNewsPost
        fields = ['title', 'short_description', 'post_image', 'created_by', 'created_at', 'updated_at']


class NewsDistributionSerializer(serializers.ModelSerializer):
    news_post_title = serializers.CharField(source="news_post.title", read_only=True)
    portal_name = serializers.CharField(source="portal.name", read_only=True)
    master_category_name = serializers.CharField(source="master_category.name", read_only=True)
    portal_category_name = serializers.CharField(source="portal_category.name", read_only=True)
    news_post_image = serializers.SerializerMethodField()

    class Meta:
        model = NewsDistribution
        fields = "__all__"
        
    def get_news_post_image(self, obj):
        request = self.context.get("request")
        if obj.news_post.post_image and request:
            return request.build_absolute_uri(obj.news_post.post_image.url)
        return None

class NewsDistributionListSerializer(serializers.ModelSerializer):
    news_post_title = serializers.CharField(source="news_post.title", read_only=True)
    news_post_created_by = serializers.CharField(source="news_post.created_by", read_only=True)
    news_post_image = serializers.SerializerMethodField()
    portal_name = serializers.CharField(source="portal.name", read_only=True)
    master_category_name = serializers.CharField(source="master_category.name", read_only=True)
    portal_category_name = serializers.CharField(source="portal_category.name", read_only=True)
    live_url = serializers.SerializerMethodField()

    class Meta:
        model = NewsDistribution
        fields = ['id', 'news_post_title', 'portal_name', 'master_category_name', 'portal_category_name', 'status', 
                  'sent_at', 'retry_count', 'news_post_image', 'news_post_created_by', 'ai_title', 'ai_short_description',
                  'ai_content', 'ai_meta_title', 'ai_slug', 'live_url']
    
    def get_news_post_image(self, obj):
        request = self.context.get("request")
        if obj.news_post.post_image and request:
            return request.build_absolute_uri(obj.news_post.post_image.url)
        return None
    
    def get_live_url(self, obj):
        """
        Returns the live URL for the distributed news post, following the pattern:
        <portal.domain_url>/<ai_slug>
        Example: https://www.gccnews24.com/sresan-pharma-owner-arrested-after-children-die-from-toxic-syrup
        """
        if obj.portal and obj.portal.domain_url and obj.ai_slug:
            domain = obj.portal.domain_url.rstrip("/") 
            slug = obj.ai_slug.lstrip("/")
            return f"{domain}/{slug}"
        return None
