from .models import CompanyProfile

def company_context(request):
    """
    Injects company profile and module visibility flags (e.g. show_inventory)
    into all templates.
    """
    try:
        company = CompanyProfile.objects.first()
        show_inventory = getattr(company, 'show_inventory', True) if company else True
    except Exception:
        company = None
        show_inventory = True

    return {
        'company_profile': company,
        'show_inventory': show_inventory,
    }
