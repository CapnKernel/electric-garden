"""Send a test payload to the Google Sheets webhook endpoint.

Exercises the Stage 1 receiver end-to-end.  Exactly one of ``--url`` or
``--in-process`` must be given; there is no default target, so the command
never accidentally hits a live server.

Examples:
    # Against the deployed VPS:
    ./manage.py sheets_webhook_test --url https://garden.afork.com/garden/api/sheets/webhook/

    # Against a local dev server:
    ./manage.py sheets_webhook_test --url http://127.0.0.1:8000/garden/api/sheets/webhook/

    # In-process (no server needed), using the configured API key:
    ./manage.py sheets_webhook_test --in-process
"""

import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'POST a sample Google Sheets change payload to the webhook endpoint.'

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument(
            '--url',
            default=None,
            help='Webhook URL to POST to (e.g. https://garden.afork.com/garden/api/sheets/webhook/).',
        )
        target.add_argument(
            '--in-process',
            action='store_true',
            help='Use the Django test client instead of making a real HTTP request.',
        )
        parser.add_argument(
            '--key',
            default=None,
            help='API key to send in the X-API-Key header (default: SHEETS_WEBHOOK_API_KEY).',
        )
        parser.add_argument(
            '--sheet-id',
            default='test-sheet-id',
            help='Value for the sheet_id field.',
        )
        parser.add_argument(
            '--range',
            default='B2',
            help='Value for the range field.',
        )
        parser.add_argument(
            '--old-value',
            default='old',
            help='Value for the old_values field.',
        )
        parser.add_argument(
            '--new-value',
            default='new',
            help='Value for the new_values field.',
        )

    def handle(self, *args, **options):
        key = options['key'] or getattr(settings, 'SHEETS_WEBHOOK_API_KEY', None)
        if not key:
            raise CommandError('No API key available. Pass --key or set SHEETS_WEBHOOK_API_KEY in the environment.')

        payload = {
            'sheet_id': options['sheet_id'],
            'range': options['range'],
            'old_values': [[options['old_value']]],
            'new_values': [[options['new_value']]],
            'timestamp': '2026-09-25T00:00:00Z',
            'user_email': 'management-command@example.com',
        }

        if options['in_process']:
            self._post_in_process(payload, key)
        else:
            self._post_over_http(options['url'], payload, key)

    def _post_over_http(self, url, payload, key):
        body = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(
            url,
            data=body,
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'X-API-Key': key,
            },
        )
        self.stdout.write(f'POST {url}')
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                status = response.status
                text = response.read().decode('utf-8')
        except urllib.error.HTTPError as exc:
            status = exc.code
            text = exc.read().decode('utf-8', errors='replace')
        except urllib.error.URLError as exc:
            raise CommandError(f'Could not reach {url}: {exc.reason}') from exc

        self.stdout.write(f'HTTP {status}')
        self.stdout.write(text)
        if 200 <= status < 300:
            self.stdout.write(self.style.SUCCESS('Webhook accepted the payload.'))
        else:
            raise CommandError(f'Webhook rejected the payload (HTTP {status}).')

    def _post_in_process(self, payload, key):
        from django.test import Client

        client = Client()
        response = client.post(
            '/garden/api/sheets/webhook/',
            data=json.dumps(payload),
            content_type='application/json',
            headers={'X-API-Key': key},
        )
        self.stdout.write(f'HTTP {response.status_code}')
        self.stdout.write(response.content.decode('utf-8'))
        if 200 <= response.status_code < 300:
            self.stdout.write(self.style.SUCCESS('Webhook accepted the payload.'))
        else:
            raise CommandError(f'Webhook rejected the payload (HTTP {response.status_code}).')
