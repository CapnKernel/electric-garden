FROM python:3.13-slim-trixie

ARG APP_UID

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=conf.settings

WORKDIR /app

COPY src/requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends uwsgi uwsgi-plugin-python3 && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

COPY src/ .

# Generate production local_settings.py from docker_settings.py
# settings.py imports local_settings.py at the bottom, so this
# makes all production overrides take effect automatically.
COPY src/conf/docker_settings.py conf/local_settings.py

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

RUN (id -u user 2>/dev/null || useradd ${APP_UID:+-u ${APP_UID}} -m user) && \
    mkdir -p /app/staticfiles /data/db /data/media /data/env /data/backups && \
    chown -R user:user /app /data

USER user

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
