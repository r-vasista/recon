from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model

from .models import (
    PortalUserMapping
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
        data.update({
            "user_id": self.user.id,
            "username": self.user.username
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