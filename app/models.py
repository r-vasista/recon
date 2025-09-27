import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    is_active = models.BooleanField(default=True)
    inactivated_at = models.DateTimeField(null=True, blank=True)

    def deactivate(self):
        self.is_active = False
        self.inactivated_at = timezone.now()
        self.save()

    def activate(self):
        self.is_active = True
        self.inactivated_at = None
        self.save()

    class Meta:
        abstract = True


class Portal(BaseModel):
    """Represents an external news portal (other Django project)."""
    name = models.CharField(max_length=150, unique=True)
    base_url = models.URLField()
    api_key = models.CharField(max_length=255)
    secret_key = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class PortalCategory(BaseModel):
    """Categories belonging to a Portal."""
    portal = models.ForeignKey(Portal, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=150)
    external_id = models.CharField(max_length=100)  # category id in that portal

    class Meta:
        unique_together = ("portal", "external_id")

    def __str__(self):
        return f"{self.portal.name} - {self.name}"


class MasterCategory(BaseModel):
    """Super Admin defined category grouping across portals."""
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name


class MasterCategoryMapping(BaseModel):
    """Mapping between MasterCategory and PortalCategory."""
    master_category = models.ForeignKey(MasterCategory, on_delete=models.CASCADE, related_name="mappings")
    portal_category = models.ForeignKey(PortalCategory, on_delete=models.CASCADE, related_name="mappings")
    use_default_content = models.BooleanField(default=False, help_text="If true, send MasterNewsPost content without GPT rewrite")

    class Meta:
        unique_together = ("master_category", "portal_category")

    def __str__(self):
        return f"{self.master_category.name} -> {self.portal_category}"


class Group(BaseModel):
    """Group of master categories assigned to users."""
    name = models.CharField(max_length=150, unique=True)
    master_categories = models.ManyToManyField(MasterCategory, related_name="groups")

    def __str__(self):
        return self.name


class UserGroup(BaseModel):
    """Assigns a user to a group (1 user -> 1 group)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="user_group")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="users")

    def __str__(self):
        return f"{self.user} -> {self.group}"


class MasterNewsPost(BaseModel):
    """Main news post created inside Recon."""
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="master_news_posts")

    # Mandatory fields
    title = models.CharField(max_length=255)
    short_description = models.CharField(max_length=300)
    content = models.TextField()
    post_image = models.ImageField(upload_to="posts/%Y/%m/%d/")
    
    # Optional overrides (subset of fields in each portal's NewsPost model)
    is_active = models.BooleanField(null=True, blank=True)
    latest_news = models.BooleanField(null=True, blank=True)
    upcoming_event = models.BooleanField(null=True, blank=True)
    Head_Lines = models.BooleanField(null=True, blank=True)
    articles = models.BooleanField(null=True, blank=True)
    trending = models.BooleanField(null=True, blank=True)
    BreakingNews = models.BooleanField(null=True, blank=True)
    Event = models.BooleanField(null=True, blank=True)
    Event_date = models.DateField(null=True, blank=True)
    Event_end_date = models.DateField(null=True, blank=True)
    schedule_date = models.DateTimeField(null=True, blank=True)
    post_tag = models.TextField(null=True, blank=True)
    counter=models.PositiveIntegerField(null=True, blank=True)

    # Meta info
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class NewsDistribution(BaseModel):
    """
    Tracks distribution of a news post to each portal.
    Stores optional per-portal overrides.
    Example: user may set BreakingNews=True for Portal A,
             but leave it empty for Portal B.
    """
    news_post = models.ForeignKey(MasterNewsPost, on_delete=models.CASCADE, related_name="news_distribution")
    portal = models.ForeignKey(Portal, on_delete=models.CASCADE)
    portal_category = models.ForeignKey(PortalCategory, on_delete=models.SET_NULL, null=True, blank=True)
    group = models.ForeignKey(
        "Group", on_delete=models.SET_NULL, null=True, blank=True, related_name="news_distributions"
    )
    master_category = models.ForeignKey(
        MasterCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="news_distributions"
    )
    extra_data = models.JSONField(null=True, blank=True)
    
    ai_title = models.CharField(max_length=255, null=True, blank=True)
    ai_short_description = models.CharField(max_length=300, null=True, blank=True)
    ai_content = models.TextField(null=True, blank=True)

    # Extendable JSON for future portal-specific fields

    status = models.CharField(
        max_length=20,
        choices=(("PENDING", "Pending"), ("SUCCESS", "Success"), ("FAILED", "Failed")),
        default="PENDING"
    )
    response_message = models.TextField(null=True, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    retry_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ("news_post", "portal")

    def __str__(self):
        return f"{self.news_post.title} -> {self.portal.name}"


class PortalPrompt(models.Model):
    """
    Custom AI prompt configuration for each portal.
    If missing → fallback to default/general prompt.
    """
    portal = models.OneToOneField(Portal, on_delete=models.CASCADE, related_name="prompt")
    prompt_text = models.TextField()

    def __str__(self):
        return f"Prompt for {self.portal.name}"
