# Docker deployment

This guide walks through deploying **Electric Garden** behind [Traefik](https://github.com/CapnKernel/docker-traefik) on a VPS.  Traefik handles routing and automatic TLS certificates via Let's Encrypt.  The Django app runs in a container with uWSGI serving static files, authenticated media, and the app itself.

**User vs root:** Git commands (clone, pull, etc.) must be run as the **non-privileged user** that owns the app files.  Docker commands must be run as **root** (e.g. via `sudo` or a root shell).

## 1. Get Traefik running

Go to GitHub and [Create a PAT](https://github.com/settings/personal-access-tokens) (Personal Access Token) to clone [docker-traefik](https://github.com/CapnKernel/docker-traefik) with.  Give it read-only access to the contents and metadata permissions, and restrict it to the `docker-traefik` repo.

Now, clone (as the non-privileged user):

```sh
cd /home/user
git clone https://CapnKernel:PAT@github.com/CapnKernel/docker-traefik
cd docker-traefik
```

Then start Traefik (as root):

```sh
docker compose up -d
```

Verify Traefik is running:

```sh
docker ps
# Look for the traefik container, ports 80, 443, and 8080
```

Traefik will auto-discover other containers on the `shared_docker_network` network via Docker labels created by apps.

### Docker commands for traefik

(Run all of these from `~user/docker-traefik`)
```sh
# See Traefik logs
docker compose logs -f

# See Traefik status
docker compose ps

# Run / start Traefik
docker compose up -d

# Restart Traefik
docker compose restart

# Stop Traefik
docker compose down

# Rebuild and run Traefik (e.g. after config changes)
docker compose up -d --force-recreate
```

## 2. Set up DNS record

If you want a top level site, such as https://garden.example.com/, set up a DNS A or CNAME record with your DNS provider.

## 3. Clone the app

[Create a PAT](https://github.com/settings/personal-access-tokens) for authentication, with read-only access to the content and metadata permissions, and restricted to the `electric-garden` repo.  Then clone the Electric Garden repository onto the VPS:

```sh
# On the VPS, as the user who will own the app files:
git clone https://PAT@github.com/CapnKernel/electric-garden.git
cd ~/electric-garden
```

## 4. Configure the Django app

[`docker-compose.yml`](docker-compose.yml) is already set up for Electric Garden.  Review it and adjust the environment variables and Traefik labels for your deployment.

**Top-level site at `https://garden.example.com/` (current configuration)**

```yaml
name: garden
services:
  garden:
    build:
      context: .
      args:
        APP_UID: 1120 # Leave blank if you don't care about the uid/gid.
    image: garden:latest
    pull_policy: build
    container_name: garden_web
    volumes:
      - static:/app/static
      - data:/data
    environment:
      - DJANGO_SETTINGS_MODULE=conf.settings
      - SITE_NAME=Electric Garden
      - ALLOWED_HOSTS=garden.example.com,localhost
      # For a top-level site (e.g. garden.example.com/):
      - SCRIPT_NAME=
      # For a subpath site (e.g. vps.example.com/garden):
      # - SCRIPT_NAME=/garden
      - CSRF_TRUSTED_ORIGINS=https://garden.example.com
      - EMAIL_DEFAULT_FROM=noreply@example.com
      - EMAIL_HOST=
      - EMAIL_PORT=
      - EMAIL_HOST_USER=
      - EMAIL_HOST_PASSWORD=
      - DBBACKUP_HOSTNAME=garden
      # Shared secret for the Google Sheets webhook (App Script -> Django).
      # Leave as CHANGE_ME to have entrypoint.sh generate one on first start
      # (it is printed to the container log); or set your own value here.
      - SHEETS_WEBHOOK_API_KEY=CHANGE_ME
    networks:
      - shared_docker_network
    restart: unless-stopped
    labels:
      - "traefik.enable=true"
      # Top-level site: Host(`garden.example.com`)
      # Subpath site:   Host(`vps.example.com`) && PathPrefix(`/garden`)
      - "traefik.http.routers.garden.rule=Host(`garden.example.com`)"
      - "traefik.http.routers.garden.entrypoints=websecure"
      - "traefik.http.routers.garden.tls=true"
      - "traefik.http.routers.garden.tls.certresolver=letsencrypt"
      - "traefik.http.services.garden.loadbalancer.server.port=8000"

volumes:
  static:
  data:

networks:
  shared_docker_network:
    external: true
```

**Subpath site at `https://vps.example.com/garden` (alternative)**

To deploy under a subpath instead, uncomment `SCRIPT_NAME=/garden` and change the Traefik rule:

```yaml
    environment:
      - SITE_NAME=Electric Garden
      - ALLOWED_HOSTS=vps.example.com,localhost
      - SCRIPT_NAME=/garden
      - CSRF_TRUSTED_ORIGINS=https://vps.example.com
      - DBBACKUP_HOSTNAME=garden
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.garden.rule=Host(`vps.example.com`) && PathPrefix(`/garden`)"
      - "traefik.http.routers.garden.entrypoints=websecure"
      - "traefik.http.routers.garden.tls=true"
      - "traefik.http.routers.garden.tls.certresolver=letsencrypt"
      - "traefik.http.services.garden.loadbalancer.server.port=8000"
```

**Key configuration points:**

| Setting | Top-level | Subpath | Reason |
|---|---|---|---|
| `SCRIPT_NAME` | (empty) | `/garden` | Tells Django the URL prefix; uWSGI strips it from `PATH_INFO` so Django sees bare paths |
| `ALLOWED_HOSTS` | `garden.example.com,localhost` | `vps.example.com,localhost` | Must match the Host header Traefik forwards |
| `CSRF_TRUSTED_ORIGINS` | `https://garden.example.com` | `https://vps.example.com` | Required for POST requests over HTTPS |
| Traefik rule | `Host(\`garden.example.com\`)` | `Host(\`vps.example.com\`) && PathPrefix(\`/garden\`)` | Routes matching requests to this container |
| `SHEETS_WEBHOOK_API_KEY` | shared secret | shared secret | Authenticates the Google Sheets webhook (App Script → Django); must match the value in the Apps Script project |

## 5. Deploy the app

(as root):

```sh
cd ~/electric-garden
docker compose up -d
```

This will:
- Build the `garden:latest` image (install Python deps, copy code, set up uWSGI)
- Create the named volumes (`static`, `data`)
- Start the `garden_web` container on `shared_docker_network`
- Run migrations and collect static files on startup
- Traefik detects the new container via labels and starts routing traffic

## 6. Create a superuser

```sh
docker compose exec garden python manage.py createsuperuser --email admin@example.com
```

## 7. Verify

Use `curl` to check the site responds:

| Page | Top-level site | Subpath site |
|---|---|---|
| Main | `curl -sI https://localhost/ -H 'Host: garden.example.com' \| head -5` | `curl -sI https://localhost/garden/ -H 'Host: vps.example.com' \| head -5` |
| Admin | `curl -sI https://localhost/office/ -H 'Host: garden.example.com' \| head -5` | `curl -sI https://localhost/garden/office/ -H 'Host: vps.example.com' \| head -5` |

Expected: a `200` or `302` (redirect to login) response.

From your web browser:

- App (top-level): `https://garden.example.com/`
- Admin (top-level): `https://garden.example.com/office/`
- App (subpath): `https://vps.example.com/garden/`
- Admin (subpath): `https://vps.example.com/garden/office/`
- Traefik dashboard: `http://localhost:8080/` (use ssh port forwarding)

## 7a. Set up the Google Sheets webhook

The Google Sheets → Django sync receives changes at
`POST /garden/api/sheets/webhook/`, authenticated with the `X-API-Key` header.
The key is the shared secret `SHEETS_WEBHOOK_API_KEY`, which must match the
`WEBHOOK_KEY` script property in the Apps Script project.

### How the key is generated

[`entrypoint.sh`](entrypoint.sh) generates the key automatically on first
start if `SHEETS_WEBHOOK_API_KEY` is unset or left as `CHANGE_ME`.  It is
stored on the persistent `/data/env` volume (so it survives restarts and
updates) and **printed to the container log** so the deployer can copy it.

To use your own key instead, set `SHEETS_WEBHOOK_API_KEY` in
[`docker-compose.yml`](docker-compose.yml) and restart the container; the
explicit value takes precedence over the generated one.

### Retrieve the key

After the container is running, retrieve the key from the `/data/env` volume:

```sh
docker compose exec garden cat /data/env/sheets_webhook_api_key.txt
```

### Configure the Apps Script

In the Google Sheet, open **Extensions → Apps Script → Project Settings →
Script properties** and add:

| Property | Value |
|---|---|
| `WEBHOOK_URL` | `https://garden.example.com/garden/api/sheets/webhook/` |
| `WEBHOOK_KEY` | the key retrieved above |

[`Code.gs`](AppsScript/Code.gs) reads both with
`PropertiesService.getScriptProperties().getProperty(...)`.

Then add the installable trigger: **Triggers → Add trigger → `onSheetEdit`,
From spreadsheet, On edit**.  (A simple `onEdit` trigger cannot make external
requests, so the installable trigger is required.)

### Test the webhook

From the VPS host (the command needs the key, which is not visible to a
host-side `manage.py` unless you pass it):

```sh
docker compose exec garden python manage.py sheets_webhook_test --in-process
```

Or against the live URL, passing the key explicitly:

```sh
docker compose exec garden python manage.py sheets_webhook_test \
    --url https://garden.example.com/garden/api/sheets/webhook/ \
    --key "$(docker compose exec -T garden cat /data/env/sheets_webhook_api_key.txt)"
```

A successful run prints `HTTP 200` and `Webhook accepted the payload.`

## 8. Update the app

When you push changes to `electric-garden` on GitHub, pull and redeploy on the VPS.  Take a backup **before** and **after** the pull so you can roll back if anything goes wrong:

```sh
# 1. Back up the current database and media (as root)
docker compose exec garden python manage.py dbbackup
docker compose exec garden python manage.py mediabackup

# 2. Pull the latest code (as the non-privileged user that owns the app files)
cd ~/electric-garden
git pull

# 3. Rebuild the image and restart the container (as root)
docker compose up -d --build

# 4. Back up again after the update (as root)
docker compose exec garden python manage.py dbbackup
docker compose exec garden python manage.py mediabackup
```

What this does:
- The **before** backup captures the pre-update state, so you can restore it if the new version has problems.
- `git pull` fetches the latest code from GitHub into `~/electric-garden`.
- `docker compose up -d --build` rebuilds the `garden:latest` image from the new code, recreates the container, and restarts it.
- On startup the entrypoint runs `migrate` and `collectstatic` automatically, so schema and static-file changes are applied without extra steps.
- The **after** backup captures the post-migration state, so you have a clean restore point for the new version.
- Named volumes (`static`, `data`) are preserved, so your database, uploads, and secrets survive the update.

Notes:
- Run `git pull` as the **non-privileged user**; run the docker and backup commands as **root**.
- **No need to stop the app first.** `docker compose up -d --build` recreates the container in place (a rolling update), so the old container keeps serving until the new one is ready. `docker compose down` is only for fully stopping the app (e.g. maintenance) and is not required for an update.
- If you changed `docker-compose.yml` (e.g. environment variables or Traefik labels), the `--build` flag also recreates the container with the new config.
- To see the new version's logs while it starts up: `docker compose logs -f`.

## Deployment URL patterns

| Pattern | `SCRIPT_NAME` | Traefik rule |
|---|---|---|
| Top-level site | (empty) | `Host(\`garden.example.com\`)` |
| Subpath site | `/garden` | `Host(\`vps.example.com\`) && PathPrefix(\`/garden\`)` |

For a **top-level site** (e.g. `https://garden.example.com/`), set `SCRIPT_NAME=` (empty) and use a simple `Host()` rule.

For a **subpath site** (e.g. `https://vps.example.com/garden`), set `SCRIPT_NAME=/garden` and use `Host() && PathPrefix(/garden)`.  uWSGI's `--mount` + `--manage-script-name` handles prefix stripping.

## Configuration Reference

| Variable | Description |
|---|---|
| `DJANGO_SETTINGS_MODULE` | Always `conf.settings` |
| `SITE_NAME` | Display name in templates (currently `Electric Garden`) |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `SCRIPT_NAME` | URL prefix (empty for root, `/garden` for subpath) |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated origins |
| `EMAIL_DEFAULT_FROM` | From address for emails |
| `EMAIL_HOST` | SMTP server |
| `EMAIL_PORT` | SMTP port |
| `EMAIL_HOST_USER` | SMTP username |
| `EMAIL_HOST_PASSWORD` | SMTP password |
| `DBBACKUP_HOSTNAME` | Instance identifier in backup filenames (currently `garden`) |
| `SHEETS_WEBHOOK_API_KEY` | Shared secret authenticating the Google Sheets webhook (App Script → Django) |

## Docker management

All docker commands below must be run as **root** (e.g. via `sudo` or a root shell).  Git commands (clone, pull, etc.) should be run as the non-privileged user.

The app uses two named volumes:

| Volume name | Mount point | Access | Purpose |
|---|---|---|---|
| `static` | `/app/static/` | ro | Collected static files (CSS, JS, images) |
| `data` | `/data/` | rw | Everything else: the SQLite database (`/data/db/`), user-uploaded media (`/data/media/`), persistent secrets (`/data/env/`), and backups (`/data/backups/`) |

### Shell browsing
To browse the volumes, open a shell inside the container:

```sh
docker compose exec garden bash
```

Use standard commands to inspect:

```sh
# List files in a volume
ls -la /data/db/

# Read a file
cat /data/env/secret_key.txt

# Check database size
du -sh /data/db/
```

### Copying files in and out

```sh
# Copy a file into the container (e.g. restore a database backup)
docker cp ./backup.sql garden_web:/data/db/

# Copy a file out of the container (e.g. download a media file)
docker cp garden_web:/data/media/photo.jpg ./photo.jpg

# Copy the entire database out
docker cp garden_web:/data/db/db.sqlite3 ./db.sqlite3
```

### Backup and restore (compressed SQL)

The app uses [`django-dbbackup`](https://django-dbbackup.readthedocs.io/) to create **compressed SQL** backups of the database and archives of the media files.  Backups are written to the `/data/backups` directory (inside the `data` volume) and the latest 10 are kept automatically.

Run these as **root**:

```sh
# Back up the database (creates a gzip-compressed .sql file in /data/backups)
docker compose exec garden python manage.py dbbackup

# Back up the media files (creates a compressed archive in /data/backups)
docker compose exec garden python manage.py mediabackup

# List existing backups
docker compose exec garden python manage.py listbackups
```

Restore (as root):

```sh
# Restore the database from the most recent backup
docker compose exec garden python manage.py dbrestore

# Restore the database from a specific backup file
docker compose exec garden python manage.py dbrestore --backup-file /data/backups/garden-app-2026-01-01-000000.sql.gz

# Restore the media files from the most recent backup
docker compose exec garden python manage.py mediarestore
```

To copy a backup off the VPS for off-site storage:

```sh
docker cp garden_web:/data/backups/garden-app-2026-01-01-000000.sql.gz ./garden-backup.sql.gz
```

> **Note:** `dbrestore` replaces the current database.  It is safest to take a fresh `dbbackup` first, and to stop the app (`docker compose down`) before restoring so no writes occur mid-restore.

### Running tests

You can run the test suite inside the running container with `docker compose exec`.  Run these as **root**:

```sh
# Run the full suite
docker compose exec garden pytest

# Run a specific test file or directory
docker compose exec garden pytest garden/tests/test_api.py
docker compose exec garden pytest authuser/tests/

# Run a single test by node id
docker compose exec garden pytest garden/tests/test_api.py::test_name -v
```

Notes:

- The service name is `garden`, so `docker compose exec garden ...` targets the running container.  The container name is `garden_web` if you prefer `docker exec garden_web pytest`.
-
To run the tests in a throwaway container built from the same image (without touching the running production container):

```sh
docker compose run --rm --entrypoint pytest garden
```

This starts a fresh container from the `garden:latest` image, runs pytest, and removes it afterwards.

### Other commands

```sh
# See app logs
docker compose logs -f

# See app status
docker compose ps

# Stop the app (keeps volumes, network)
docker compose down

# Restart the app
docker compose restart

# Run / start the app (builds image if needed)
docker compose up -d

# Rebuild the image and start (after code changes)
docker compose up -d --build

# Run Django management commands
docker compose exec garden python manage.py check --deploy
docker compose exec garden python manage.py createsuperuser  --email admin@example.com

# Backup / restore the database and media (compressed SQL / archives)
# See "Backup and restore" above for details.
docker compose exec garden python manage.py listbackups
docker compose exec garden python manage.py dbbackup
docker compose exec garden python manage.py mediabackup
docker compose exec garden python manage.py dbrestore
docker compose exec garden python manage.py mediarestore

# Remove everything (volumes too — deletes database, media, secrets)
docker compose down -v
```

### Clean _everything_

This is the _nuke everything from orbit_ option.  It wipes out all images, containers, volumes and build objects for all apps, and traefik too.  Run as root, works from any directory.

```sh
# Nuke
docker stop $(docker ps -aq); docker rm $(docker ps -aq); docker rmi -f $(docker images -q); docker volume rm $(docker volume ls -q); docker system prune -af --volumes
# Verify
docker ps -a; echo '---'; docker images; echo '---'; docker volume ls; echo '---'; docker system df
```
