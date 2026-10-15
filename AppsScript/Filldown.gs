/**
 * Cell-edit handling.
 *
 * The installable `onEdit` trigger calls `onCellEdit`.  When a single cell in
 * one of the tracked sheets is edited, each content modifier in
 * `FILLDOWN_MODIFIERS` is given the chance to act on the edit.
 *
 * Setup:
 *   1. Project Settings -> Script properties, add:
 *        FILLDOWN_ENABLED = 1
 *   2. Triggers -> Add trigger -> onCellEdit, From spreadsheet, On edit.
 *
 * Modifiers only run if FILLDOWN_ENABLED is set to 1.  Set it to 0 to disable.
 */

/** Sheets whose edits trigger a fill-down. */
var FILLDOWN_SHEET_NAMES = ['Plants', 'Packets', 'Plantings'];

/** Sentinel value that marks a cell as "fill me in from above". */
var FILLDOWN_SENTINEL = '"';

/**
 * Content modifiers applied, in order, to each qualifying edit.
 *
 * Each modifier is a function `(e) => void` that may modify the sheet in
 * response to the edit event `e`.
 */
var FILLDOWN_MODIFIERS = [onEditDoDitto, onEditSetNote];

/**
 * Installable onEdit trigger entry point.
 *
 * Applies each content modifier to a qualifying edit.  Only acts on
 * single-cell edits in one of the tracked sheets, below the header row.
 *
 * @param {Object} e The edit event object supplied by Apps Script.
 */
function onCellEdit(e) {
  if (!e || !e.range) {
    Logger.log('onCellEdit: no event or range; aborting.');
    return;
  }

  Logger.log(
    'onCellEdit: sheet=%s row=%s col=%s value=%s (type=%s)',
    e.range.getSheet().getName(),
    e.range.getRow(),
    e.range.getColumn(),
    e.value,
    typeof e.value
  );

  // Only operate when the enable property is the numeric 1.
  var enabled = PropertiesService.getScriptProperties().getProperty('FILLDOWN_ENABLED');
  if (enabled !== '1') {
    Logger.log('onCellEdit: FILLDOWN_ENABLED=%s; aborting.', enabled);
    return;
  }

  var sheet = e.range.getSheet();
  if (!sheet || FILLDOWN_SHEET_NAMES.indexOf(sheet.getName()) === -1) {
    Logger.log('onCellEdit: sheet not tracked; aborting.');
    return;
  }

  // Only handle a single-cell edit.
  if (e.range.getNumRows() !== 1 || e.range.getNumColumns() !== 1) {
    Logger.log('onCellEdit: not a single-cell edit; aborting.');
    return;
  }

  // Row 1 is the header row; never fill down from it.
  if (e.range.getRow() < 2) {
    Logger.log('onCellEdit: header row; aborting.');
    return;
  }

  for (var i = 0; i < FILLDOWN_MODIFIERS.length; i++) {
    Logger.log('onCellEdit: running modifier %s', FILLDOWN_MODIFIERS[i].name);
    FILLDOWN_MODIFIERS[i](e);
  }
}

/**
 * Map a value for fill-down.
 *
 * Passes the value through unchanged, except when the edit is in the "Packet"
 * column of the "Plantings" sheet and the value is of the form `P=` followed by
 * a number between 100 and 999 inclusive, in which case the number is
 * incremented, e.g. `P=263` -> `P=264`.
 *
 * @param {*} value The value to map.
 * @param {Object} e The edit event object supplied by Apps Script.
 * @return {*} The mapped value.
 */
function filldownValueMapper(value, e) {
  if (!isPlantingsPacketCell(e)) {
    return value;
  }

  var match = String(value).match(/^P=(\d+)$/);
  if (match) {
    var number = parseInt(match[1], 10);
    if (number >= 100 && number <= 999) {
      return 'P=' + (number + 1);
    }
  }
  return value;
}

/**
 * Whether the edit event targets the "Packet" column of the "Plantings" sheet.
 *
 * @param {Object} e The edit event object supplied by Apps Script.
 * @return {boolean} True when the edit is in the Plantings "Packet" column.
 */
function isPlantingsPacketCell(e) {
  if (!e || !e.range) {
    return false;
  }
  var sheet = e.range.getSheet();
  if (!sheet || sheet.getName() !== 'Plantings') {
    return false;
  }
  var header = sheet.getRange(1, e.range.getColumn()).getValue();
  return String(header) === 'Packet';
}

