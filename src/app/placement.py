"""Where a planting or a packet is kept.

A location has two halves: the container it is in (``planted_in`` on a planting
event, ``container`` on a packet) and an optional free-text detail
(``location``).  They describe one thing, so they are handled together through
:class:`Placement` rather than as independent fields.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Placement:
    """A container, a free-text detail, both, or neither.

    ``text`` is normalised (stripped, with an empty string becoming ``None``), so
    two placements that differ only in whitespace compare equal.
    """

    container: object | None = None
    text: str | None = None

    def __post_init__(self):
        object.__setattr__(self, 'text', (self.text or '').strip() or None)

    @classmethod
    def from_event(cls, event):
        """The placement recorded on ``event``; ``EMPTY`` when there is no event."""
        if event is None:
            return EMPTY
        return cls(container=event.planted_in, text=event.location)

    @property
    def is_empty(self):
        """Whether neither half is set."""
        return self.container is None and self.text is None

    def is_in(self, container):
        """Whether this placement is the given container."""
        return self.container is not None and self.container.pk == container.pk

    @property
    def display(self):
        """Both halves as one string, e.g. ``Pot 1 · Front garden``."""
        return ' · '.join(str(part) for part in (self.container, self.text) if part)

    def __str__(self):
        return self.display


EMPTY = Placement()
