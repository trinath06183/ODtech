from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Template filter to look up a dict value by key.
    Usage: {{ my_dict|get_item:key_variable }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)