/**
 * "Ditto" content modifier.
 *
 * If the edited cell's new value is the sentinel `"`, it is replaced with the
 * mapped value of the cell above it.  Nothing happens when the cell above is
 * blank or itself the sentinel.
 *
 * Otherwise, if the edited cell's new value is not empty, the column is walked
 * downwards from the edited cell.  Each following cell whose value is the
 * sentinel `"` is replaced with the mapped value of the cell above it, and the
 * walk continues until a following cell is not the sentinel.
 *
 * @param {Object} e The edit event object supplied by Apps Script.
 */
function onEditDoDitto(e) {
  var sheet = e.range.getSheet();
  var row = e.range.getRow();
  var col = e.range.getColumn();
  var value = e.value;

  Logger.log(
    'onEditDoDitto: row=%s col=%s value=%s sentinel=%s isSentinel=%s',
    row,
    col,
    value,
    FILLDOWN_SENTINEL,
    value === FILLDOWN_SENTINEL
  );

  // Determine the value to start filling from.
  var fillValue;
  if (value === FILLDOWN_SENTINEL) {
    // Sentinel in the edited cell: take the mapped value from the cell above.
    var aboveRange = sheet.getRange(row - 1, col);
    var above = aboveRange.getValue();
    if (above === undefined || above === null || above === '' || above === FILLDOWN_SENTINEL) {
      Logger.log('onEditDoDitto: sentinel edit but cell above is blank/sentinel; nothing to copy.');
      return;
    }
    fillValue = filldownValueMapper(above, e);
    Logger.log('onEditDoDitto: sentinel edit; above=%s mapped=%s', above, fillValue);
    e.range.setValue(fillValue);
    aboveRange.copyFormatToRange(sheet, col, col, row, row);
    // Advance so the next cell down continues the sequence.
    fillValue = filldownValueMapper(fillValue, e);
  } else if (value === undefined || value === null || value === '') {
    // Empty edit: nothing to fill down.
    Logger.log('onEditDoDitto: empty edit; nothing to fill down.');
    return;
  } else {
    fillValue = filldownValueMapper(value, e);
  }

  // Walk down the column, filling sentinel cells until a non-sentinel is found.
  Logger.log('onEditDoDitto: walking down from row=%s with fillValue=%s', row, fillValue);
  var offset = 1;
  while (true) {
    var targetRow = row + offset;
    var below = sheet.getRange(targetRow, col);
    var belowValue = below.getValue();
    Logger.log(
      'onEditDoDitto: walk step %s -> row=%s belowValue=%s (isSentinel=%s)',
      offset,
      targetRow,
      belowValue,
      belowValue === FILLDOWN_SENTINEL
    );
    if (belowValue !== FILLDOWN_SENTINEL) {
      Logger.log('onEditDoDitto: row=%s is not sentinel; stopping walk.', targetRow);
      break;
    }
    Logger.log('onEditDoDitto: row=%s filling with %s', targetRow, fillValue);
    below.setValue(fillValue);
    // Copy the format of the cell above into the filled cell.
    sheet.getRange(targetRow - 1, col).copyFormatToRange(sheet, col, col, targetRow, targetRow);
    Logger.log('onEditDoDitto: row=%s format copied from row=%s', targetRow, targetRow - 1);
    fillValue = filldownValueMapper(fillValue, e);
    Logger.log('onEditDoDitto: next fillValue=%s', fillValue);
    offset++;
  }
  Logger.log('onEditDoDitto: walk finished after %s step(s).', offset - 1);
}

/**
 * "Set note" content modifier.
 *
 * When the edited value is of the form `P=` followed by a number, the note of
 * the edited cell is set to a looked-up name:
 *   - number 0-99: the "Name" of the `Plants` row whose "Barcode" matches.
 *   - number 100-999: the "Full name" of the `Packets` row whose "Barcode"
 *     matches.
 *
 * Does nothing when the edited cell is in the "Barcode" column.
 *
 * @param {Object} e The edit event object supplied by Apps Script.
 */
