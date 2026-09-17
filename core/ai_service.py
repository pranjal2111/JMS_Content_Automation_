import os
import io
import base64
import uuid
import requests
from django.conf import settings
from openai import AzureOpenAI
try:
    from PIL import Image
except ImportError:
    pass

def generate_post_content(prompt: str) -> str:
    endpoint_url = os.environ.get("ENDPOINT_URL", "").strip()
    api_key = os.environ.get("OPENAI_API_KEY")
    
    # Check if this is an Azure OpenAI key
    if endpoint_url and 'azure.com' in endpoint_url:
        client = AzureOpenAI(
            api_key=api_key,
            api_version="2023-12-01-preview",
            azure_endpoint=endpoint_url
        )
        # Note: In Azure, 'model' must match your exact deployment name.
        model_name = "gpt-4o-mini"
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": (
                    "You are an expert social media manager and copywriter. "
                    "Write highly engaging, human-like Facebook posts. "
                    "CRITICAL: Do NOT use any markdown formatting. Do NOT use bullet points, hyphens (-), or dashes for lists. Write in natural paragraphs. "
                    "Do NOT sound like an AI. Keep the tone conversational, authentic, and natural. "
                    "STRICT RULE: Output ONLY the raw post content. NEVER include conversational filler like 'Here is your post', 'Sure', or 'You're welcome!'. Start the post immediately."
                )},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    else:
        # Fallback to standard OpenAI if needed, or raise exception
        raise ValueError("Azure OpenAI configuration is missing or invalid.")

def generate_image_for_post(prompt: str, brand_name: str = None, logo_path: str = None) -> str:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    endpoint_url = os.environ.get("Endpoint")
    api_key = os.environ.get("Secret_Key")
    model_name = os.environ.get("Model", "gpt-image-2.5-flare")
    
    if not endpoint_url or not api_key:
        return None
        
    try:
        # Based on standard AzureOpenAI configuration for images
        client = AzureOpenAI(
            api_key=api_key,
            api_version="2024-02-15-preview",
            azure_endpoint=endpoint_url
        )
        
        # Create an image generation prompt based on the content
        image_prompt = f"Create a professional, high-quality image for a social media post with the following context: {prompt[:800]}"
        
        if brand_name:
            image_prompt += f"\nMake sure the visual style aligns with the brand '{brand_name}'."
        # We don't ask DALL-E to generate a logo anymore since we are overlaying the real one!
            
        response = client.images.generate(
            model=model_name,
            prompt=image_prompt,
            n=1,
            size="1024x1024"
        )
        
        if response.data and len(response.data) > 0:
            img_data = response.data[0]
            
            # 1. Get raw image bytes
            image_bytes = None
            if getattr(img_data, 'b64_json', None):
                image_bytes = base64.b64decode(img_data.b64_json)
            elif getattr(img_data, 'url', None):
                resp = requests.get(img_data.url)
                if resp.status_code == 200:
                    image_bytes = resp.content
            
            if not image_bytes:
                return None
                
            # 2. Composite logo if available
            if logo_path and os.path.exists(logo_path):
                try:
                    # Open base image
                    base_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
                    
                    # Open logo
                    logo_img = Image.open(logo_path).convert("RGBA")
                    
                    # Resize logo (e.g., 20% of base image width)
                    target_width = int(base_img.width * 0.20)
                    aspect_ratio = logo_img.height / logo_img.width
                    target_height = int(target_width * aspect_ratio)
                    logo_img = logo_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    
                    # Position: Top Right with 30px padding
                    padding = 30
                    position = (base_img.width - target_width - padding, padding)
                    
                    # Paste logo using alpha channel as mask
                    base_img.alpha_composite(logo_img, dest=position)
                    
                    # Convert back to RGB for saving as standard image if needed, or save as PNG (which supports alpha)
                    output_io = io.BytesIO()
                    base_img.save(output_io, format="PNG")
                    image_bytes = output_io.getvalue()
                except Exception as composite_err:
                    print(f"Failed to overlay logo: {composite_err}")
            
            # 3. Save the image to the media folder
            filename = f"generated_img_{uuid.uuid4().hex[:8]}.png"
            save_dir = os.path.join(settings.MEDIA_ROOT, 'ai_images')
            os.makedirs(save_dir, exist_ok=True)
            
            filepath = os.path.join(save_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
                
            # 4. Return the URL to access it via Django
            return f"{settings.MEDIA_URL}ai_images/{filename}"
    except Exception as e:
        print(f"Image generation failed: {e}")
        
    return None
