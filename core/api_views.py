from rest_framework import generics, status, views
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .models import BrandProfile, GeneratedPost, MetaConnection
from .serializers import RegisterSerializer, BrandProfileSerializer, GeneratedPostSerializer
from . import ai_service
from . import meta_service

User = get_user_model()

class CurrentUserView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "business_name": user.business.name if user.business else None
        })

class LogoutView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)
        except Exception:
            return Response({"error": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

class BrandProfileView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        business = request.user.business
        if not business:
            return Response({"error": "User is not associated with any business."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            profile, _ = BrandProfile.objects.get_or_create(business=business)
            serializer = BrandProfileSerializer(profile)
            return Response(serializer.data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        business = request.user.business
        if not business:
            return Response({"error": "User is not associated with any business."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            profile, _ = BrandProfile.objects.get_or_create(business=business)
            serializer = BrandProfileSerializer(profile, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class GeneratePostView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        topic = request.data.get('topic')
        custom_tone = request.data.get('tone')
        if not topic:
            return Response({'error': 'Topic is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        business = request.user.business
        profile = BrandProfile.objects.filter(business=business).first()
        
        # Build prompt using Brand Profile info
        brand_info = ""
        if profile:
            tone = custom_tone if custom_tone else profile.tone_of_voice
            brand_info = f"Tone of voice: {tone}. Target Audience: {profile.target_audience}. Guidelines: {profile.brand_guidelines}."
        
        prompt = f"Generate a highly engaging Facebook post about: {topic}. {brand_info} Keep it professional yet engaging, and include suitable emojis and hashtags."
        
        try:
            content = ai_service.generate_post_content(prompt)
            
            # Save the generated post to review
            post = GeneratedPost.objects.create(
                business=business,
                topic=topic,
                generated_content=content,
                status='DRAFT'
            )
            
            serializer = GeneratedPostSerializer(post)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PostListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = GeneratedPostSerializer

    def get_queryset(self):
        qs = GeneratedPost.objects.filter(business=self.request.user.business).order_by('-created_at')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(topic__icontains=search)
        return qs

class GetMetaAuthUrlView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        try:
            auth_url = meta_service.get_authorization_url()
            if not auth_url:
                return Response({"error": "Meta App credentials are not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            return Response({'auth_url': auth_url})
        except Exception as e:
            return Response({"error": f"Failed to generate Meta auth URL: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MetaCallbackAPIView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        code = request.data.get('code')
        if not code:
            return Response({"error": "No authorization code provided"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Exchange code for access token
            access_token = meta_service.exchange_code_for_token(code)
            
            # Save token to business
            business = request.user.business
            connection, _ = MetaConnection.objects.get_or_create(business=business)
            connection.access_token = access_token
            connection.is_active = True
            connection.save()
            
            return Response({"message": "Meta successfully connected!"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MetaStatusView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        business = request.user.business
        connection = MetaConnection.objects.filter(business=business).first()
        if not connection or not connection.access_token:
            return Response({"is_connected": False})
        return Response({
            "is_connected": connection.is_active,
            "page_id": connection.page_id,
            "instagram_id": connection.instagram_id
        })

class MetaPagesView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        business = request.user.business
        connection = MetaConnection.objects.filter(business=business, is_active=True).first()
        if not connection or not connection.access_token:
            return Response({"error": "Meta not connected"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            pages = meta_service.fetch_user_pages(connection.access_token)
            return Response({"pages": pages})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        page_id = request.data.get('page_id')
        if not page_id:
            return Response({"error": "page_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        business = request.user.business
        connection = MetaConnection.objects.filter(business=business, is_active=True).first()
        if not connection:
            return Response({"error": "Meta not connected"}, status=status.HTTP_400_BAD_REQUEST)
            
        connection.page_id = page_id
        connection.save()
        return Response({"message": "Page successfully selected"})

class DashboardStatsView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        business = request.user.business
        if not business:
            return Response({"error": "User is not associated with any business."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            posts_generated = GeneratedPost.objects.filter(business=business).count()
            pages_connected = 0
            
            connection = MetaConnection.objects.filter(business=business, is_active=True).first()
            if connection and connection.access_token:
                pages_connected = 1 if connection.page_id else 0 
                
            return Response({
                "pages_connected": pages_connected,
                "posts_generated": posts_generated
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PostDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = GeneratedPostSerializer

    def get_queryset(self):
        return GeneratedPost.objects.filter(business=self.request.user.business)

class PublishPostView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, pk):
        business = request.user.business
        try:
            post = GeneratedPost.objects.get(pk=pk, business=business)
        except GeneratedPost.DoesNotExist:
            return Response({"error": "Post not found"}, status=status.HTTP_404_NOT_FOUND)
            
        connection = MetaConnection.objects.filter(business=business, is_active=True).first()
        if not connection or not connection.access_token:
            return Response({"error": "Meta account not connected"}, status=status.HTTP_400_BAD_REQUEST)
            
        if not connection.page_id:
            return Response({"error": "No Facebook Page selected for publishing"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Call Meta API to publish
            meta_service.publish_to_page(
                page_id=connection.page_id,
                page_access_token=connection.access_token,
                message=post.generated_content,
                image_url=post.media_url
            )
            
            post.status = 'PUBLISHED'
            post.save()
            
            return Response({"message": "Post successfully published to Facebook!"})
        except Exception as e:
            post.status = 'FAILED'
            post.save()
            return Response({"error": f"Publishing failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
