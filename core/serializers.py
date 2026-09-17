from rest_framework import serializers
from .models import User, Business, BrandProfile, BrandAsset, MetaConnection, GeneratedPost

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
        fields = ['id', 'target_audience', 'tone_of_voice', 'brand_guidelines']
        fields = ['id', 'target_audience', 'tone_of_voice', 'brand_guidelines', 'website_url', 'company_description']

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
        fields = ['id', 'topic', 'generated_content', 'media_url', 'media_urls', 'status', 'created_at', 'published_at']
