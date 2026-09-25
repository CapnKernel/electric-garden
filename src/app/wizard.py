"""Views for a multi-page "wizard-style" workflow.

Each step is its own URL/view and returns an HTML fragment that is swapped into 
a single ``#wizard-content`` container.

State is carried between steps in the HTTP request/response: every step renders
hidden ``<input>`` fields holding the accumulated wizard state, and the next
step's POST reads them back.  Nothing is stored server-side (no session), so the
wizard is fully stateless and each request is self-contained.

Example data is for "items", but should be modified as needed

The example workflow is a three-step "relabel" wizard for an item:

  1. ``wizard_name_hx``     — edit the item's name.
  2. ``wizard_description_hx`` — edit the item's description.
  3. ``wizard_confirm_hx``  — review and apply the changes.

Naming follows the django-htmx-fun pattern: ``_page`` views return a full page
(GET only), ``_hx`` views return an HTML fragment via GET, and ``_hxpost`` views
return an HTML fragment via POST.  One URL per method.

Pages/partials:
  * ``wizard_page``            — the wizard shell (GET), full page.  On load it
                                 ``hx-get``s the first step into
                                 ``#wizard-content``.
  * ``wizard_name_hx``         — step 1 form (GET), ``#wizard-content``.
  * ``wizard_name_hxpost``     — step 1 submission (POST), ``#wizard-content``.
  * ``wizard_description_hx``  — step 2 form (GET), ``#wizard-content``.
  * ``wizard_description_hxpost`` — step 2 submission (POST), ``#wizard-content``.
  * ``wizard_confirm_hx``      — step 3 review (GET), ``#wizard-content``.
  * ``wizard_confirm_hxpost``  — step 3 apply (POST), ``#wizard-content``.
"""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django_htmx.http import HttpResponseClientRedirect

# from .models import Item, ItemHistory
class Item:
    pass


# The ordered list of wizard steps.  Each entry is (slug, label).  The slug is
# used to build the step's URL name (``wizard_<slug>_hx``) and to render the
# progress indicator.
WIZARD_STEPS = [
    ('name', 'Name'),
    ('description', 'Description'),
    ('confirm', 'Confirm'),
]


def _step_url(slug, pk):
    """Return the GET URL for a wizard step."""
    return reverse(f'app:wizard_{slug}_hx', kwargs={'pk': pk})


def _wizard_state(request):
    """Read the accumulated wizard state from the request.

    State is passed back and forth in the HTTP request/response via hidden
    fields, so it is read from POST first (form submissions) and then GET
    (initial loads / back navigation).
    """
    return {
        'name': request.POST.get('name', request.GET.get('name', '')).strip(),
        'description': request.POST.get('description', request.GET.get('description', '')).strip(),
    }


def _wizard_context(request, item, current_slug):
    """Build the base template context shared by every wizard step.

    Includes the accumulated state, the step list (for the progress indicator)
    and the current step's index so the template can render "Step N of M".
    """
    state = _wizard_state(request)
    slugs = [slug for slug, _ in WIZARD_STEPS]
    context = {
        'item': item,
        'state': state,
        'steps': WIZARD_STEPS,
        'current_slug': current_slug,
        'step_number': slugs.index(current_slug) + 1,
        'total_steps': len(WIZARD_STEPS),
    }
    return context


def _get_wizard_item(pk):
    """Fetch the item the wizard operates on."""
    return get_object_or_404(Item, pk=pk)


def _redirect_to_item(request, pk):
    """Redirect to the item detail page.

    For htmx requests this is a client-side redirect (``HX-Redirect``) so the
    browser navigates instead of swapping a full page into the target; for
    plain requests it is a normal HTTP redirect.
    """
    url = reverse('app:item_detail', kwargs={'pk': pk})
    if request.htmx:
        return HttpResponseClientRedirect(url)
    return redirect(url)


@require_GET
def wizard_page(request, pk):
    """Render the wizard shell (the full page).

    The page shell is returned immediately; the first step's fragment is
    fetched separately via ``hx-get`` on load (see ``wizard_name_hx``).
    """
    item = _get_wizard_item(pk)
    context = {'item': item, 'first_step_url': _step_url('name', pk)}
    return render(request, 'app/wizard.html', context)


@require_GET
def wizard_name_hx(request, pk):
    """Render step 1 (name) as a fragment."""
    item = _get_wizard_item(pk)
    context = _wizard_context(request, item, 'name')
    return render(request, 'app/wizard.html#wizard-name', context)


@require_POST
def wizard_name_hxpost(request, pk):
    """Handle step 1 submission and advance to step 2.

    The submitted name is validated and carried forward in the response's
    hidden fields; the step 2 fragment is returned so it can be swapped in.
    """
    item = _get_wizard_item(pk)
    context = _wizard_context(request, item, 'name')

    if not context['state']['name']:
        context['error'] = 'Name is required.'
        return render(request, 'app/wizard.html#wizard-name', context)

    # Advance to step 2, carrying the accumulated state in the context.
    context = _wizard_context(request, item, 'description')
    return render(request, 'app/wizard.html#wizard-description', context)


@require_GET
def wizard_description_hx(request, pk):
    """Render step 2 (description) as a fragment."""
    item = _get_wizard_item(pk)
    context = _wizard_context(request, item, 'description')
    return render(request, 'app/wizard.html#wizard-description', context)


@require_POST
def wizard_description_hxpost(request, pk):
    """Handle step 2 submission and advance to step 3."""
    item = _get_wizard_item(pk)
    context = _wizard_context(request, item, 'confirm')
    return render(request, 'app/wizard.html#wizard-confirm', context)


@require_GET
def wizard_confirm_hx(request, pk):
    """Render step 3 (confirm) as a fragment."""
    item = _get_wizard_item(pk)
    context = _wizard_context(request, item, 'confirm')
    return render(request, 'app/wizard.html#wizard-confirm', context)


@require_POST
def wizard_confirm_hxpost(request, pk):
    """Apply the accumulated wizard state and finish.

    The only DB change is updating the item's name/description, done atomically
    in one transaction, and an ``UPDATE`` history entry is logged.  On success
    the client is redirected to the item detail page.
    """
    item = _get_wizard_item(pk)
    state = _wizard_state(request)

    if not state['name']:
        # Defensive: state should always carry a name by this point.
        context = _wizard_context(request, item, 'name')
        context['error'] = 'Name is required.'
        return render(request, 'app/wizard.html#wizard-name', context)

    with transaction.atomic():
        item.name = state['name']
        item.description = state['description']
        item.save()

        ItemHistory.objects.create(
            item=item,
            action='UPDATE',
            description=f'Relabelled {item.name} via wizard',
            metadata={'name': state['name'], 'description': state['description']},
        )

    messages.success(request, f'{item.name} updated.')
    return _redirect_to_item(request, pk)
