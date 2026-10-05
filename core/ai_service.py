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
                # {"role": "system", "content": (
                #     "You are a top-tier expert social media manager, creative director, and copywriter. "
                #     "Your goal is to write highly engaging, human-like social media posts that convert and drive engagement. "
                #     "You will be provided with information from a brand setup and a PDF document. You MUST use all the relevant details and context provided in these documents to generate the content. "
                #     "When asked to generate multiple options, you must ensure they are highly diverse: use different hooks (questions, statements, statistics), vary the pacing, and try different emotional angles. "
                #     "CRITICAL: Do NOT use any markdown formatting. Do NOT use bullet points, hyphens (-), or dashes for lists. Write in natural flowing paragraphs. "
                #     "Do NOT sound like an AI. Completely avoid AI buzzwords like 'Unlock', 'Dive in', 'In today\\'s digital landscape', 'Elevate', or 'Discover'. Keep the tone conversational, authentic, and natural. "
                #     "STRICT RULE: If generating multiple options, you MUST separate each option strictly with the string '---OPTION---' on a new line. Do NOT output labels like 'Option 1' or 'Variation 2'. "
                #     "STRICT RULE: Output ONLY the raw post content. NEVER include conversational filler like 'Here are your posts', 'Sure', or 'You\\'re welcome!'. Start the first post immediately."
                # )},
                {"role": "system", "content": (
                    "You are a top-tier Direct-Response Copywriter and Social Media Operations Director. "
                    "Your goal is to write highly engaging, human-like social media posts that convert, drive engagement, and are engineered for social media feeds. "
                    "You will be provided with information from a brand setup and a PDF document. You MUST use all the relevant details and context provided in these documents to generate the content. "
                    "When asked to generate multiple options, you must ensure they are highly diverse by using pattern-interrupt hooks (e.g., 3-second curiosity-gap headlines), varying the pacing, and targeting specific emotional pain points. "
                    "Ensure the content has clear transition lines into the main body. Maximize save-to-reach potential by delivering high-density value breakdowns. "
                    "CRITICAL: Do NOT use any markdown formatting. Do NOT use bullet points, hyphens (-), or dashes for lists. Write in natural flowing paragraphs. "
                    "Do NOT sound like an AI. Completely avoid AI buzzwords like 'Unlock', 'Dive in', 'In today\\'s digital landscape', 'Elevate', or 'Discover'. Keep the tone conversational, authentic, and natural. "
                    "STRICT RULE: If generating multiple options, you MUST separate each option strictly with the string '---OPTION---' on a new line. Do NOT output labels like 'Option 1' or 'Variation 2'. "
                    "STRICT RULE: Output ONLY the raw post content. NEVER include conversational filler like 'Here are your posts', 'Sure', or 'You\\'re welcome!'. Start the first post immediately."
                )},
                {"role": "user", "content": prompt}
            ],
            temperature=1.1,
            presence_penalty=1.0,
            frequency_penalty=1.0
        )
        return response.choices[0].message.content
    else:
        # Fallback to standard OpenAI if needed, or raise exception
        raise ValueError("Azure OpenAI configuration is missing or invalid.")

