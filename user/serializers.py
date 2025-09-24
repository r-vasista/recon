from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model

from .models import (
    PortalUserMapping, UserCategoryGroupAssignment
)
from app.models import (
    Group, MasterCategory
)
from app.serializers import (
    MasterCategoryListSerializer, GroupListSerializer
)
User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email"),
            password=validated_data["password"],
        )
        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)

        # Add additional user info
        role_name = None
        if hasattr(self.user, "role") and self.user.role:  # user has UserRole relation
            role_name = self.user.role.role.name

        data.update({
            "user_id": self.user.id,
            "username": self.user.username,
            "role": role_name
        })

        return data
    
    
class PortalCheckResultSerializer(serializers.Serializer):
    portal = serializers.CharField()
    found = serializers.BooleanField()
    user_id = serializers.IntegerField(required=False, allow_null=True)
    username = serializers.CharField(required=False, allow_null=True)
    message = serializers.CharField(required=False, allow_blank=True)


class PortalUserMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortalUserMapping
        fields = '__all__'
        read_only_fields = ["id", "created_at", "updated_at"]
   
        
class PortalUserMappingListSerializer(serializers.ModelSerializer):
    portal_name = serializers.CharField(source="portal.name", read_only=True)

    class Meta:
        model = PortalUserMapping
        fields = ["id", "portal_name", "portal_user_id", "status"]


class UserAssignmentCreateSerializer(serializers.Serializer):
    username = serializers.CharField(write_only=True)
    groups = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=Group.objects.all()),
        required=False,
        allow_empty=True
    )
    master_categories = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=MasterCategory.objects.all()),
        required=False,
        allow_empty=True
    )

    def validate(self, data):
        groups = data.get("groups", [])
        master_categories = data.get("master_categories", [])

        if not groups and not master_categories:
            raise serializers.ValidationError("Either groups or master_categories must be provided.")
        if groups and master_categories:
            raise serializers.ValidationError("You cannot assign both groups and master_categories in the same request.")

        return data

    def create(self, validated_data):
        username = validated_data.pop("username")
        groups = validated_data.pop("groups", [])
        master_categories = validated_data.pop("master_categories", [])

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist.")

        assignments = []
        if groups:
            for group in groups:
                assignment, _ = UserCategoryGroupAssignment.objects.get_or_create(
                    user=user, group=group
                )
                assignments.append(assignment)
        elif master_categories:
            for category in master_categories:
                assignment, _ = UserCategoryGroupAssignment.objects.get_or_create(
                    user=user, master_category=category
                )
                assignments.append(assignment)

        return assignments

class UserAssignmentListSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.username")
    group = GroupListSerializer()
    master_category = MasterCategoryListSerializer()

    class Meta:
        model = UserCategoryGroupAssignment
        fields = ["id", "user", "group", "master_category", "created_at"]

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "is_active",
            "date_joined",
        ]