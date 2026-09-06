from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid

# 1. Tenant/Business Model
class Business(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

# 2. Custom User Model linked to Business
class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, null=True, blank=True, related_name='users')
    
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('EDITOR', 'Editor'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='ADMIN')

    def __str__(self):
        return self.username

# 3. Brand Knowledge Base
class BrandProfile(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='brand_profile')
    tone_of_voice = models.TextField(blank=True, help_text="E.g., Professional, Playful, Authoritative")
    target_audience = models.TextField(blank=True)
    brand_guidelines = models.TextField(blank=True)

class BrandAsset(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='assets')
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='brand_assets/')
    asset_type = models.CharField(max_length=50, choices=[('LOGO', 'Logo'), ('DOCUMENT', 'Document'), ('IMAGE', 'Image')])
    uploaded_at = models.DateTimeField(auto_now_add=True)

# 4. Meta Integrations
class MetaConnection(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='meta_connection')
    access_token = models.CharField(max_length=500)
    page_id = models.CharField(max_length=255, blank=True, null=True)
    instagram_id = models.CharField(max_length=255, blank=True, null=True)
    ad_account_id = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)

# 5. Content Generation
class GeneratedPost(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='posts')
    topic = models.CharField(max_length=255)
    generated_content = models.TextField()
    media_url = models.URLField(blank=True, null=True)
    
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('REVIEW', 'Pending Review'),
        ('APPROVED', 'Approved'),
        ('PUBLISHED', 'Published'),
        ('FAILED', 'Failed')
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
