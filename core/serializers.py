from rest_framework import serializers
from .models import User, Business, BrandProfile, BrandAsset, MetaConnection, GeneratedPost, AutoReplyLog, AutoDMLog, AdCampaign

class BusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = ['id', 'name', 'created_at']

class UserSerializer(serializers.ModelSerializer):
    business = BusinessSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'business']

class RegisterSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['email', 'password', 'business_name']
        
    def create(self, validated_data):
        business_name = validated_data.pop('business_name')
        # Create business (Tenant)
        business = Business.objects.create(name=business_name)
        # Create user associated with the business
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=validated_data['password'],
            business=business
        )
        return user

class BrandProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandProfile
        fields = ['id', 'tone_of_voice', 'target_audience', 'brand_guidelines', 'website_url', 'company_description', 'default_category', 'default_fb_objective', 'default_insta_objective', 'topics']

class BrandAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandAsset
        fields = ['id', 'asset_type', 'file', 'name', 'uploaded_at']

class MetaConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetaConnection
        fields = ['id', 'is_active', 'page_id', 'instagram_id']

class GeneratedPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedPost
        fields = ['id', 'topic', 'category', 'fb_objective', 'insta_objective', 'generated_content', 'media_url', 'media_urls', 'status', 'created_at', 'scheduled_at', 'published_at', 'published_platform']

class AutoReplyLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoReplyLog
        fields = ['id', 'platform', 'commenter_name', 'comment_text', 'reply_text', 'post_id', 'created_at']

class AutoDMLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoDMLog
        fields = ['id', 'platform', 'trigger_type', 'recipient_name', 'recipient_id', 'comment_text', 'dm_text', 'post_id', 'status', 'error_message', 'created_at']

class AdCampaignSerializer(serializers.ModelSerializer):
    post_topic = serializers.CharField(source='post.topic', read_only=True)
    post_media_url = serializers.CharField(source='post.media_url', read_only=True)
    post_content = serializers.CharField(source='post.generated_content', read_only=True)
    class Meta:
        model = AdCampaign
        fields = ['id', 'post', 'post_topic', 'post_media_url', 'post_content', 'meta_campaign_id', 'meta_adset_id', 'meta_ad_id', 'budget', 'created_at', 'campaign_type']
