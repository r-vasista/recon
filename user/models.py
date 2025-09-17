import uuid
from django.db import models
from django.contrib.auth import get_user_model
from app.models import BaseModel, Portal

User = get_user_model()


class PortalUserMapping(BaseModel):
    """
    Maps a Recon user to their account in a specific portal.
    - When user logs in, Recon checks each portal by username.
    - If found, map immediately.
    - If not found, mark status=PENDING until user/admin resolves it.
    """

    STATUS_CHOICES = (
        ("MATCHED", "Matched"),   # Found a user in portal with same username
        ("PENDING", "Pending"),   # User not found, waiting for manual action
        ("MISMATCH", "Mismatch"), # Username exists but different (needs update)
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="portal_user_mappings")
    portal = models.ForeignKey(Portal, on_delete=models.CASCADE, related_name="user_mappings")

    # Portal-side reference
    portal_user_id = models.CharField(max_length=100, null=True, blank=True)  # ID from portal DB
    portal_username = models.CharField(max_length=150, null=True, blank=True) # Username in portal

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    notes = models.TextField(null=True, blank=True)  # extra info like error msg

    class Meta:
        unique_together = ("user", "portal")

    def __str__(self):
        return f"{self.user.username} -> {self.portal.name} ({self.status})"


