from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *

admin.site.register(Business)
admin.site.register(User, UserAdmin)
admin.site.register(BrandProfile)
admin.site.register(BrandAsset)
admin.site.register(MetaConnection)
admin.site.register(GeneratedPost)