# Project context for AI coding assistants

This file provides persistent context that should be read at the start of every
session. Keep it up to date as the project evolves.

## Project overview

Django project for managing planting in a garden. The Django app
lives under `src/`. Production runs in Docker (see `Dockerfile` and
`docker-compose.yml`); local development runs without Docker.

## Virtual environment

The Python virtual environment is at `src/env/`.

Use it for all local Python commands (tests, manage.py, etc.):

```sh
cd src
pytest
./manage.py runserver
```

Do NOT use the system `python3` — it does not have the project dependencies
installed (e.g. Django).

## Running tests

```sh
cd src
pytest
```

Pytest config is in `src/pytest.ini` (`DJANGO_SETTINGS_MODULE = conf.settings`).

Do not offer to run all tests unless asked.

## Settings / configuration

- `src/conf/settings.py` — base settings.
- `src/conf/local_settings.py` — local dev overrides (gitignored; copy from
  `src/conf/local_settings.py.template`).
- `src/conf/docker_settings.py` — production overrides; copied to
  `local_settings.py` during the Docker build.
- `src/.env` — local environment variables (copy from `src/.env.template`).

## Code style

- Ruff is the linter and formatter (config in `pyproject.toml`).
- Line length 119; single quotes for internal strings.
- `djlint` is used for Django template linting.
- VSCode is configured to use ruff as the Python formatter (see
  `.vscode/settings.json`, which is gitignored/local-only).

## Important

- As far as possible, suggest all changes to one file in one `apply_diff`.
  Do not use multiple `apply_diff`s on the same file for one concern unless unavoidable.
- On the VPS, do _not_ run git commands as root.  Run them as user `user`.

