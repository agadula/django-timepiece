from .base import *
from .ldap_auth import *


DEBUG = True

TEMPLATE_DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'timepiece',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
}

INTERNAL_IPS = ('127.0.0.1',)

# Email addresses to send notices to, e.g. when pending contract hours
# are entered.
#TIMEPIECE_ACCOUNTING_EMAILS = ["accounting@example.com"]

# Whether links in emails should use https
# Default is True
#TIMEPIECE_EMAILS_USE_HTTPS = True
