# Production settings for Docker deployment.
#
# During Docker build, this file is copied to local_settings.py
# (see the Dockerfile COPY command).  The existing settings.py
# imports local_settings.py at the bottom, so all overrides here
# take effect automatically.
#
# For local development, settings.py loads your own local_settings.py,
# which should be copied from local_settings.py.template.

import os
from pathlib import Path

import dj_database_url
from django.conf import global_settings

BASE_DIR = Path(__file__).resolve().parent.parent

SITE_ID = 1

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Pick one
# DEPLOY_TYPE = "dev"
# DEPLOY_TYPE = "test"
DEPLOY_TYPE = 'prod'

# ALLOWED_HOSTS is set via environment variable at deploy time.
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')

# SCRIPT_NAME is set via environment variable in docker-compose.yml.
# This is a deployment detail, not hardcoded in the image.
# --manage-script-name in entrypoint.sh strips SCRIPT_NAME from
# PATH_INFO at the uWSGI level, so Django never sees the prefix.
SCRIPT_NAME = os.environ.get('SCRIPT_NAME', '')

DATABASES = {
    'default': dj_database_url.config(default=f'sqlite:////data/db/db.sqlite3'),
}

STATIC_ROOT = '/app/static'
# Override STATICFILES_DIRS from settings.py — in Docker, STATIC_ROOT
# is the same as the app's static source directory, so including it
# in STATICFILES_DIRS would cause a circular reference error.
STATICFILES_DIRS = []
STATIC_URL = f'{SCRIPT_NAME}/static/'
MEDIA_ROOT = '/data/media/'
MEDIA_URL = f'{SCRIPT_NAME}/media/'

ADMINS = [('Mitch Davis', 'mjd@garden.example.com')]
EMAIL_DEFAULT_FROM = os.environ.get('EMAIL_DEFAULT_FROM')

# Shared secret for the Google Sheets webhook (App Script -> Django).
# Must match the WEBHOOK_KEY script property in the Apps Script project.
SHEETS_WEBHOOK_API_KEY = os.environ.get('SHEETS_WEBHOOK_API_KEY')

# Display name for this instance in templates. Set at deploy time.
SITE_NAME = os.environ.get('SITE_NAME', 'Electric Garden')

STORAGES = dict(global_settings.STORAGES)
STORAGES['dbbackup'] = {
    'BACKEND': 'django.core.files.storage.FileSystemStorage',
    'OPTIONS': {
        'location': '/data/backups',
    },
}

# DBBACKUP_HOSTNAME identifies this instance in backup filenames.
# Set via environment variable at deploy time (e.g. 'app2', 'app3').
DBBACKUP_HOSTNAME = os.environ.get('DBBACKUP_HOSTNAME', 'app')
DBBACKUP_FILENAME_TEMPLATE = '{servername}-app-{datetime}.sql'
DBBACKUP_CLEANUP_KEEP = 10
DBBACKUP_CONNECTOR_MAPPING = {
    'django.db.backends.sqlite3': 'dbbackup.db.sqlite.SqliteConnector',
}

# Proxy settings for running behind Traefik
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# CSRF_TRUSTED_ORIGINS is set via environment variable at deploy time.
CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS', 'http://localhost').split(',')

# Update auth URLs to account for the SCRIPT_NAME prefix
LOGIN_URL = f'{SCRIPT_NAME}/accounts/login/'
LOGIN_REDIRECT_URL = SCRIPT_NAME or '/'
LOGOUT_REDIRECT_URL = SCRIPT_NAME or '/'
