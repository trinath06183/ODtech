from django import template

register = template.Library()

@register.filter
def replace(value, arg):
    """
    Replaces all values of arg from the given string with a space.
    Usage: {{ value|replace:"_" }}
    """
    if isinstance(value, str):
        return value.replace(arg, ' ')
    return value
