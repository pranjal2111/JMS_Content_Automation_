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
    website_url = models.URLField(blank=True, null=True)
    company_description = models.TextField(blank=True, help_text="Core services, background, or brochure text")

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
    media_urls = models.JSONField(default=list, blank=True, help_text="List of image URLs for carousel posts")
    
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
    published_platform = models.CharField(max_length=50, blank=True, null=True)

class AutoReplySettings(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='auto_reply_settings')
    reply_text = models.TextField(help_text="The text to auto-reply to comments on Facebook and Instagram.", blank=True)
    is_active = models.BooleanField(default=False)

class AutoReplyLog(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='auto_reply_logs')
    platform = models.CharField(max_length=50, help_text="facebook or instagram")
    commenter_name = models.CharField(max_length=255, blank=True, null=True)
    comment_text = models.TextField(blank=True, null=True)
    reply_text = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class AdCampaign(models.Model):
    post = models.OneToOneField(GeneratedPost, on_delete=models.CASCADE, related_name='ad_campaign')
    meta_campaign_id = models.CharField(max_length=255, blank=True, null=True)
    meta_adset_id = models.CharField(max_length=255, blank=True, null=True)
    meta_ad_id = models.CharField(max_length=255, blank=True, null=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2, default=10.00, help_text="Daily budget in account currency")
    status = models.CharField(max_length=50, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

from django.db.models.signals import post_delete
from django.dispatch import receiver

@receiver(post_delete, sender=User)
def delete_related_business(sender, instance, **kwargs):
    """
    When a User is deleted, delete their associated Business if no other users are attached to it.
    Since Business is the parent of all other data (Posts, MetaConnection, BrandProfile) 
    with on_delete=models.CASCADE, this will automatically delete all related data.
    """
    if instance.business:
        # Check if this was the last user for this business
        if not User.objects.filter(business=instance.business).exists():
            instance.business.delete()