def generate_image_for_post(prompt: str, brand_name: str = None, logo_path: str = None, website_url: str = None) -> str:
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
        import uuid
        image_prompt = (
            "Create a highly aesthetic, premium, and visually striking image suitable for a modern social media campaign. "
            "CRITICAL: There must be absolutely NO human faces or people in the image. The visuals must be strictly related to the core topic, objects, or abstract concepts from the context. "
            "Extract a very short, catchy 3-to-5 word hook or title from the following context and write it boldly and beautifully in the center of the image using modern typography. "
            "DO NOT write the brand name anywhere in the image, as a logo will be overlaid later. "
            f"UNIQUE BATCH ID: {uuid.uuid4()} "
            f"Context of the post: {prompt[:800]}"
        )
        
        try:
            response = client.images.generate(
                model=model_name,
                prompt=image_prompt,
                n=1,
                size="1024x1024"
            )
        except Exception as e:
            # If rejected by safety filter, fallback to a completely neutral generic prompt
            print(f"Initial image generation failed, retrying with safe fallback prompt. Error: {e}")
            try:
                fallback_prompt = (
                    "Create a highly aesthetic, premium, and visually striking abstract gradient background suitable for a modern social media campaign. "
                    "There must be absolutely NO human faces or people. Use beautiful calming colors."
                )
                response = client.images.generate(
                    model=model_name,
                    prompt=fallback_prompt,
                    n=1,
                    size="1024x1024"
                )
            except Exception as e2:
                print(f"Fallback AI generation also failed: {e2}")
                response = None
        
        if response and response.data and len(response.data) > 0:
            img_data = response.data[0]
        else:
            # Guaranteed fallback using Pillow
            img_data = None
            
        # 1. Get raw image bytes
        image_bytes = None
        if img_data:
            if getattr(img_data, 'b64_json', None):
                image_bytes = base64.b64decode(img_data.b64_json)
            elif getattr(img_data, 'url', None):
                resp = requests.get(img_data.url)
                if resp.status_code == 200:
                    image_bytes = resp.content
        
        if not image_bytes:
            # Generate a beautiful gradient fallback image using PIL
            print("Generating fallback gradient image locally...")
            import math
            img = Image.new('RGB', (1024, 1024))
            # Create a simple blue-purple gradient
            for y in range(1024):
                for x in range(1024):
                    r = int(255 * (x / 1024.0) * 0.5)
                    g = int(255 * (y / 1024.0) * 0.3)
                    b = int(255 * (0.5 + 0.5 * (x + y) / 2048.0))
                    img.putpixel((x, y), (r, g, b))
            
            output_io = io.BytesIO()
            img.save(output_io, format="PNG")
            image_bytes = output_io.getvalue()
            
        # 2. Add Watermark and Logo
        try:
            base_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            
            # Composite logo if available
            if logo_path and os.path.exists(logo_path):
                try:
                    logo_img = Image.open(logo_path).convert("RGBA")
                    target_width = int(base_img.width * 0.15)
                    aspect_ratio = logo_img.height / logo_img.width
                    target_height = int(target_width * aspect_ratio)
                    logo_img = logo_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    
                    padding = 30
                    position = (base_img.width - target_width - padding, padding)
                    base_img.alpha_composite(logo_img, dest=position)
                except Exception as comp_err:
                    print(f"Failed to overlay logo: {comp_err}")
            
            # Add jmstech.co at the bottom
            try:
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(base_img)
                if not website_url:
                    raise Exception("No website URL provided")
                domain = website_url.replace("https://", "").replace("http://", "").strip("/")
                if not domain.startswith("www."):
                    website_text = "www." + domain
                else:
                    website_text = domain
                try:
                    font = ImageFont.truetype("arialbd.ttf", 38)
                except:
                    font = ImageFont.load_default()
                    
                bbox = draw.textbbox((0, 0), website_text, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                
                text_x = 40
                text_y = base_img.height - text_h - 40
                
                # Draw text with subtle drop shadow for readability
                shadow_offset = 2
                draw.text((text_x + shadow_offset, text_y + shadow_offset), website_text, font=font, fill=(0, 0, 0, 180))
                draw.text((text_x, text_y), website_text, font=font, fill=(255, 255, 255, 255))
            except Exception as txt_err:
                print(f"Failed to draw website text: {txt_err}")
                
            output_io = io.BytesIO()
            base_img.save(output_io, format="PNG")
            image_bytes = output_io.getvalue()
        except Exception as e:
            print(f"Image modification failed: {e}")
            
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


def generate_content_with_gemini(prompt: str) -> str:
   
    from dotenv import load_dotenv
    import os
    import requests
    load_dotenv(override=True)
    api_key = os.environ.get("gemini_key")
    if not api_key:
        raise ValueError("Gemini API key (gemini_key) is missing in .env")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "system_instruction": {
            "parts": {
                # "text": "You are a top-tier expert social media manager. Write highly engaging, human-like social media posts."
                "text": (
                    "You are a top-tier Direct-Response Copywriter and Social Media Operations Director. "
                    "Write highly engaging, human-like social media posts that convert, drive engagement, and are engineered for social media feeds. "
                    "Use pattern-interrupt hooks (e.g., 3-second curiosity-gap headlines) and clear transition lines. "
                    "Maximize save-to-reach potential by delivering high-density value breakdowns."
                )
            }
        },
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    import time
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text']
        except requests.exceptions.HTTPError as e:
            if response.status_code in (429, 503) and attempt < 2:
                print(f"Retrying text generation due to {response.status_code}...")
                time.sleep(2 ** attempt)
                continue
            print(f"Error calling Gemini API for text: {e}")
            raise ValueError(f"Gemini API text generation failed: {e}")
        except Exception as e:
            print(f"Error calling Gemini API for text: {e}")
            raise ValueError(f"Gemini API text generation failed: {e}")


def generate_image_with_gemini(prompt: str, brand_name: str = None, logo_path: str = None) -> str:
    # Separate function to generate an image using Gemini's API (e.g. Imagen 3 if available on the key).
    from dotenv import load_dotenv
    import os
    import requests
    load_dotenv(override=True)
    api_key = os.environ.get("gemini_key")
    if not api_key:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/nano-banana-pro-preview:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }
    
    import time
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if 'candidates' in data and len(data['candidates']) > 0:
                parts = data['candidates'][0].get('content', {}).get('parts', [])
                if parts and 'inlineData' in parts[0]:
                    b64_img = parts[0]['inlineData'].get('data')
                    if b64_img:
                        import base64
                        import uuid
                        from django.conf import settings
                        
                        image_bytes = base64.b64decode(b64_img)
                        
                        # We can add logo compositing here if needed, similar to old code
                        
                        filename = f"gemini_img_{uuid.uuid4().hex[:8]}.png"
                        save_dir = os.path.join(settings.MEDIA_ROOT, 'ai_images')
                        os.makedirs(save_dir, exist_ok=True)
                        
                        filepath = os.path.join(save_dir, filename)
                        with open(filepath, 'wb') as f:
                            f.write(image_bytes)
                            
                        return f"{settings.MEDIA_URL}ai_images/{filename}"
            return None
        except requests.exceptions.HTTPError as e:
            if response.status_code in (429, 503) and attempt < 2:
                if hasattr(response, 'text') and 'quota' in response.text.lower():
                    break
                time.sleep(5)
                continue
            print(f"Error calling Gemini Image API: {e}")
            return "https://placehold.co/800x800/png?text=Fallback+Image+(Quota+Exceeded)"
        except Exception as e:
            print(f"Error calling Gemini Image API: {e}")
            return "https://placehold.co/800x800/png?text=Fallback+Image+(Quota+Exceeded)"
            
    return "https://placehold.co/800x800/png?text=Fallback+Image+(Quota+Exceeded)"


