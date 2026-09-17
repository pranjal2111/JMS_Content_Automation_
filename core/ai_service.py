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