function onEditSetNote(e) {
  var sheet = e.range.getSheet();
  var col = e.range.getColumn();
  var value = e.value;

  Logger.log('onEditSetNote: sheet=%s col=%s value=%s', sheet.getName(), col, value);

  // A sentinel edit is resolved by Ditto; read the resulting cell value so the
  // note reflects the calculated value rather than the sentinel.
  if (value === FILLDOWN_SENTINEL) {
    value = e.range.getValue();
    Logger.log('onEditSetNote: sentinel edit; resolved value=%s', value);
  }

  if (value === undefined || value === null || value === '') {
    Logger.log('onEditSetNote: empty value; nothing to do.');
    return;
  }

  // Never set a note on the Barcode column itself.
  var header = String(sheet.getRange(1, col).getValue());
  if (header === 'Barcode') {
    Logger.log('onEditSetNote: cell is in the Barcode column; nothing to do.');
    return;
  }

  // Container barcodes: expand to the container name.
  if (/^PC=\d+$/.test(String(value))) {
    var containerName = lookupValueByBarcode('Containers', 'Name', value);
    Logger.log('onEditSetNote: container lookup for %s -> %s', value, containerName);
    if (containerName !== null) {
      e.range.setNote(containerName);
      Logger.log('onEditSetNote: note set to %s', containerName);
    } else {
      Logger.log('onEditSetNote: no matching container found; note not set.');
    }
    return;
  }

  var match = String(value).match(/^P=(\d+)$/);
  if (!match) {
    Logger.log('onEditSetNote: value does not match P=<number>; nothing to do.');
    return;
  }

  var number = parseInt(match[1], 10);
  var note = null;

  if (number >= 0 && number <= 99) {
    Logger.log('onEditSetNote: looking up Plants "Name" for barcode %s', value);
    var plantName = lookupValueByBarcode('Plants', 'Name', value);
    var plantCode = lookupValueByBarcode('Plants', 'Code', value);
    if (plantName !== null) {
      note = plantCode + ': ' + plantName;
    }
  } else if (number >= 100 && number <= 999) {
    Logger.log('onEditSetNote: looking up Packets "Full name" for barcode %s', value);
    var packetFullName = lookupValueByBarcode('Packets', 'Full name', value);
    // The Packets sheet has no code column; resolve the code via the Plants
    // sheet using the packet's "Plant" barcode.
    var plantBarcode = lookupValueByBarcode('Packets', 'Plant', value);
    var packetCode = plantBarcode !== null
      ? lookupValueByBarcode('Plants', 'Code', plantBarcode)
      : null;
    if (packetFullName !== null) {
      note = packetCode + ': ' + packetFullName;
    }
  } else {
    Logger.log('onEditSetNote: number %s out of range; nothing to do.', number);
    return;
  }

  Logger.log('onEditSetNote: lookup result note=%s', note);

  if (note !== null) {
    e.range.setNote(note);
    Logger.log('onEditSetNote: note set to %s', note);
  } else {
    Logger.log('onEditSetNote: no matching row found; note not set.');
  }
}

/**
 * Look up a value in a sheet by matching the "Barcode" column.
 *
 * @param {string} sheetName The name of the sheet to search.
 * @param {string} resultHeader The header of the column whose value to return.
 * @param {string} barcode The barcode value to match.
 * @return {string|null} The matched value, or null if not found.
 */
function lookupValueByBarcode(sheetName, resultHeader, barcode) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName);
  if (!sheet) {
    Logger.log('lookupValueByBarcode: sheet "%s" not found.', sheetName);
    return null;
  }

  var lastRow = sheet.getLastRow();
  var lastCol = sheet.getLastColumn();
  Logger.log('lookupValueByBarcode: sheet=%s lastRow=%s lastCol=%s', sheetName, lastRow, lastCol);
  if (lastRow < 2 || lastCol < 1) {
    Logger.log('lookupValueByBarcode: sheet "%s" has no data rows.', sheetName);
    return null;
  }

  var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  var barcodeCol = headers.indexOf('Barcode') + 1;
  var resultCol = headers.indexOf(resultHeader) + 1;
  Logger.log(
    'lookupValueByBarcode: headers=%s barcodeCol=%s resultCol=%s',
    headers,
    barcodeCol,
    resultCol
  );
  if (barcodeCol < 1 || resultCol < 1) {
    Logger.log('lookupValueByBarcode: missing "Barcode" or "%s" column.', resultHeader);
    return null;
  }

  var barcodes = sheet.getRange(2, barcodeCol, lastRow - 1, 1).getValues();
  for (var i = 0; i < barcodes.length; i++) {
    if (String(barcodes[i][0]) === String(barcode)) {
      var found = String(sheet.getRange(i + 2, resultCol).getValue());
      Logger.log('lookupValueByBarcode: matched barcode %s at row %s -> %s', barcode, i + 2, found);
      return found;
    }
  }

  Logger.log('lookupValueByBarcode: no row matched barcode %s.', barcode);
  return null;
}
