import concurrent.futures
import re
from rest_framework import generics, status, views
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .models import BrandProfile, GeneratedPost, MetaConnection, BrandAsset, AutoReplyLog, AutoDMLog, AdCampaign
from .serializers import RegisterSerializer, BrandProfileSerializer, GeneratedPostSerializer
from . import ai_service
from . import meta_service
from .knowledge_extractor import extract_text_from_url, extract_text_from_pdf

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

from .serializers import BrandAssetSerializer
from rest_framework.parsers import MultiPartParser, FormParser

class BrandAssetView(views.APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request):
        business = request.user.business
        assets = BrandAsset.objects.filter(business=business)
        serializer = BrandAssetSerializer(assets, many=True)
        return Response(serializer.data)

    def post(self, request):
        business = request.user.business
        serializer = BrandAssetSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(business=business)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class BrandAssetDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = BrandAssetSerializer

    def get_queryset(self):
        return BrandAsset.objects.filter(business=self.request.user.business)

class GeneratePostView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        topic = request.data.get('topic')
        custom_tone = request.data.get('tone')
        category = request.data.get('category')
        fb_objective = request.data.get('fb_objective')
        insta_objective = request.data.get('insta_objective')
        
        business = request.user.business
        profile = BrandProfile.objects.filter(business=business).first()
        
        if not topic and profile and profile.topics:
            topic = profile.topics
            
        if not topic:
            return Response({'error': 'Topic is required. Configure it in Brand Setup or provide it directly.'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Build prompt using Brand Profile info
        brand_info = ""
        liked_posts_info = ""
        tone = custom_tone
        if profile:
            if not tone:
                tone = profile.tone_of_voice
            if not category:
                category = profile.default_category
            if not fb_objective:
                fb_objective = profile.default_fb_objective
            if not insta_objective:
                insta_objective = profile.default_insta_objective

            website_data = ""
            if profile.website_url:
                website_data = extract_text_from_url(profile.website_url)
                
            pdf_data = ""
            documents = BrandAsset.objects.filter(business=business, asset_type='DOCUMENT')
            for doc in documents:
                if doc.file and doc.file.path.endswith('.pdf'):
                    pdf_data += extract_text_from_pdf(doc.file.path) + "\n\n"
            
            if profile.liked_posts:
                liked_posts_info = f"\n\nCRITICAL: The user has previously approved these posts. Please analyze their style, formatting, and tone, and ensure your generated options strictly match this preferred style:\n{profile.liked_posts[-5000:]}\n"
                
            brand_info = (
                f"\nBrand Context:\n"
                f"- Tone of Voice: {tone or 'Professional'}\n"
                f"- Target Audience: {profile.target_audience}\n"
                f"- Brand Guidelines: {profile.brand_guidelines}\n"
                f"- Company Description: {profile.company_description}\n"
                f"- Website Content: {website_data}\n"
                f"- Uploaded Document Content: {pdf_data[:10000]}\n"
                f"{liked_posts_info}"
            )
        
        category = category or 'General'
        fb_objective = fb_objective or 'Awareness'
        insta_objective = insta_objective or 'Brand Awareness'
        
        import uuid
        prompt = (
            "You are an expert social media strategist and world-class copywriter.\n"
            f"Your task is to craft a highly engaging social media post about: '{topic}'.\n\n"
            "=== STRATEGIC DIRECTION ===\n"
            f"Ã¢â‚¬Â¢ Content Category: {category}\n"
            f"Ã¢â‚¬Â¢ Facebook Objective: {fb_objective}\n"
            f"Ã¢â‚¬Â¢ Instagram Objective: {insta_objective}\n"
            f"{brand_info}\n\n"
            "=== GENERATION INSTRUCTIONS ===\n"
            "1. Generate EXACTLY 5 completely distinct, high-performing variations of the post.\n"
            "2. Structure each post with a thumb-stopping hook, engaging body copy, and a clear Call-to-Action (CTA).\n"
            "3. Ensure the copy sounds 100% human, authentic, and conversational. STRICTLY AVOID generic AI buzzwords (e.g., 'unlock', 'delve', 'elevate', 'supercharge').\n"
            "4. Adapt the messaging to drive the specified Facebook and Instagram objectives effectively.\n"
            "5. Maintain absolute adherence to the brand's tone of voice and guidelines.\n"
            "6. Seamlessly integrate 2-4 well-placed emojis and 3-5 highly relevant hashtags.\n"
            f"7. CRITICAL: THIS IS A NEW BATCH (ID: {uuid.uuid4()}). Provide fresh, highly creative angles that stand out from typical corporate posts.\n\n"
            "=== OUTPUT FORMAT ===\n"
            "- Separate each variation using EXACTLY the string '---OPTION---' on its own line.\n"
            "- Do NOT include labels like 'Option 1:', introductory text, or closing remarks. ONLY output the post text."
        )
        
        try:
            content_raw = ai_service.generate_post_content(prompt)
            
            if not content_raw:
                raise ValueError("AI failed to generate content (possibly blocked by content filters).")

            # Split by delimiter
            options = [opt.strip() for opt in content_raw.split('---OPTION---') if opt.strip()]
            
            # Fallback if AI didn't follow formatting
            if len(options) < 2:
                # Try splitting by "Option X:"
                alt_options = re.split(r'Option \d+:', content_raw)
                options = [opt.strip() for opt in alt_options if opt.strip()]
            
            if not options:
                options = [content_raw]
            
            # Cap at 5
            options = options[:5]
            
            # Generate unique images for each option concurrently
            logo_asset = BrandAsset.objects.filter(business=business, asset_type='LOGO').first()
            logo_path = logo_asset.file.path if logo_asset and logo_asset.file else None
            
            def gen_media(args):
                idx, opt_text = args
                # Generate video for odd indices, image for even indices
                if idx % 2 != 0:
                    try:
                        video_url = ai_service.generate_video_with_gemini(opt_text)
                        if video_url:
                            return video_url
                    except Exception as e:
                        print(f"Video generation failed: {e}")
                    # Fallback to image if video fails or returns None
                    return ai_service.generate_image_for_post(
                        opt_text, 
                        brand_name=business.name if business else None, 
                        logo_path=logo_path,
                        website_url=profile.website_url if profile else None
                    )
                else:
                    return ai_service.generate_image_for_post(
                        opt_text, 
                        brand_name=business.name if business else None, 
                        logo_path=logo_path,
                        website_url=profile.website_url if profile else None
                    )
                
            media_urls = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                # Map the function over all 5 options
                args_list = list(enumerate(options))
                results = executor.map(gen_media, args_list)
                media_urls = list(results)
            
            return Response({
                'topic': topic,
                'category': category,
                'fb_objective': fb_objective,
                'insta_objective': insta_objective,
                'options': options,
                'media_urls': media_urls
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ApproveAndScheduleView(views.APIView):
    permission_classes = (IsAuthenticated,)
    
    def post(self, request):
        topic = request.data.get('topic')
        category = request.data.get('category')
        fb_objective = request.data.get('fb_objective')
        insta_objective = request.data.get('insta_objective')
        content = request.data.get('content')
        media_url = request.data.get('media_url')
        scheduled_at = request.data.get('scheduled_at')
        published_platform = request.data.get('published_platform')
        
        if not content:
            return Response({'error': 'Content is required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        business = request.user.business
        
        # Save the approved post
        post = GeneratedPost.objects.create(
            business=business,
            topic=topic,
            category=category,
            fb_objective=fb_objective,
            insta_objective=insta_objective,
            generated_content=content,
            media_url=media_url,
            status='APPROVED',
            scheduled_at=scheduled_at,
            published_platform=published_platform
        )
        
        # Add to liked_posts in BrandProfile for AI learning
        profile, _ = BrandProfile.objects.get_or_create(business=business)
        
        separator = "\n\n---APPROVED POST---\n\n"
        if profile.liked_posts:
            profile.liked_posts += f"{separator}{content}"
        else:
            profile.liked_posts = content
            
        # Keep only the last 10000 characters to prevent overflow
        profile.liked_posts = profile.liked_posts[-10000:]
        profile.save()
        
        serializer = GeneratedPostSerializer(post)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class PostListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = GeneratedPostSerializer

    def get_queryset(self):
        qs = GeneratedPost.objects.filter(business=self.request.user.business).exclude(status='AD_SCRATCH').order_by('-created_at')
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
            "instagram_id": connection.instagram_id,
            "ad_account_id": connection.ad_account_id
        })

class MetaAdAccountsView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        business = request.user.business
        connection = MetaConnection.objects.filter(business=business, is_active=True).first()
        if not connection or not connection.access_token:
            return Response({"error": "Meta not connected"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            ad_accounts = meta_service.fetch_user_ad_accounts(connection.access_token)
            return Response({"ad_accounts": ad_accounts})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        ad_account_id = request.data.get('ad_account_id')
        if not ad_account_id:
            return Response({"error": "ad_account_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        business = request.user.business
        connection = MetaConnection.objects.filter(business=business, is_active=True).first()
        if not connection:
            return Response({"error": "Meta not connected"}, status=status.HTTP_400_BAD_REQUEST)
            
        connection.ad_account_id = ad_account_id
        connection.save()
        return Response({"message": "Ad Account successfully selected"})

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
        
        # Automatically fetch and save the linked Instagram ID
        try:
            pages = meta_service.fetch_user_pages(connection.access_token)
            for page in pages:
                if page.get("id") == page_id:
                    ig_account = page.get("instagram_business_account")
                    if ig_account and ig_account.get("id"):
                        connection.instagram_id = ig_account.get("id")
                    else:
                        connection.instagram_id = "" # Clear it if none exists
                    break
        except Exception:
            pass # Non-critical error
            
        # Subscribe the app to the page for webhooks
        try:
            meta_service.subscribe_app_to_page(page_id, connection.access_token)
        except Exception as e:
            print(f"Failed to subscribe app to page: {str(e)}")
            
        connection.save()
        return Response({"message": "Page successfully selected"})

class DashboardStatsView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        business = request.user.business
        if not business:
            return Response({"error": "User is not associated with any business."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            posts_generated = GeneratedPost.objects.filter(business=business).exclude(status='AD_SCRATCH').count()
            published_posts = GeneratedPost.objects.filter(business=business, status='PUBLISHED').count()
            scheduled_posts = GeneratedPost.objects.filter(business=business, scheduled_at__isnull=False).exclude(status='PUBLISHED').count()
            
            auto_replies_sent = AutoReplyLog.objects.filter(business=business).count()
            auto_dms_sent = AutoDMLog.objects.filter(business=business, status='sent').count()
            ad_campaigns_total = AdCampaign.objects.filter(post__business=business).count()
            
            pages_connected = 0
            
            connection = MetaConnection.objects.filter(business=business, is_active=True).first()
            if connection and connection.access_token:
                pages_connected = 1 if connection.page_id else 0 
                
            # Fetch Recent Activity
            recent_activity = []
            
            latest_posts = GeneratedPost.objects.filter(business=business).exclude(status='AD_SCRATCH').order_by('-created_at')[:5]
            for p in latest_posts:
                if p.status == 'PUBLISHED':
                    title = f"Published Post: {p.topic}"
                elif p.scheduled_at:
                    title = f"Scheduled Post: {p.topic}"
                else:
                    title = f"Generated Post: {p.topic}"
                    
                recent_activity.append({
                    "id": f"post_{p.id}",
                    "title": title,
                    "date": p.created_at,
                    "type": "POST"
                })
                
            latest_ads = AdCampaign.objects.filter(post__business=business).order_by('-created_at')[:5]
            for a in latest_ads:
                recent_activity.append({
                    "id": f"ad_{a.id}",
                    "title": f"Launched Ad: {a.post.topic}",
                    "date": a.created_at,
                    "type": "AD"
                })
                
            recent_activity = sorted(recent_activity, key=lambda x: x['date'], reverse=True)[:6]

            return Response({
                "posts_generated": posts_generated,
                "published_posts": published_posts,
                "scheduled_posts": scheduled_posts,
                "auto_replies_sent": auto_replies_sent,
                "auto_dms_sent": auto_dms_sent,
                "ad_campaigns_total": ad_campaigns_total,
                "pages_connected": pages_connected,
                "recent_activity": recent_activity
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
        platform = request.data.get('platform', 'facebook') # 'facebook' or 'instagram'

        try:
            post = GeneratedPost.objects.get(pk=pk, business=business)
        except GeneratedPost.DoesNotExist:
            return Response({"error": "Post not found"}, status=status.HTTP_404_NOT_FOUND)
            
        connection = MetaConnection.objects.filter(business=business, is_active=True).first()
        if not connection or not connection.access_token:
            return Response({"error": "Meta account not connected"}, status=status.HTTP_400_BAD_REQUEST)
            
            
        try:
            images_to_post = post.media_urls if post.media_urls else post.media_url
            
            def make_public_url(url):
                if not url: return url
                if url.startswith('http'): return url
                
                abs_url = request.build_absolute_uri(url)
                
                # Meta cannot download from localhost. Try to construct the dev tunnel URL for port 8000.
                if '127.0.0.1' in abs_url or 'localhost' in abs_url:
                    import os
                    redirect_uri = os.environ.get('META_REDIRECT_URI', '')
                    if 'devtunnels.ms' in redirect_uri:
                        from urllib.parse import urlparse
                        host = urlparse(redirect_uri).netloc
                        host = host.replace('-5173.', '-8000.')
                        return f"https://{host}{url}"
                return abs_url
                
            if isinstance(images_to_post, list):
                images_to_post = [make_public_url(img) for img in images_to_post]
            else:
                images_to_post = make_public_url(images_to_post)
            
            responses = []
            if platform in ('facebook', 'both'):
                if not connection.page_id:
                    return Response({"error": "No Facebook Page selected for publishing"}, status=status.HTTP_400_BAD_REQUEST)
                fb_res = meta_service.publish_to_page(
                    page_id=connection.page_id,
                    user_access_token=connection.access_token,
                    message=post.generated_content,
                    image_urls=images_to_post
                )
                responses.append(fb_res)
                
            if platform in ('instagram', 'both'):
                if not connection.instagram_id:
                    return Response({"error": "No Instagram account selected for publishing"}, status=status.HTTP_400_BAD_REQUEST)
                if not images_to_post:
                    return Response({"error": "Instagram requires an image. Text-only posts are not supported."}, status=status.HTTP_400_BAD_REQUEST)
                
                ig_res = meta_service.publish_to_instagram(
                    ig_user_id=connection.instagram_id,
                    access_token=connection.access_token,
                    image_url=images_to_post[0] if isinstance(images_to_post, list) else images_to_post,
                    caption=post.generated_content
                )
                responses.append(ig_res)
                
            # If any request failed
            for response_data in responses:
                if isinstance(response_data, dict) and 'error' in response_data:
                    post.status = 'FAILED'
                    post.save()
                    
                    # Facebook sometimes nests errors like {'error': {'error': {'message': '...'}}}
                    error_obj = response_data['error']
                    if isinstance(error_obj, dict) and 'error' in error_obj:
                        error_obj = error_obj['error']
                        
                    error_msg = error_obj.get('message', 'Unknown error') if isinstance(error_obj, dict) else str(error_obj)
                    return Response({"error": f"{platform.capitalize()} Error: {error_msg}"}, status=status.HTTP_400_BAD_REQUEST)
            
            post.status = 'PUBLISHED'
            post.published_platform = platform
            post.save()
            
            return Response({
                "message": f"Post successfully published to {platform.capitalize()}!", 
                f"{platform}_post_id": response_data.get('id')
            })
        except Exception as e:
            post.status = 'FAILED'
            post.save()
            return Response({"error": f"Publishing failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from .models import AutoReplySettings, AdCampaign

class AutoReplySettingsView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        business = request.user.business
        settings, _ = AutoReplySettings.objects.get_or_create(business=business)
        return Response({
            "reply_text": settings.reply_text,
            "is_active": settings.is_active,
            "fb_reply_text": settings.fb_reply_text,
            "fb_auto_reply_active": settings.fb_auto_reply_active,
            "ig_reply_text": settings.ig_reply_text,
            "ig_auto_reply_active": settings.ig_auto_reply_active,
            "fb_dm_text": settings.fb_dm_text,
            "fb_dm_on_like_active": settings.fb_dm_on_like_active,
            "ig_dm_text": settings.ig_dm_text,
            "ig_dm_on_like_active": settings.ig_dm_on_like_active,
        })

    def post(self, request):
        business = request.user.business
        settings, _ = AutoReplySettings.objects.get_or_create(business=business)
        settings.reply_text = request.data.get('reply_text', settings.reply_text)
        settings.is_active = request.data.get('is_active', settings.is_active)
        settings.fb_reply_text = request.data.get('fb_reply_text', settings.fb_reply_text)
        settings.fb_auto_reply_active = request.data.get('fb_auto_reply_active', settings.fb_auto_reply_active)
        settings.ig_reply_text = request.data.get('ig_reply_text', settings.ig_reply_text)
        settings.ig_auto_reply_active = request.data.get('ig_auto_reply_active', settings.ig_auto_reply_active)
        settings.fb_dm_text = request.data.get('fb_dm_text', settings.fb_dm_text)
        settings.fb_dm_on_like_active = request.data.get('fb_dm_on_like_active', settings.fb_dm_on_like_active)
        settings.ig_dm_text = request.data.get('ig_dm_text', settings.ig_dm_text)
        settings.ig_dm_on_like_active = request.data.get('ig_dm_on_like_active', settings.ig_dm_on_like_active)
        settings.save()
        return Response({"message": "Settings saved successfully"})

class CreateAdView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, pk):
        business = request.user.business
        
        try:
            post = GeneratedPost.objects.get(pk=pk, business=business)
        except GeneratedPost.DoesNotExist:
            return Response({"error": "Post not found"}, status=status.HTTP_404_NOT_FOUND)
            
        connection = MetaConnection.objects.filter(business=business, is_active=True).first()
        if not connection or not connection.ad_account_id:
            return Response({"error": "No Ad Account connected"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Get dynamic payload from wizard, with fallbacks
        budget = request.data.get('budget', 10.00)
        campaign_name = request.data.get('campaign_name', f"Campaign: {post.topic}")
        objective = request.data.get('objective', 'OUTCOME_ENGAGEMENT')
        age_min = request.data.get('age_min', 18)
        age_max = request.data.get('age_max', 65)
        genders = request.data.get('genders', []) # empty means all
        countries = request.data.get('countries', ['IN'])
        website_url = request.data.get('website_url', 'https://example.com')
        campaign_status = request.data.get('status', 'PAUSED')
        call_to_action = request.data.get('call_to_action', 'LEARN_MORE')
        
        # Build targeting object
        targeting = {
            "geo_locations": {"countries": countries},
            "age_min": int(age_min),
            "age_max": int(age_max)
        }
        if genders:
            targeting["genders"] = genders

        try:
            # 1. Create Campaign
            camp_res = meta_service.create_ad_campaign(connection.ad_account_id, campaign_name, connection.access_token, objective=objective, status=campaign_status)
            if 'error' in camp_res: raise Exception(camp_res['error'])
            camp_id = camp_res['id']

            # 2. Create Ad Set
            adset_res = meta_service.create_ad_set(connection.ad_account_id, connection.access_token, camp_id, f"AdSet: {post.topic}", float(budget), targeting=targeting, status=campaign_status)
            if 'error' in adset_res: raise Exception(adset_res['error'])
            adset_id = adset_res['id']
            
            # 3. Upload Image or Video
            image_url = post.media_urls[0] if post.media_urls else post.media_url
            if image_url and not image_url.startswith('http'):
                image_url = request.build_absolute_uri(image_url)
                
            image_hash = None
            video_id = None
            clean_url = image_url.lower().split('?')[0]
            if clean_url.endswith(('.mp4', '.mov', '.webm')):
                vid_res = meta_service.upload_ad_video(connection.ad_account_id, connection.access_token, image_url)
                if 'error' in vid_res: raise Exception(vid_res['error'])
                video_id = vid_res['id']
                # Upload a default thumbnail for video to get image_hash
                fallback_thumb = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ac/No_image_available.svg/1024px-No_image_available.svg.png"
                
                logo_asset = BrandAsset.objects.filter(business=business, asset_type='LOGO').first()
                if logo_asset and logo_asset.file:
                    fallback_thumb = request.build_absolute_uri(logo_asset.file.url)
                    if '127.0.0.1' in fallback_thumb or 'localhost' in fallback_thumb:
                        import os
                        redirect_uri = os.environ.get('META_REDIRECT_URI', '')
                        if 'devtunnels.ms' in redirect_uri:
                            from urllib.parse import urlparse
                            host = urlparse(redirect_uri).netloc
                            host = host.replace('-5173.', '-8000.')
                            fallback_thumb = f"https://{host}{logo_asset.file.url}"

                img_res = meta_service.upload_ad_image(connection.ad_account_id, connection.access_token, fallback_thumb)
                if 'error' not in img_res and 'images' in img_res:
                    image_hash = img_res['images']['image.jpg']['hash']
            else:
                img_res = meta_service.upload_ad_image(connection.ad_account_id, connection.access_token, image_url)
                if 'error' in img_res: raise Exception(img_res['error'])
                image_hash = img_res['images']['image.jpg']['hash']
            
            # 4. Create Creative
            creative_res = meta_service.create_ad_creative(connection.ad_account_id, connection.access_token, connection.page_id, post.generated_content, website_url, image_hash=image_hash, video_id=video_id, call_to_action_type=call_to_action, video_thumbnail_url=fallback_thumb if video_id else None)
            if 'error' in creative_res: raise Exception(creative_res['error'])
            creative_id = creative_res['id']
            
            # 5. Create Ad
            ad_res = meta_service.create_ad(connection.ad_account_id, connection.access_token, adset_id, creative_id, f"Ad: {post.topic}", status=campaign_status)
            if 'error' in ad_res: raise Exception(ad_res['error'])
            ad_id = ad_res['id']

            AdCampaign.objects.create(
                post=post, meta_campaign_id=camp_id, meta_adset_id=adset_id, meta_ad_id=ad_id, budget=budget
            )
            return Response({"message": "Ad Campaign created successfully in PAUSED state."})
            
        except Exception as e:
            return Response({"error": f"Ad creation failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from django.conf import settings
from django.http import HttpResponse

class MetaWebhookView(views.APIView):
    permission_classes = (AllowAny,) # Webhooks don't use JWT

    def get(self, request):
        # Verification endpoint
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        # In production, use settings.META_WEBHOOK_TOKEN
        if mode == 'subscribe' and token == "1234": 
            return HttpResponse(challenge, status=200)
        return HttpResponse('Error, wrong validation token', status=403)

    def post(self, request):
        # Process incoming webhook events
        data = request.data
        if data.get("object") in ["page", "instagram"]:
            for entry in data.get("entry", []):
                target_id = entry.get("id")  # This is either page_id or instagram_id
                for change in entry.get("changes", []):
                    field = change.get("field")
                    value = change.get("value", {})
                    if field in ["feed", "comments"]:
                        
                        # Check if it's a new comment
                        is_page_comment = value.get("item") == "comment" and value.get("verb") == "add"
                        is_ig_comment = field == "comments"
                        
                        if is_page_comment or is_ig_comment:
                            comment_id = value.get("comment_id") or value.get("id")
                            sender_id = value.get("from", {}).get("id")
                            
                            # Prevent infinite loop by not replying to our own page's comments
                            if sender_id == target_id:
                                continue
                                
                            if comment_id:
                                # Find connection matching this page or IG account
                                from .models import MetaConnection, AutoReplySettings
                                from django.db.models import Q
                                
                                connection = MetaConnection.objects.filter(
                                    Q(page_id=target_id) | Q(instagram_id=target_id), 
                                    is_active=True
                                ).first()
                                
                                if connection:
                                    ar_settings = AutoReplySettings.objects.filter(business=connection.business).first()
                                    if ar_settings:
                                        # Use platform-specific reply text and active toggle
                                        if is_ig_comment:
                                            reply_active = ar_settings.ig_auto_reply_active
                                            reply_msg = ar_settings.ig_reply_text
                                        else:
                                            reply_active = ar_settings.fb_auto_reply_active
                                            reply_msg = ar_settings.fb_reply_text
                                        
                                        # Fallback to legacy fields if new fields are empty
                                        if not reply_msg and ar_settings.reply_text:
                                            reply_msg = ar_settings.reply_text
                                            reply_active = ar_settings.is_active
                                        
                                        if reply_active and reply_msg:
                                            from . import meta_service
                                            # Send Public Reply
                                            res = meta_service.send_comment_reply(comment_id, reply_msg, connection.access_token, connection.page_id, is_ig_comment)
                                            
                                            # Send Private DM Reply
                                            if is_ig_comment:
                                                dm_res = meta_service.send_instagram_private_reply(comment_id, reply_msg, connection.instagram_id, connection.access_token, connection.page_id)
                                            else:
                                                dm_res = meta_service.send_facebook_private_reply(comment_id, reply_msg, connection.page_id, connection.access_token)
                                        
                                            # Log the auto-reply (and DM)
                                            if not res.get("error"):
                                                from .models import AutoReplyLog, AutoDMLog
                                            
                                                # Facebook uses 'name', Instagram uses 'username'
                                                from_data = value.get("from", {})
                                                commenter_name = from_data.get("username") if is_ig_comment else from_data.get("name")
                                                if not commenter_name:
                                                    commenter_name = "Unknown"
                                                
                                                comment_text = value.get("message", "")
                                                if not comment_text and is_ig_comment:
                                                    comment_text = value.get("text", "")
                                                
                                                # Check for attachments (stickers, gifs, photos)
                                                attachment = value.get("photo") or value.get("video") or value.get("link")
                                                if not attachment and "attachment" in value:
                                                    attachment = value.get("attachment", {}).get("url")
                                                    
                                                if attachment:
                                                    if comment_text:
                                                        comment_text += f" [MEDIA:{attachment}]"
                                                    else:
                                                        comment_text = f"[MEDIA:{attachment}]"
                                            
                                                platform = "instagram" if is_ig_comment else "facebook"
                                                
                                                # Extract post_id correctly for Instagram vs Facebook
                                                if is_ig_comment:
                                                    post_id_val = value.get("media", {}).get("id", "")
                                                else:
                                                    post_id_val = value.get("post_id", "")
                                                    
                                                AutoReplyLog.objects.create(
                                                    business=connection.business,
                                                    platform=platform,
                                                    commenter_name=commenter_name,
                                                    comment_text=comment_text,
                                                    reply_text=reply_msg,
                                                    post_id=post_id_val
                                                )
                                                
                                                # Log the DM as well
                                                dm_status = 'failed' if dm_res.get('error') else 'sent'
                                                error_msg = str(dm_res.get('error', '')) if dm_res.get('error') else None
                                                sender_id = from_data.get("id")
                                                
                                                AutoDMLog.objects.create(
                                                    business=connection.business,
                                                    comment_text=comment_text,
                                                    platform=platform,
                                                    trigger_type='comment',
                                                    recipient_name=commenter_name,
                                                    recipient_id=sender_id,
                                                    dm_text=reply_msg,
                                                    post_id=post_id_val,
                                                    status=dm_status,
                                                    error_message=error_msg
                                                )
                                        
                                         
                    # === HANDLE LIKE EVENTS (Facebook & Instagram) ===
                    is_fb_like = value.get("item") in ["like", "reaction"] and value.get("verb") == "add" and data.get("object") == "page"
                    is_ig_like = field == "likes" and data.get("object") == "instagram"
                    
                    if is_fb_like or is_ig_like:
                        if is_ig_like:
                            # Instagram provides the liker's ID simply as 'id' in the value object for likes
                            sender_id = value.get("id")
                            sender_name = "IG User"
                            post_id = value.get("media_id", "")
                        else:
                            sender_id = value.get("from", {}).get("id")
                            sender_name = value.get("from", {}).get("name", "Unknown")
                            post_id = value.get("post_id", "")
                        
                        # Don't DM our own page/account
                        if sender_id and sender_id != target_id:
                            from .models import MetaConnection, AutoReplySettings, AutoDMLog
                            from django.db.models import Q
                            
                            connection = MetaConnection.objects.filter(
                                Q(page_id=target_id) | Q(instagram_id=target_id),
                                is_active=True
                            ).first()
                            
                            if connection:
                                dm_settings = AutoReplySettings.objects.filter(business=connection.business).first()
                                
                                if dm_settings:
                                    dm_active = dm_settings.ig_dm_on_like_active if is_ig_like else dm_settings.fb_dm_on_like_active
                                    dm_text = dm_settings.ig_dm_text if is_ig_like else dm_settings.fb_dm_text
                                    
                                    if dm_active and dm_text:
                                        from . import meta_service
                                        if is_ig_like:
                                            res = meta_service.send_instagram_dm(
                                                sender_id, dm_text, connection.instagram_id, connection.access_token, connection.page_id
                                            )
                                        else:
                                            res = meta_service.send_facebook_dm(
                                                sender_id, dm_text, connection.page_id, connection.access_token
                                            )
                                        
                                        # Log the auto-DM
                                        dm_status = 'failed' if res.get('error') else 'sent'
                                        error_msg = str(res.get('error', '')) if res.get('error') else None
                                        AutoDMLog.objects.create(
                                            business=connection.business,
                                            platform='instagram' if is_ig_like else 'facebook',
                                            trigger_type='like',
                                            recipient_name=sender_name,
                                            recipient_id=sender_id,
                                            dm_text=dm_text,
                                            post_id=post_id,
                                            status=dm_status,
                                            error_message=error_msg
                                        )
                                        
        return HttpResponse('EVENT_RECEIVED', status=200)

class CreateAdScratchView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        business = request.user.business
            
        connection = MetaConnection.objects.filter(business=business, is_active=True).first()
        if not connection or not connection.ad_account_id:
            return Response({"error": "No Ad Account connected"}, status=status.HTTP_400_BAD_REQUEST)
            
        budget = request.data.get('budget', 10.00)
        campaign_name = request.data.get('campaign_name', "Custom Campaign")
        objective = request.data.get('objective', 'OUTCOME_ENGAGEMENT')
        age_min = request.data.get('age_min', 18)
        age_max = request.data.get('age_max', 65)
        genders = request.data.get('genders', [])
        countries = request.data.get('countries', ['IN'])
        website_url = request.data.get('website_url', 'https://example.com')
        campaign_status = request.data.get('status', 'PAUSED')
        call_to_action = request.data.get('call_to_action', 'LEARN_MORE')
        
        ad_creative = request.data.get('custom_creative', 'Custom Ad')
        ad_image_url = request.data.get('custom_media_url', '')

        if not ad_image_url:
            return Response({"error": "An image URL is required for the ad."}, status=status.HTTP_400_BAD_REQUEST)
        
        targeting = {
            "geo_locations": {"countries": countries},
            "age_min": int(age_min),
            "age_max": int(age_max)
        }
        if genders:
            targeting["genders"] = genders

        try:
            # 0. Create a dummy post to satisfy the database relationship
            post = GeneratedPost.objects.create(
                business=business,
                topic=campaign_name,
                generated_content=ad_creative,
                media_url=ad_image_url,
                status='AD_SCRATCH'
            )

            # 1. Create Campaign
            camp_res = meta_service.create_ad_campaign(connection.ad_account_id, campaign_name, connection.access_token, objective=objective, status=campaign_status)
            if 'error' in camp_res: raise Exception(camp_res['error'])
            camp_id = camp_res['id']

            # 2. Create Ad Set
            adset_res = meta_service.create_ad_set(connection.ad_account_id, connection.access_token, camp_id, f"AdSet: {campaign_name}", float(budget), targeting=targeting, status=campaign_status)
            if 'error' in adset_res: raise Exception(adset_res['error'])
            adset_id = adset_res['id']
            
            # 3. Upload Image or Video
            if ad_image_url and not ad_image_url.startswith('http'):
                ad_image_url = request.build_absolute_uri(ad_image_url)
                
            image_hash = None
            video_id = None
            clean_url = ad_image_url.lower().split('?')[0]
            if clean_url.endswith(('.mp4', '.mov', '.webm')):
                vid_res = meta_service.upload_ad_video(connection.ad_account_id, connection.access_token, ad_image_url)
                if 'error' in vid_res: raise Exception(vid_res['error'])
                video_id = vid_res['id']
                # Upload a default thumbnail for video to get image_hash
                fallback_thumb = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ac/No_image_available.svg/1024px-No_image_available.svg.png"
                
                logo_asset = BrandAsset.objects.filter(business=business, asset_type='LOGO').first()
                if logo_asset and logo_asset.file:
                    fallback_thumb = request.build_absolute_uri(logo_asset.file.url)
                    if '127.0.0.1' in fallback_thumb or 'localhost' in fallback_thumb:
                        import os
                        redirect_uri = os.environ.get('META_REDIRECT_URI', '')
                        if 'devtunnels.ms' in redirect_uri:
                            from urllib.parse import urlparse
                            host = urlparse(redirect_uri).netloc
                            host = host.replace('-5173.', '-8000.')
                            fallback_thumb = f"https://{host}{logo_asset.file.url}"
                img_res = meta_service.upload_ad_image(connection.ad_account_id, connection.access_token, fallback_thumb)
                if 'error' not in img_res and 'images' in img_res:
                    image_hash = img_res['images']['image.jpg']['hash']
            else:
                img_res = meta_service.upload_ad_image(connection.ad_account_id, connection.access_token, ad_image_url)
                if 'error' in img_res: raise Exception(img_res['error'])
                image_hash = img_res['images']['image.jpg']['hash']
            
            # 4. Create Creative
            creative_res = meta_service.create_ad_creative(connection.ad_account_id, connection.access_token, connection.page_id, ad_creative, website_url, image_hash=image_hash, video_id=video_id, call_to_action_type=call_to_action, video_thumbnail_url=fallback_thumb if video_id else None)
            if 'error' in creative_res: raise Exception(creative_res['error'])
            creative_id = creative_res['id']
            
            # 5. Create Ad
            ad_res = meta_service.create_ad(connection.ad_account_id, connection.access_token, adset_id, creative_id, f"Ad: {campaign_name}", status=campaign_status)
            if 'error' in ad_res: raise Exception(ad_res['error'])
            ad_id = ad_res['id']

            AdCampaign.objects.create(
                post=post, meta_campaign_id=camp_id, meta_adset_id=adset_id, meta_ad_id=ad_id, budget=budget
            )
            return Response({"message": "Ad Campaign created successfully in PAUSED state from scratch.", "post_id": post.id})
            
        except Exception as e:
            return Response({"error": f"Ad creation failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from .models import AutoReplyLog
from .serializers import AutoReplyLogSerializer

class AutoReplyLogListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = AutoReplyLogSerializer

    def get_queryset(self):
        return AutoReplyLog.objects.filter(business=self.request.user.business)

from .models import AutoDMLog
from .serializers import AutoDMLogSerializer

class AutoDMLogListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = AutoDMLogSerializer

    def get_queryset(self):
        return AutoDMLog.objects.filter(business=self.request.user.business)


class MetaPostDetailsView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, post_id):
        platform = request.query_params.get('platform', 'instagram')
        connection = MetaConnection.objects.filter(business=request.user.business, is_active=True).first()
        if not connection:
            return Response({"error": "No Meta connection found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from .meta_service import fetch_post_details, _get_page_access_token
            access_token = _get_page_access_token(connection.page_id, connection.access_token) if connection.page_id else connection.access_token
            details = fetch_post_details(post_id, access_token, platform)
            return Response(details, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AdCampaignListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    from .serializers import AdCampaignSerializer
    serializer_class = AdCampaignSerializer

    def get_queryset(self):
        return AdCampaign.objects.filter(post__business=self.request.user.business).order_by('-created_at')


