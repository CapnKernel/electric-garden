/**
 * Google Apps Script sender for the Electric Garden Sheets sync.
 *
 * Install this in the bound script of the Google Sheet you want to sync.
 * An installable `onEdit` trigger calls `onSheetEdit`, which POSTs the change
 * to the Django webhook at `WEBHOOK_URL`.
 *
 * Setup:
 *   1. Open the Sheet -> Extensions -> Apps Script.
 *   2. Paste this file in as `Code.gs`.
 *   3. Project Settings -> Script properties, add:
 *        WEBHOOK_URL  = https://garden.afork.com/garden/api/sheets/webhook/
 *        WEBHOOK_KEY  = <the same value as SHEETS_WEBHOOK_API_KEY in Django>
 *   4. Triggers -> Add trigger -> onSheetEdit, From spreadsheet, On edit.
 *
 * Where to get WEBHOOK_KEY:
 *   On the VPS, entrypoint.sh generates the key on first start and stores it
 *   on the persistent /data/env volume.  Retrieve it with:
 *
 *       docker compose exec garden cat /data/env/sheets_webhook_api_key.txt
 *
 *   (It is also printed to the container log at startup.)  Paste that value
 *   into the WEBHOOK_KEY script property above.  See DOCKER.md for details.
 *
 * Note: `onEdit` is a simple trigger and cannot make external requests, so the
 * installable trigger above is required.
 */

/** Maximum number of retry attempts for a failed POST. */
var MAX_ATTEMPTS = 4;

/** Base delay (ms) for exponential backoff between retries. */
var BASE_BACKOFF_MS = 500;

/**
 * Installable onEdit trigger entry point.
 *
 * @param {Object} e The edit event object supplied by Apps Script.
 */
function onSheetEdit(e) {
  if (!e || !e.range) {
    return;
  }

  var props = PropertiesService.getScriptProperties();
  var url = props.getProperty('WEBHOOK_URL');
  var key = props.getProperty('WEBHOOK_KEY');

  if (!url || !key) {
    console.error('WEBHOOK_URL and WEBHOOK_KEY script properties must be set.');
    return;
  }

  var sheet = e.range.getSheet();
  var payload = {
    sheet_id: SpreadsheetApp.getActiveSpreadsheet().getId(),
    range: e.range.getA1Notation(),
    old_values: e.oldValue === undefined || e.oldValue === null ? null : [[e.oldValue]],
    new_values: e.value === undefined || e.value === null ? null : [[e.value]],
    timestamp: new Date().toISOString(),
    user_email: Session.getActiveUser().getEmail() || null,
  };

  postWithRetry(url, key, payload, sheet.getName());
}

/**
 * POST the payload to Django, retrying with exponential backoff.
 *
 * @param {string} url The webhook URL.
 * @param {string} key The API key sent in the X-API-Key header.
 * @param {Object} payload The JSON payload.
 * @param {string} sheetName Sheet name, used only for logging.
 */
function postWithRetry(url, key, payload, sheetName) {
  var options = {
    method: 'post',
    contentType: 'application/json',
    headers: { 'X-API-Key': key },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  };

  for (var attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      var response = UrlFetchApp.fetch(url, options);
      var code = response.getResponseCode();
      if (code >= 200 && code < 300) {
        console.log('Synced ' + sheetName + '!' + payload.range + ' (HTTP ' + code + ').');
        return;
      }
      console.error('Attempt ' + attempt + ' failed: HTTP ' + code + ' ' + response.getContentText());
    } catch (err) {
      console.error('Attempt ' + attempt + ' threw: ' + err);
    }

    if (attempt < MAX_ATTEMPTS) {
      Utilities.sleep(BASE_BACKOFF_MS * Math.pow(2, attempt - 1));
    }
  }

  console.error('Giving up after ' + MAX_ATTEMPTS + ' attempts for ' + sheetName + '!' + payload.range);
}
