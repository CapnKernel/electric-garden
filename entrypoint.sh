#!/bin/sh
set -e

# Persist SECRET_KEY across container restarts.
# Generate once per container, store on the persistent /data/env volume.
# On subsequent starts, read the stored key so sessions survive restarts.
SECRET_KEY_FILE="/data/env/secret_key.txt"
if [ -z "$SECRET_KEY" ]; then
    if [ -f "$SECRET_KEY_FILE" ]; then
        export SECRET_KEY="$(cat "$SECRET_KEY_FILE")"
    else
        export SECRET_KEY="$(openssl rand -base64 32)"
        echo "$SECRET_KEY" > "$SECRET_KEY_FILE"
    fi
fi

# Run database migrations
python manage.py migrate --noinput

# Collect static files into the shared static volume
python manage.py collectstatic --noinput --clear

# Start uwsgi
# uwsgi with --cheap: worker starts in cheap mode (minimal RAM).
# After --idle seconds of no requests, worker stops entirely.
# Next request spawns a fresh worker automatically.
# --workers 1: single worker to keep RAM usage minimal.
# SCRIPT_NAME is set via environment variable in docker-compose.yml.
# --mount: mounts the WSGI app at the SCRIPT_NAME prefix.  uWSGI
#   automatically sets SCRIPT_NAME in the WSGI environ and strips
#   it from PATH_INFO, so Django never sees the prefix.
# --manage-script-name: required for --mount to work correctly.
# --static-map: uWSGI serves static files directly, no nginx needed.
# --file-serve-mode: uWSGI handles X-Sendfile for protected media.
# The static-map URL prefix is always "/static/" regardless of
# SCRIPT_NAME.  uWSGI's --manage-script-name strips the mountpoint
# prefix from PATH_INFO before static file matching, so the URL
# prefix in --static-map must be the bare path, not the full URL.
# The filesystem path is always /app/static/ (the collectstatic dir).
MOUNTPOINT="${SCRIPT_NAME:-/}"
exec uwsgi --plugin python3 \
    --virtualenv /usr/local \
    --http-socket 0.0.0.0:8000 \
    --mount "${MOUNTPOINT}=conf.wsgi:application" \
    --manage-script-name \
    --static-map "/static/=/app/static/" \
    --file-serve-mode \
    --workers=1 \
    --cheap \
    --idle=300
