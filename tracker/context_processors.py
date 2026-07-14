from django.contrib.auth import get_user_model
User = get_user_model()

def user_notifications(request):
    if request.user.is_authenticated:
        unread = request.user.notifications.filter(is_read=False).order_by('-created_at')[:10]
        read = request.user.notifications.filter(is_read=True).order_by('-created_at')[:20]
        count = request.user.notifications.filter(is_read=False).count()
        all_users = User.objects.filter(is_active=True).values('username', 'first_name', 'last_name')
        return {
            'unread_notifications': unread,
            'read_notifications': read,
            'unread_notifications_count': count,
            'all_active_users': list(all_users)
        }
    return {}

from .models import UserFieldVisibility

def field_visibility(request):
    """
    Context processor to inject field_visibility rules into all templates.
    """
    default_visibility = {
        'can_see_selling_price': True,
        'can_see_purchase_price': True,
        'can_see_profit_loss': True,
        'can_see_lot_total': True,
        'can_see_internal_notes': True,
    }

    if not request.user.is_authenticated:
        return {'field_visibility': default_visibility}

    # For admins, check if they have a UserFieldVisibility model with preferences,
    # otherwise default to True for everything. Admins' implicit permission is True.
    if request.user.is_staff or request.user.is_superuser:
        try:
            visibility = request.user.field_visibility
            return {
                'field_visibility': {
                    'can_see_selling_price': True and visibility.pref_show_selling_price,
                    'can_see_purchase_price': True and visibility.pref_show_purchase_price,
                    'can_see_profit_loss': True and visibility.pref_show_profit_loss,
                    'can_see_lot_total': True and visibility.pref_show_lot_total,
                    'can_see_internal_notes': True and visibility.pref_show_internal_notes,
                }
            }
        except UserFieldVisibility.DoesNotExist:
            return {
                'field_visibility': {
                    'can_see_selling_price': True,
                    'can_see_purchase_price': True,
                    'can_see_profit_loss': True,
                    'can_see_lot_total': True,
                    'can_see_internal_notes': True,
                }
            }

    # For standard users, evaluate Admin Permission AND User Preference
    try:
        visibility = request.user.field_visibility
        return {
            'field_visibility': {
                'can_see_selling_price': visibility.can_see_selling_price and visibility.pref_show_selling_price,
                'can_see_purchase_price': visibility.can_see_purchase_price and visibility.pref_show_purchase_price,
                'can_see_profit_loss': visibility.can_see_profit_loss and visibility.pref_show_profit_loss,
                'can_see_lot_total': visibility.can_see_lot_total and visibility.pref_show_lot_total,
                'can_see_internal_notes': visibility.can_see_internal_notes and visibility.pref_show_internal_notes,
            }
        }
    except UserFieldVisibility.DoesNotExist:
        return {'field_visibility': default_visibility}
