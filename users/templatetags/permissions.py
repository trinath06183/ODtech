from django import template
from users.models import AppSection

register = template.Library()

@register.filter
def has_read_perm(user, section_code):
    if not user.is_authenticated:
        return False
    return user.has_section_perm(section_code, 'read')

@register.filter
def has_write_perm(user, section_code):
    if not user.is_authenticated:
        return False
    return user.has_section_perm(section_code, 'write')
