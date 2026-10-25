"""Template tags shared by the project's templates."""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


class _HeadingNodeBase(template.Node):
    """Shared behaviour for block tags that render their content as a heading."""

    def __init__(self, nodelist):
        self.nodelist = nodelist

    def get_nodes_by_type(self, nodetype):
        """Report nested nodes so template inheritance can override them.

        Django only collects block nodes that it can find by type.  Without this
        a ``{% block %}`` inside the tag would be invisible to child templates
        that ``{% extends %}`` this one.
        """
        nodes = super().get_nodes_by_type(nodetype)
        nodes.extend(self.nodelist.get_nodes_by_type(nodetype))
        return nodes


class HeadingNode(_HeadingNodeBase):
    """Render the enclosed content inside an ``<h1>``, or nothing if it is blank."""

    def render(self, context):
        content = self.nodelist.render(context).strip()
        if not content:
            return ''
        return format_html('<h1>{}</h1>', mark_safe(content))


@register.tag('heading')
def do_heading(parser, token):
    """Wrap the enclosed content in an ``<h1>`` element."""
    nodelist = parser.parse(('endheading',))
    parser.delete_first_token()
    return HeadingNode(nodelist)


class RoleHeadingNode(_HeadingNodeBase):
    """Render the enclosed content as a heading with a fixed role and classes."""

    def __init__(self, tag_name, css_class, nodelist):
        super().__init__(nodelist)
        self.tag_name = tag_name
        self.css_class = css_class

    def render(self, context):
        content = self.nodelist.render(context).strip()
        if not content:
            return ''
        return format_html(
            '<{tag} class="{css_class}">{content}</{tag}>',
            tag=self.tag_name,
            css_class=self.css_class,
            content=mark_safe(content),
        )


def _role_heading(parser, tag_name, html_tag, css_class):
    """Parse a role heading block and return its node."""
    nodelist = parser.parse((f'end{tag_name}',))
    parser.delete_first_token()
    return RoleHeadingNode(html_tag, css_class, nodelist)


@register.tag('card_title')
def do_card_title(parser, token):
    """Render a top-level card title as ``h2.card-title.h5``."""
    return _role_heading(parser, 'card_title', 'h2', 'card-title h5 mb-0')


@register.tag('section_title')
def do_section_title(parser, token):
    """Render a major section heading as ``h3.h4``."""
    return _role_heading(parser, 'section_title', 'h3', 'h4')


@register.tag('subsection_title')
def do_subsection_title(parser, token):
    """Render a minor section heading as ``h3.h5``."""
    return _role_heading(parser, 'subsection_title', 'h3', 'h5')


@register.tag('alert_title')
def do_alert_title(parser, token):
    """Render an alert heading inside a card as ``h3.alert-heading.h5``."""
    return _role_heading(parser, 'alert_title', 'h3', 'alert-heading h5')


@register.tag('page_alert_title')
def do_page_alert_title(parser, token):
    """Render a page-level alert heading as ``h2.alert-heading.h5``."""
    return _role_heading(parser, 'page_alert_title', 'h2', 'alert-heading h5')
