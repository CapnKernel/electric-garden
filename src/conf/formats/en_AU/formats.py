"""Project display formats for Australian English.

Django consults locale format modules (``FORMAT_MODULE_PATH``) before falling
back to ``settings.DATE_FORMAT``, so mirroring the setting here makes
``{{ value|date }}`` and ``date_format()`` use it without every template having
to specify the format.  ``settings.DATE_FORMAT`` remains the single source of
truth.
"""

from django.conf import settings

DATE_FORMAT = settings.DATE_FORMAT
SHORT_DATE_FORMAT = settings.DATE_FORMAT
