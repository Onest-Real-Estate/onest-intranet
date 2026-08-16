from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def inertia_json(value):
    """Make an already-encoded Inertia page JSON string safe for a script tag."""
    return mark_safe(
        str(value)
        .replace("&", "\\u0026")
        .replace("<", "\\u003C")
        .replace(">", "\\u003E")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
