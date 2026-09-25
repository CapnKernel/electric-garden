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
  // console.log('onSheetEdit triggered at ' + new Date().toISOString());

  if (!e || !e.range) {
    // console.log('No edit range in event; ignoring (not a cell edit).');
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
  // console.log(
  //   'Edit on sheet "' + sheet.getName() + '" range ' + e.range.getA1Notation() +
  //   ' (old=' + JSON.stringify(e.oldValue) + ', new=' + JSON.stringify(e.value) + ')'
  // );

  var payload = {
    sheet_name: sheet.getName(),
    range: e.range.getA1Notation(),
    old_values: e.oldValue === undefined || e.oldValue === null ? null : [[e.oldValue]],
    new_values: e.value === undefined || e.value === null ? null : [[e.value]],
    timestamp: new Date().toISOString(),
    user_email: Session.getActiveUser().getEmail() || null,
  };

  // The header of the edited column (row 1) names the field to update.  Only
  // meaningful for a single-column edit; omitted otherwise.
  if (e.range.getNumColumns() === 1) {
    var header = sheet.getRange(1, e.range.getColumn()).getValue();
    if (header !== '' && header !== null && header !== undefined) {
      payload.column_name = String(header);
      console.log('Column name: ' + JSON.stringify(payload.column_name));
    }
  }

  // Column A holds the row key.  Include it only when the edit is a single
  // cell or lies within one row (i.e. does not span multiple rows) and the
  // A cell is non-empty.  Otherwise the "key" property is omitted entirely.
  if (e.range.getNumRows() === 1) {
    var rowKey = sheet.getRange(e.range.getRow(), 1).getValue();
    if (rowKey !== '' && rowKey !== null && rowKey !== undefined) {
      payload.key = String(rowKey);
      // console.log('Row key: ' + JSON.stringify(payload.key));
    } else {
      // console.log('Row key is empty; omitting "key" from payload.');
    }
  } else {
    // console.log('Edit spans multiple rows; omitting "key" from payload.');
  }

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

  // console.log('POSTing to ' + url + ' for ' + sheetName + '!' + payload.range);

  for (var attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    // console.log('Attempt ' + attempt + ' of ' + MAX_ATTEMPTS + '...');
    try {
      var response = UrlFetchApp.fetch(url, options);
      var code = response.getResponseCode();
      var body = response.getContentText();
      if (code >= 200 && code < 300) {
        // console.log('Synced ' + sheetName + '!' + payload.range + ' (HTTP ' + code + '): ' + body);
        return;
      }
      console.error('Attempt ' + attempt + ' failed: HTTP ' + code + ' ' + body);
    } catch (err) {
      console.error('Attempt ' + attempt + ' threw: ' + err);
    }

    if (attempt < MAX_ATTEMPTS) {
      var delay = BASE_BACKOFF_MS * Math.pow(2, attempt - 1);
      // console.log('Retrying in ' + delay + ' ms...');
      Utilities.sleep(delay);
    }
  }

  console.error('Giving up after ' + MAX_ATTEMPTS + ' attempts for ' + sheetName + '!' + payload.range);
}

/**
 * Manual test caller for `onSheetEdit`.
 *
 * Run this from the Apps Script editor (select `testOnSheetEdit` and press Run)
 * to exercise the full webhook path without editing the Sheet.  It builds a
 * fake edit event using a real range from the active spreadsheet, so
 * `e.range.getSheet()` and `e.range.getA1Notation()` work as they do for a
 * genuine edit.
 *
 * Adjust A1_NOTATION / OLD_VALUE / NEW_VALUE below to taste.
 */
function testOnSheetEdit() {
  var A1_NOTATION = 'B2';
  var OLD_VALUE = 'old';
  var NEW_VALUE = 'new';

  var range = SpreadsheetApp.getActiveSpreadsheet().getRange(A1_NOTATION);
  var fakeEvent = {
    range: range,
    oldValue: OLD_VALUE,
    value: NEW_VALUE,
  };

  console.log('Calling onSheetEdit with a fake event for range ' + A1_NOTATION + '.');
  onSheetEdit(fakeEvent);
}
