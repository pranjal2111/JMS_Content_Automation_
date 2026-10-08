import os
from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
from core.models import GeneratedPost, MetaConnection
from core import meta_service
import logging

logger = logging.getLogger(__name__)

def publish_scheduled_posts():
    now = timezone.now()
    # Find posts that are APPROVED and scheduled time is reached
    posts_to_publish = GeneratedPost.objects.filter(
        status='APPROVED',
        scheduled_at__lte=now
    )
    
    for post in posts_to_publish:
        business = post.business
        connection = MetaConnection.objects.filter(business=business, is_active=True).first()
        
        if not connection or not connection.access_token:
            post.status = 'FAILED'
            post.save()
            logger.error(f"Failed to publish post {post.id}: Meta account not connected")
            continue
            
        platform = post.published_platform if post.published_platform else 'facebook'
        
        try:
            images_to_post = post.media_urls if post.media_urls else post.media_url
            
            def make_public_url(url):
                if not url: return url
                if url.startswith('http'): return url
                
                # In background task, we don't have request. We rely on META_REDIRECT_URI.
                redirect_uri = os.environ.get('META_REDIRECT_URI', 'http://localhost:8000')
                if 'devtunnels.ms' in redirect_uri:
                    from urllib.parse import urlparse
                    host = urlparse(redirect_uri).netloc
                    host = host.replace('-5173.', '-8000.')
                    return f"https://{host}{url}"
                
                # Fallback if no tunnel
                return f"http://localhost:8000{url}"

            if isinstance(images_to_post, list):
                images_to_post = [make_public_url(img) for img in images_to_post]
            else:
                images_to_post = make_public_url(images_to_post)
                
            responses = []
            if platform in ('facebook', 'both'):
                if connection.page_id:
                    fb_res = meta_service.publish_to_page(
                        page_id=connection.page_id,
                        user_access_token=connection.access_token,
                        message=post.generated_content,
                        image_urls=images_to_post
                    )
                    responses.append(fb_res)
                    
            if platform in ('instagram', 'both'):
                if connection.instagram_id and images_to_post:
                    ig_url = images_to_post[0] if isinstance(images_to_post, list) else images_to_post
                    ig_res = meta_service.publish_to_instagram(
                        ig_user_id=connection.instagram_id,
                        access_token=connection.access_token,
                        image_url=ig_url,
                        caption=post.generated_content
                    )
                    responses.append(ig_res)
                    
            # Check for errors
            has_error = False
            for response_data in responses:
                if isinstance(response_data, dict) and 'error' in response_data:
                    has_error = True
                    logger.error(f"Error publishing post {post.id}: {response_data['error']}")
                    break
                    
            if has_error:
                post.status = 'FAILED'
            else:
                post.status = 'PUBLISHED'
                post.published_platform = platform
                logger.info(f"Successfully published scheduled post {post.id}")
                
            post.save()
            
        except Exception as e:
            post.status = 'FAILED'
            post.save()
            logger.error(f"Exception while publishing post {post.id}: {str(e)}")

def start_scheduler():
    scheduler = BackgroundScheduler()
    # Runs the function every 1 minute
    scheduler.add_job(publish_scheduled_posts, 'interval', minutes=1, id='publish_scheduled_posts', replace_existing=True)
    scheduler.start()
    logger.info("APScheduler for publishing posts has started.")
