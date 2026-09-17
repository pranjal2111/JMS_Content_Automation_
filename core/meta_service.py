import os
import requests
from django.conf import settings

META_API_VERSION = "v19.0"
GRAPH_API_URL = f"https://graph.facebook.com/{META_API_VERSION}"

def get_meta_app_credentials():
    return {
        "client_id": os.environ.get("META_APP_ID"),
        "client_secret": os.environ.get("META_APP_SECRET"),
        "redirect_uri": os.environ.get("META_REDIRECT_URI", "http://localhost:5173/meta-connect")
    }

def get_authorization_url():
    creds = get_meta_app_credentials()
    # Requesting scopes needed for publishing, instagram, messaging, and ads
    scopes = "pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish,instagram_manage_comments,ads_management,ads_read,pages_manage_metadata"
    
    url = f"https://www.facebook.com/{META_API_VERSION}/dialog/oauth"
    url += f"?client_id={creds['client_id']}"
    url += f"&redirect_uri={creds['redirect_uri']}"
    url += f"&scope={scopes}"
    return url

def exchange_code_for_token(code):
    """
    Exchanges the authorization code for a short-lived access token,
    and then immediately exchanges it for a long-lived access token.
    """
    creds = get_meta_app_credentials()
    
    # 1. Get Short Lived Token
    token_url = f"{GRAPH_API_URL}/oauth/access_token"
    params = {
        "client_id": creds["client_id"],
        "redirect_uri": creds["redirect_uri"],
        "client_secret": creds["client_secret"],
        "code": code
    }
    
    response = requests.get(token_url, params=params)
    if response.status_code != 200:
        raise Exception(f"Failed to get token: {response.json()}")
        
    short_token = response.json().get("access_token")
    
    # 2. Get Long Lived Token
    long_token_params = {
        "grant_type": "fb_exchange_token",
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "fb_exchange_token": short_token
    }
    
    long_response = requests.get(token_url, params=long_token_params)
    if long_response.status_code != 200:
        return short_token # Fallback to short token if exchange fails
        
    return long_response.json().get("access_token")

def fetch_user_pages(access_token):
    """Fetches all Facebook Pages the user manages."""
    url = f"{GRAPH_API_URL}/me/accounts"
    params = {
        "access_token": access_token,
        "fields": "id,name,access_token,instagram_business_account"
    }
    response = requests.get(url, params=params)
    data = response.json()
    if 'error' in data:
        raise Exception(data['error']['message'])
    return data.get('data', [])

def fetch_user_ad_accounts(access_token):
    """Fetches all Ad Accounts the user manages."""
    url = f"{GRAPH_API_URL}/me/adaccounts"
    params = {
        "access_token": access_token,
        "fields": "id,name,account_id"
    }
    response = requests.get(url, params=params)
    data = response.json()
    if 'error' in data:
        raise Exception(data['error']['message'])
    return data.get('data', [])
    return []

import json

def publish_to_page(page_id, user_access_token, message, image_urls=None):
    """Publishes a text post, single image post, or multi-image carousel to a Facebook Page."""
    # First, get the correct page access token
    token_url = f"{GRAPH_API_URL}/{page_id}"
    token_params = {"fields": "access_token", "access_token": user_access_token}
    token_response = requests.get(token_url, params=token_params).json()
    
    if isinstance(token_response, dict):
        page_access_token = token_response.get("access_token", user_access_token)
    else:
        page_access_token = user_access_token

    if not image_urls:
        # Text only post
        url = f"{GRAPH_API_URL}/{page_id}/feed"
        payload = {"message": message, "access_token": page_access_token}
        response = requests.post(url, data=payload)
        return response.json()
        
    if isinstance(image_urls, str):
        image_urls = [image_urls]

    if len(image_urls) == 1:
        # Single image post
        url = f"{GRAPH_API_URL}/{page_id}/photos"
        payload = {"url": image_urls[0], "message": message, "access_token": page_access_token}
        response = requests.post(url, data=payload)
        return response.json()
        
    # Multi-image post (Carousel)
    attached_media = []
    for img_url in image_urls:
        upload_url = f"{GRAPH_API_URL}/{page_id}/photos"
        upload_payload = {
            "url": img_url,
            "published": "false",
            "access_token": page_access_token
        }
        upload_res = requests.post(upload_url, data=upload_payload).json()
        if "id" in upload_res:
            attached_media.append({"media_fbid": upload_res["id"]})
            
    if not attached_media:
        return {"error": {"message": "Failed to upload images for carousel."}}
        
    # Publish the multi-image post
    feed_url = f"{GRAPH_API_URL}/{page_id}/feed"
    feed_payload = {
        "message": message,
        "attached_media": json.dumps(attached_media),
        "access_token": page_access_token
    }
    response = requests.post(feed_url, data=feed_payload)
    return response.json()

