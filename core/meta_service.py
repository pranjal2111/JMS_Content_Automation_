import os
import requests
from django.conf import settings

META_API_VERSION = "v19.0"
GRAPH_API_URL = f"https://graph.facebook.com/{META_API_VERSION}"

def get_meta_app_credentials():
    return {
        "client_id": os.environ.get("META_APP_ID"),
        "client_secret": os.environ.get("META_APP_SECRET"),
        "redirect_uri": "http://localhost:5174/meta-connect"
    }

def get_authorization_url():
    creds = get_meta_app_credentials()
    # Requesting scopes needed for publishing
    scopes = "pages_show_list,pages_read_engagement,pages_manage_posts"
    
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
        "client_redirect_uri": creds["redirect_uri"],
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
    """Fetches the pages managed by the user."""
    url = f"{GRAPH_API_URL}/me/accounts"
    params = {"access_token": access_token}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json().get("data", [])
    return []

def publish_to_page(page_id, page_access_token, message, image_url=None):
    """Publishes a post to a specific Facebook Page."""
    if image_url:
        url = f"{GRAPH_API_URL}/{page_id}/photos"
        payload = {
            "url": image_url,
            "message": message,
            "access_token": page_access_token
        }
    else:
        url = f"{GRAPH_API_URL}/{page_id}/feed"
        payload = {
            "message": message,
            "access_token": page_access_token
        }
        
    response = requests.post(url, data=payload)
    return response.json()
