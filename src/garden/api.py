"""django-ninja API for receiving Google Sheets change notifications.

Stage 2: every valid delivery is persisted as a ``SheetChangeLog`` row with
status ``"pending"`` so nothing is lost and each change can be replayed or
reconciled later.  The endpoint authenticates the caller with a shared API key.

The Google Apps Script sender (``Code.gs``) POSTs to
``/garden/api/sheets/webhook/`` with the API key in the ``X-API-Key`` header.
"""

import logging
from datetime import datetime

from django.conf import settings
from django.utils.dateparse import parse_datetime
from ninja import NinjaAPI, Schema
from ninja.security import APIKeyHeader

from .models import SheetChangeLog

logger = logging.getLogger(__name__)

api = NinjaAPI(
    title='Electric Garden Sheets API',
    version='1.0.0',
    urls_namespace='garden_api',
)


class ApiKeyAuth(APIKeyHeader):
    """Validate the ``X-API-Key`` header against ``SHEETS_WEBHOOK_API_KEY``."""

    param_name = 'X-API-Key'

    def __call__(self, request):
        # Declare the security scheme so the OpenAPI docs (Swagger UI) show an
        # "Authorize" button for entering the API key.
        self.openapi_scheme = {
            'type': 'apiKey',
            'in': 'header',
            'name': self.param_name,
        }
        return super().__call__(request)

    def authenticate(self, request, key):
        expected = getattr(settings, 'SHEETS_WEBHOOK_API_KEY', None)
        if not expected:
            # Fail closed: without a configured key, reject every request.
            logger.error('SHEETS_WEBHOOK_API_KEY is not configured; rejecting webhook request.')
            return None
        if key == expected:
            return key
        return None


class SheetChangeIn(Schema):
    """Payload sent by the Google Apps Script ``onEdit`` trigger."""

    sheet_name: str
    range: str
    key: str | None = None
    column_name: str | None = None
    old_values: list[list[str | None]] | None = None
    new_values: list[list[str | None]] | None = None
    timestamp: str | None = None
    user_email: str | None = None


class SheetChangeOut(Schema):
    status: str
    message: str
    tracking_id: int


def _parse_timestamp(value):
    """Parse the Apps Script ISO-8601 timestamp, returning ``None`` if unusable."""
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            logger.warning('Could not parse timestamp %r; storing null.', value)
            return None
    return parsed


@api.post('/sheets/webhook/', auth=ApiKeyAuth(), response=SheetChangeOut)
def sheets_webhook(request, payload: SheetChangeIn):
    """Receive a change notification from Google Sheets and log it.

    Every valid delivery is stored as a ``SheetChangeLog`` row with status
    ``"pending"``; the row's primary key is returned as the tracking ID.
    """
    change = SheetChangeLog.objects.create(
        sheet_name=payload.sheet_name,
        range=payload.range,
        key=payload.key,
        column_name=payload.column_name,
        old_values=payload.old_values,
        new_values=payload.new_values,
        edit_timestamp=_parse_timestamp(payload.timestamp),
        user_email=payload.user_email,
        status=SheetChangeLog.Status.PENDING,
    )
    logger.warning(
        'Google Sheets change logged: id=%s sheet_name=%s range=%s key=%s column=%s user=%s timestamp=%s',
        change.pk,
        payload.sheet_name,
        payload.range,
        payload.key,
        payload.column_name,
        payload.user_email,
        payload.timestamp,
    )
    return SheetChangeOut(status='ok', message='Change received.', tracking_id=change.pk)
