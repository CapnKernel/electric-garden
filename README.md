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

   Generate `SECRET_KEY` in `.env`:

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
