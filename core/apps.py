from django.apps import AppConfig
import os

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # Start the scheduler only in the main thread (avoids running twice with runserver)
        if os.environ.get('RUN_MAIN', None) == 'true' or not os.environ.get('SERVER_SOFTWARE', '').startswith('WSGIServer'):
            from . import scheduler
            scheduler.start_scheduler()