def publish_to_instagram(ig_user_id, access_token, image_url, caption):
    """Publishes a single image post to Instagram."""
    # 1. Create media container
    media_url = f"{GRAPH_API_URL}/{ig_user_id}/media"
    media_payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token
    }
    media_res = requests.post(media_url, data=media_payload).json()
    
    if "id" not in media_res:
        return {"error": media_res}
        
    creation_id = media_res["id"]
    
    # 2. Publish container
    publish_url = f"{GRAPH_API_URL}/{ig_user_id}/media_publish"
    publish_payload = {
        "creation_id": creation_id,
        "access_token": access_token
    }
    response = requests.post(publish_url, data=publish_payload)
    return response.json()

def send_comment_reply(comment_id, message, access_token):
    """Replies to a specific comment on Facebook or Instagram."""
    url = f"{GRAPH_API_URL}/{comment_id}/replies"
    payload = {
        "message": message,
        "access_token": access_token
    }
    response = requests.post(url, data=payload)
    return response.json()

def create_ad_campaign(ad_account_id, name, access_token, objective="OUTCOME_ENGAGEMENT"):
    """Creates a basic ad campaign."""
    url = f"{GRAPH_API_URL}/act_{ad_account_id}/campaigns"
    payload = {
        "name": name,
        "objective": objective,
        "status": "PAUSED",
        "special_ad_categories": "[]",
        "access_token": access_token
    }
    response = requests.post(url, data=payload)
    return response.json()

def create_ad_set(ad_account_id, access_token, campaign_id, name, daily_budget, targeting=None):
    """Creates an Ad Set within a campaign."""
    url = f"{GRAPH_API_URL}/act_{ad_account_id}/adsets"
    payload = {
        "name": name,
        "campaign_id": campaign_id,
        "daily_budget": int(daily_budget * 100), # Meta requires budget in cents
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "REACH",
        "bid_amount": 100,
        "status": "PAUSED",
        "access_token": access_token
    }
    if targeting:
        payload["targeting"] = json.dumps(targeting)
        
    response = requests.post(url, data=payload)
    return response.json()

def upload_ad_image(ad_account_id, access_token, image_url):
    """Uploads an image to the ad account and returns its hash."""
    url = f"{GRAPH_API_URL}/act_{ad_account_id}/adimages"
    # Download image first
    img_data = requests.get(image_url).content
    files = {
        "filename": ("image.jpg", img_data, "image/jpeg")
    }
    payload = {
        "access_token": access_token
    }
    response = requests.post(url, data=payload, files=files)
    return response.json()

def create_ad_creative(ad_account_id, access_token, page_id, message, link, image_hash, call_to_action_type="LEARN_MORE"):
    """Creates an Ad Creative linked to a Facebook Page."""
    url = f"{GRAPH_API_URL}/act_{ad_account_id}/adcreatives"
    
    call_to_action = {
        "type": call_to_action_type,
        "value": {
            "link": link
        }
    }
    
    payload = {
        "name": f"Creative for {page_id}",
        "object_story_spec": json.dumps({
            "page_id": page_id,
            "link_data": {
                "image_hash": image_hash,
                "link": link,
                "message": message,
                "call_to_action": call_to_action
            }
        }),
        "access_token": access_token
    }
    response = requests.post(url, data=payload)
    return response.json()

def create_ad(ad_account_id, access_token, adset_id, creative_id, name):
    """Creates the final Ad."""
    url = f"{GRAPH_API_URL}/act_{ad_account_id}/ads"
    payload = {
        "name": name,
        "adset_id": adset_id,
        "creative": json.dumps({"creative_id": creative_id}),
        "status": "PAUSED",
        "access_token": access_token
    }
    response = requests.post(url, data=payload)
    return response.json()

def get_ad_insights(ad_id, access_token):
    """Pulls insights (spend, impressions, clicks, etc.) for a specific Ad."""
    url = f"{GRAPH_API_URL}/{ad_id}/insights"
    params = {
        "fields": "spend,impressions,clicks,cpc,ctr",
        "access_token": access_token
    }
    response = requests.get(url, params=params)
    return response.json()
