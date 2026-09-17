import requests
from bs4 import BeautifulSoup
import PyPDF2

def extract_text_from_url(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        # Extract text from paragraphs, headings, lists
        text = ' '.join([p.get_text(strip=True) for p in soup.find_all(['p', 'h1', 'h2', 'h3', 'li'])])
        return text[:5000] # Limit to 5000 chars
    except Exception as e:
        return ""

def extract_text_from_pdf(file_path):
    try:
        text = ""
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        return text[:10000] # Limit to 10k chars
    except Exception as e:
        return ""
