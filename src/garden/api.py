"""django-ninja API for receiving Google Sheets change notifications.

Stage 1: minimal receiver.  The endpoint authenticates the caller with a
shared API key and prints the received payload to the console.  Nothing is
persisted yet — that arrives in Stage 2 with the ``SheetChangeLog`` model.

The Google Apps Script sender (``Code.gs``) POSTs to
``/garden/api/sheets/webhook/`` with the API key in the ``X-API-Key`` header.
"""

import logging

from django.conf import settings
from ninja import NinjaAPI, Schema
from ninja.security import APIKeyHeader

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
    old_values: list[list[str | None]] | None = None
    new_values: list[list[str | None]] | None = None
    timestamp: str | None = None
    user_email: str | None = None


class SheetChangeOut(Schema):
    status: str
    message: str


@api.post('/sheets/webhook/', auth=ApiKeyAuth(), response=SheetChangeOut)
def sheets_webhook(request, payload: SheetChangeIn):
    """Receive a change notification from Google Sheets.

    Stage 1 does nothing with the data other than log it to the console.
    """
    logger.warning(
        'Google Sheets change received: sheet_name=%s range=%s key=%s user=%s timestamp=%s\n'
        '  old_values=%r\n  new_values=%r',
        payload.sheet_name,
        payload.range,
        payload.key,
        payload.user_email,
        payload.timestamp,
        payload.old_values,
        payload.new_values,
    )
    return SheetChangeOut(status='ok', message='Change received.')
