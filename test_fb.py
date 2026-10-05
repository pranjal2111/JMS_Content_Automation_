import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jms_backend.settings')
django.setup()

from core.models import MetaConnection
from core.meta_service import GRAPH_API_URL
import requests
import json

c = MetaConnection.objects.first()
print(c.ad_account_id)

