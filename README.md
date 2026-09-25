# django-fresh

A planting management system for my vegetable garden, based on the
`django-fresh` template.

## What's included

FIXME

## Requirements

- Python 3.13+
- A virtual environment at `src/env/` (see below)
- Docker and Docker Compose for production deployment

## Local development

Local development runs without Docker.

1. Create and activate a virtual environment at `src/env/`:

   ```sh
   cd src
   python3 -m venv env
   source env/bin/activate
   pip install -r requirements.txt
   ```

2. Copy the settings and environment templates and customise them:

   ```sh
   cp conf/local_settings.py.template conf/local_settings.py
   cp .env.template .env
   ```

   Generate `SECRET_KEY` and `SHEETS_WEBHOOK_API_KEY` `.env`:

   ```sh
   python -c "import secrets, pathlib; p = pathlib.Path('.env'); p.write_text(''.join(line.replace('\"SECRET\"', '\"%s\"' % secrets.token_urlsafe(48)) for line in p.read_text().splitlines(keepends=True)))"
   ```

3. Run migrations and create a superuser:

   ```sh
   ./manage.py migrate
   ./manage.py createsuperuser
   ```

4. Start the development server:

   ```sh
   ./manage.py runserver
   ```

Use the virtual environment at `src/env/` for all local Python commands.
Do **not** use the system `python3` — it does not have the project
dependencies installed.

## Running tests

```sh
cd src
pytest
```

Pytest config is in `src/pytest.ini` (`DJANGO_SETTINGS_MODULE = conf.settings`).

## Google Sheets webhook

The Google Sheets → Django sync (see
[`plans/google_sheets_realtime_sync.md`](plans/google_sheets_realtime_sync.md))
receives changes at `POST /garden/api/sheets/webhook/`, authenticated with the
`X-API-Key` header matching `SHEETS_WEBHOOK_API_KEY` (set in `src/.env` locally,
and in `docker-compose.yml` on the VPS).  The Apps Script sender lives in
`AppsScript/`.

The `sheets_webhook_test` management command exercises the webhook.  Exactly
one of `--url` or `--in-process` is required:

```sh
cd src

# 1. Against the deployed VPS:
./manage.py sheets_webhook_test --url https://garden.afork.com/garden/api/sheets/webhook/

# 2. Against a local dev server (run `./manage.py runserver` first):
./manage.py sheets_webhook_test --url http://127.0.0.1:8000/garden/api/sheets/webhook/

# 3. In-process, with no server running (uses the Django test client):
./manage.py sheets_webhook_test --in-process
```

All three read the API key from `SHEETS_WEBHOOK_API_KEY` unless `--key` is
passed.  Use `--sheet-id`, `--range`, `--old-value` and `--new-value` to vary
the sample payload.

## Deployment

See [DOCKER.md](DOCKER.md) for the full Docker + Traefik deployment guide,
including DNS setup, `docker-compose.yml` examples for top-level and subpath
sites, backups, and day-to-day Docker management.

## Project layout

```
.
├── Dockerfile              # Production image (uWSGI)
├── docker-compose.yml      # Service, volumes, Traefik labels
├── entrypoint.sh           # Migrate, collectstatic, start uWSGI
├── DOCKER.md               # Docker deployment guide
├── pyproject.toml          # Ruff / djLint config
└── src/
    ├── manage.py
    ├── pytest.ini
    ├── requirements.txt
    ├── .env.template
    ├── app/                # Example app (views, wizard, templates, tests)
    ├── authuser/           # Custom user model + auth templates
    ├── conf/               # Settings, URLs, middleware, WSGI/ASGI
    └── static/             # Project-wide static files
```

## Code style

- Ruff is the linter and formatter (config in `pyproject.toml`).
- Line length 119; single quotes for internal strings.
- djLint is used for Django template linting.