def generate_video_with_gemini(prompt: str) -> str:
    # Separate function to generate a video using Gemini's API.
    from dotenv import load_dotenv
    import os
    load_dotenv(override=True)
    api_key = os.environ.get("gemini_key")
    if not api_key:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/veo-3.1-fast-generate-preview:predictLongRunning?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "instances": [
            {"prompt": prompt}
        ],
        "parameters": {
            "sampleCount": 1
        }
    }
    
    import time
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if 'candidates' in data and len(data['candidates']) > 0:
                parts = data['candidates'][0].get('content', {}).get('parts', [])
                if parts and 'inlineData' in parts[0]:
                    b64_video = parts[0]['inlineData'].get('data')
                    if b64_video:
                        import base64
                        import uuid
                        from django.conf import settings
                        
                        video_bytes = base64.b64decode(b64_video)
                        
                        filename = f"gemini_video_{uuid.uuid4().hex[:8]}.mp4"
                        save_dir = os.path.join(settings.MEDIA_ROOT, 'ai_videos')
                        os.makedirs(save_dir, exist_ok=True)
                        
                        filepath = os.path.join(save_dir, filename)
                        with open(filepath, 'wb') as f:
                            f.write(video_bytes)
                            
                        return f"{settings.MEDIA_URL}ai_videos/{filename}"
            return None
        except requests.exceptions.HTTPError as e:
            if response.status_code in (429, 503) and attempt < 2:
                if hasattr(response, 'text') and 'quota' in response.text.lower():
                    break
                time.sleep(5)
                continue
            print(f"Error calling Gemini Video API: {e} - Response: {response.text}")
            return None
        except Exception as e:
            print(f"Error calling Gemini Video API: {e}")
            return None
            
    return None
