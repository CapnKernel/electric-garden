// Flatpickr initialisation for ``.datepicker`` inputs.
//
// The date picker is initialised on page load and after every htmx swap,
// because swapped-in content does not run its own inline scripts.

// Initialise Flatpickr on any ``.datepicker`` inputs within ``root``.
function initDatePickers(root) {
    if (typeof flatpickr === 'undefined') {
        // Flatpickr failed to load (e.g. the CDN is unreachable); leave the
        // plain text inputs as-is rather than throwing.
        return;
    }
    (root || document).querySelectorAll('input.datepicker:not(.flatpickr-input)').forEach(function (el) {
        flatpickr(el, {
            dateFormat: 'Y-m-d',
            altInput: true,
            altFormat: 'j-M-y',
            allowInput: true,
        });
    });
}

// Set a date input (and its Flatpickr instance) to today.
function setToday(id) {
    var el = document.getElementById(id);
    if (!el) {
        return;
    }
    if (el._flatpickr) {
        el._flatpickr.setDate(new Date(), true);
    } else {
        var now = new Date();
        el.value = now.getFullYear() + '-' +
            String(now.getMonth() + 1).padStart(2, '0') + '-' +
            String(now.getDate()).padStart(2, '0');
    }
}

document.addEventListener('DOMContentLoaded', function () {
    initDatePickers(document);
});

// Re-scan the whole document after every htmx swap.  The swapped-in content
// does not run its own inline scripts, and the swap target may be replaced
// (outerHTML), so scanning the document is the most reliable approach.
document.body.addEventListener('htmx:afterSwap', function () {
    initDatePickers(document);
});
