from rest_framework import generics, status, views
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .models import BrandProfile, GeneratedPost, MetaConnection, BrandAsset
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
        if not topic:
            return Response({'error': 'Topic is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        business = request.user.business
        profile = BrandProfile.objects.filter(business=business).first()
        
        # Build prompt using Brand Profile info
        brand_info = ""
        if profile:
            tone = custom_tone if custom_tone else profile.tone_of_voice
            website_data = ""
            if profile.website_url:
                website_data = extract_text_from_url(profile.website_url)
                
            # Get text from all uploaded PDF documents
            pdf_data = ""
            documents = BrandAsset.objects.filter(business=business, asset_type='DOCUMENT')
            for doc in documents:
                if doc.file and doc.file.path.endswith('.pdf'):
                    pdf_data += extract_text_from_pdf(doc.file.path) + "\n\n"
                
            brand_info = (
                f"\nBrand Context:\n"
                f"- Tone of Voice: {tone}\n"
                f"- Target Audience: {profile.target_audience}\n"
                f"- Brand Guidelines: {profile.brand_guidelines}\n"
                f"- Company Description/Brochure: {profile.company_description}\n"
                f"- Website Content: {website_data}\n"
                f"- Uploaded Document/PDF Content: {pdf_data[:10000]}\n" # Limit to 10k chars
            )
        
        prompt = (
            f"Write a Facebook post about: {topic}.\n"
            f"{brand_info}\n"
            "Instructions:\n"
            "- Write in the exact tone and adhere strictly to the brand guidelines provided.\n"
            "- Speak directly to the target audience naturally.\n"
            "- Do NOT start with typical AI openings (e.g., 'Hey everyone!', 'Are you looking for...').\n"
            "- Include 2-3 suitable emojis and a few relevant hashtags.\n"
            "- REMEMBER: No markdown formatting, NO bullet points, and NO hyphens (-) for lists. Write in flowing paragraphs only.\n"
            "- CRITICAL: Output ONLY the Facebook post. Do not output anything else."
        )
        
        try:
            content = ai_service.generate_post_content(prompt)
            
            # Check if brand has uploaded a logo
            logo_asset = BrandAsset.objects.filter(business=business, asset_type='LOGO').first()
            logo_path = logo_asset.file.path if logo_asset and logo_asset.file else None
            
            # Generate an accompanying image
            image_url = ai_service.generate_image_for_post(
                content, 
                brand_name=business.name if business else None, 
                logo_path=logo_path
            )
            
            # Save the generated post to review
            post = GeneratedPost.objects.create(
                business=business,
                topic=topic,
                generated_content=content,
                media_url=image_url,
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
        platform = request.data.get('platform', 'facebook') # 'facebook' or 'instagram'

        try:
            post = GeneratedPost.objects.get(pk=pk, business=business)
        except GeneratedPost.DoesNotExist:
            return Response({"error": "Post not found"}, status=status.HTTP_404_NOT_FOUND)
            
        connection = MetaConnection.objects.filter(business=business, is_active=True).first()
        if not connection or not connection.access_token:
            return Response({"error": "Meta account not connected"}, status=status.HTTP_400_BAD_REQUEST)
            
        if platform == 'facebook' and not connection.page_id:
            return Response({"error": "No Facebook Page selected for publishing"}, status=status.HTTP_400_BAD_REQUEST)
        elif platform == 'instagram' and not connection.instagram_id:
            return Response({"error": "No Instagram account selected for publishing"}, status=status.HTTP_400_BAD_REQUEST)
            
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
            
            if platform == 'facebook':
                response_data = meta_service.publish_to_page(
                    page_id=connection.page_id,
                    user_access_token=connection.access_token,
                    message=post.generated_content,
                    image_urls=images_to_post
                )
            else:
                # Instagram requires an image
                if not images_to_post:
                    return Response({"error": "Instagram requires an image. Text-only posts are not supported."}, status=status.HTTP_400_BAD_REQUEST)
                    
                # Instagram only supports single images for now in this flow
                response_data = meta_service.publish_to_instagram(
                    ig_user_id=connection.instagram_id,
                    access_token=connection.access_token,
                    image_url=images_to_post[0] if isinstance(images_to_post, list) else images_to_post,
                    caption=post.generated_content
                )
            
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
            "is_active": settings.is_active
        })

    def post(self, request):
        business = request.user.business
        settings, _ = AutoReplySettings.objects.get_or_create(business=business)
        settings.reply_text = request.data.get('reply_text', '')
        settings.is_active = request.data.get('is_active', False)
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
            camp_res = meta_service.create_ad_campaign(connection.ad_account_id, campaign_name, connection.access_token, objective=objective)
            if 'error' in camp_res: raise Exception(camp_res['error'])
            camp_id = camp_res['id']

            # 2. Create Ad Set
            adset_res = meta_service.create_ad_set(connection.ad_account_id, connection.access_token, camp_id, f"AdSet: {post.topic}", float(budget), targeting=targeting)
            if 'error' in adset_res: raise Exception(adset_res['error'])
            adset_id = adset_res['id']
            
            # 3. Upload Image
            image_url = post.media_urls[0] if post.media_urls else post.media_url
            img_res = meta_service.upload_ad_image(connection.ad_account_id, connection.access_token, image_url)
            if 'error' in img_res: raise Exception(img_res['error'])
            image_hash = img_res['images']['image.jpg']['hash']
            
            # 4. Create Creative
            creative_res = meta_service.create_ad_creative(connection.ad_account_id, connection.access_token, connection.page_id, post.generated_content, website_url, image_hash, call_to_action_type=call_to_action)
            if 'error' in creative_res: raise Exception(creative_res['error'])
            creative_id = creative_res['id']
            
            # 5. Create Ad
            ad_res = meta_service.create_ad(connection.ad_account_id, connection.access_token, adset_id, creative_id, f"Ad: {post.topic}")
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
                    if field in ["feed", "comments"]:
                        value = change.get("value", {})
                        
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
                                    settings = AutoReplySettings.objects.filter(business=connection.business, is_active=True).first()
                                    if settings and settings.reply_text:
                                        from . import meta_service
                                        meta_service.send_comment_reply(comment_id, settings.reply_text, connection.access_token)
                                        
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
                status='PUBLISHED'
            )

            # 1. Create Campaign
            camp_res = meta_service.create_ad_campaign(connection.ad_account_id, campaign_name, connection.access_token, objective=objective)
            if 'error' in camp_res: raise Exception(camp_res['error'])
            camp_id = camp_res['id']

            # 2. Create Ad Set
            adset_res = meta_service.create_ad_set(connection.ad_account_id, connection.access_token, camp_id, f"AdSet: {campaign_name}", float(budget), targeting=targeting)
            if 'error' in adset_res: raise Exception(adset_res['error'])
            adset_id = adset_res['id']
            
            # 3. Upload Image
            img_res = meta_service.upload_ad_image(connection.ad_account_id, connection.access_token, ad_image_url)
            if 'error' in img_res: raise Exception(img_res['error'])
            image_hash = img_res['images']['image.jpg']['hash']
            
            # 4. Create Creative
            creative_res = meta_service.create_ad_creative(connection.ad_account_id, connection.access_token, connection.page_id, ad_creative, website_url, image_hash, call_to_action_type=call_to_action)
            if 'error' in creative_res: raise Exception(creative_res['error'])
            creative_id = creative_res['id']
            
            # 5. Create Ad
            ad_res = meta_service.create_ad(connection.ad_account_id, connection.access_token, adset_id, creative_id, f"Ad: {campaign_name}")
            if 'error' in ad_res: raise Exception(ad_res['error'])
            ad_id = ad_res['id']

            AdCampaign.objects.create(
                post=post, meta_campaign_id=camp_id, meta_adset_id=adset_id, meta_ad_id=ad_id, budget=budget
            )
            return Response({"message": "Ad Campaign created successfully in PAUSED state from scratch.", "post_id": post.id})
            
        except Exception as e:
            return Response({"error": f"Ad creation failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
