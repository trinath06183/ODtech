from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY_PLACES = Decimal("0.01")


def to_decimal(value, default="0.00"):
    if value in (None, ""):
        value = default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def money(value):
    return to_decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def financial_year(value):
    year = value.year
    if value.month < 4:
        start_year = year - 1
        end_year = year
    else:
        start_year = year
        end_year = year + 1
    return f"{start_year}-{str(end_year)[-2:]}"


def format_inr(value):
    amount = money(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    integer, decimal = f"{amount:.2f}".split(".")
    if len(integer) > 3:
        last_three = integer[-3:]
        remaining = integer[:-3]
        groups = []
        while remaining:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        integer = ",".join(groups + [last_three])
    return f"{sign}Rs. {integer}.{decimal}"


def get_public_base_url(request=None):
    """
    Returns the canonical public base URL (e.g. ngrok tunnel or production domain).
    Ensures that automated emails and external links NEVER use internal LAN IPs
    (like 192.168.x.x, 10.x.x.x, 127.0.0.1, or localhost) which fail when users
    access links on mobile data or outside the local network.
    """
    from django.conf import settings
    default_url = getattr(settings, 'SITE_URL', 'https://collar-mammal-strike.ngrok-free.dev')

    # 1. Check CompanyProfile.public_portal_url
    try:
        from config.models import CompanyProfile
        company = CompanyProfile.objects.first()
        if company and getattr(company, 'public_portal_url', None):
            val = company.public_portal_url.strip().rstrip('/')
            if val and not any(h in val for h in ['192.168.', '127.0.0.1', 'localhost', '10.', '172.16.', '::1']):
                return val
    except Exception:
        pass

    # 2. Check current request origin if it's already an external / ngrok domain
    if request:
        origin = request.build_absolute_uri('/')[:-1]
        if 'ngrok' in origin or (not any(h in origin for h in ['192.168.', '127.0.0.1', 'localhost', '10.', '172.16.', '::1']) and getattr(settings, 'SITE_URL', None)):
            return origin.rstrip('/')

    # 3. Fallback to settings.SITE_URL or default ngrok public domain
    if any(h in str(default_url) for h in ['192.168.', '127.0.0.1', 'localhost', '10.', '172.16.', '::1']):
        return 'https://collar-mammal-strike.ngrok-free.dev'
    return str(default_url).rstrip('/')


