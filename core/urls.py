from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from . import api_views

urlpatterns = [
    # API Auth
    path('api/auth/signup/', api_views.RegisterView.as_view(), name='api_signup'),
    path('api/auth/login/', TokenObtainPairView.as_view(), name='api_login'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('api/auth/me/', api_views.CurrentUserView.as_view(), name='api_auth_me'),
    path('api/auth/logout/', api_views.LogoutView.as_view(), name='api_auth_logout'),
    
    # API Knowledge Base
    path('api/knowledge-base/', api_views.BrandProfileView.as_view(), name='api_brand_profile'),
    path('api/assets/', api_views.BrandAssetView.as_view(), name='api_brand_assets'),
    path('api/assets/<int:pk>/', api_views.BrandAssetDetailView.as_view(), name='api_brand_asset_detail'),
    
    # API Dashboard (Stats & Posts)
    path('api/dashboard/stats/', api_views.DashboardStatsView.as_view(), name='api_dashboard_stats'),
    path('api/posts/', api_views.PostListView.as_view(), name='api_post_list'),
    path('api/posts/<int:pk>/', api_views.PostDetailView.as_view(), name='api_post_detail'),
    path('api/posts/<int:pk>/publish/', api_views.PublishPostView.as_view(), name='api_post_publish'),
    path('api/generate/', api_views.GeneratePostView.as_view(), name='api_generate_post'),

    # API Meta OAuth & Pages
    path('api/meta/auth-url/', api_views.GetMetaAuthUrlView.as_view(), name='api_meta_auth_url'),
    path('api/meta/callback/', api_views.MetaCallbackAPIView.as_view(), name='api_meta_callback'),
    path('api/meta/status/', api_views.MetaStatusView.as_view(), name='api_meta_status'),
    path('api/meta/pages/', api_views.MetaPagesView.as_view(), name='api_meta_pages'),
    path('api/meta/ad-accounts/', api_views.MetaAdAccountsView.as_view(), name='api_meta_ad_accounts'),
    path('api/meta/auto-reply-settings/', api_views.AutoReplySettingsView.as_view(), name='api_auto_reply_settings'),
    
    # Meta Webhook (Public)
    path('api/webhooks/meta/', api_views.MetaWebhookView.as_view(), name='api_meta_webhook'),
    
    # Auto Reply Logs
    path('api/auto-reply-logs/', api_views.AutoReplyLogListView.as_view(), name='api_auto_reply_logs'),
    
    # Ad Campaign creation
    path('api/posts/<int:pk>/create-ad/', api_views.CreateAdView.as_view(), name='api_create_ad'),
    path('api/ads/create-scratch/', api_views.CreateAdScratchView.as_view(), name='api_create_ad_scratch'),
]
