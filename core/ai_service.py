import os
from openai import AzureOpenAI

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

def generate_image_for_post(prompt: str) -> str:
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
        
        response = client.images.generate(
            model=model_name,
            prompt=image_prompt,
            n=1,
            size="1024x1024"
        )
        
        if response.data and len(response.data) > 0:
            img_data = response.data[0]
            if getattr(img_data, 'url', None):
                return img_data.url
            elif getattr(img_data, 'b64_json', None):
                import base64
                import uuid
                from django.conf import settings
                
                # Decode the base64 image
                image_bytes = base64.b64decode(img_data.b64_json)
                
                # Create a filename and ensure directory exists
                filename = f"generated_img_{uuid.uuid4().hex[:8]}.png"
                save_dir = os.path.join(settings.MEDIA_ROOT, 'ai_images')
                os.makedirs(save_dir, exist_ok=True)
                
                # Save the image to the media folder
                filepath = os.path.join(save_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(image_bytes)
                    
                # Return the URL to access it via Django
                return f"{settings.MEDIA_URL}ai_images/{filename}"
    except Exception as e:
        print(f"Image generation failed: {e}")
        
    return None
