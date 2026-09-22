import json
import logging
import urllib.request
import urllib.error
from decimal import Decimal, ROUND_HALF_UP
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Fallback approximate market rates to INR if offline or external API fails
FALLBACK_RATES_TO_INR = {
    'INR': Decimal('1.0000'),
    'USD': Decimal('83.9000'),
    'EUR': Decimal('92.8000'),
    'GBP': Decimal('109.5000'),
    'AED': Decimal('22.8500'),
    'SAR': Decimal('22.3500'),
    'CAD': Decimal('62.2000'),
    'AUD': Decimal('56.5000'),
    'SGD': Decimal('64.8000'),
    'JPY': Decimal('0.5800'),
}


def get_live_exchange_rate(from_currency='USD', to_currency='INR', for_date=None):
    """
    Fetches the live exchange rate from from_currency to to_currency (default: INR).
    Returns a Decimal rounded to 4 decimal places.
    Results are cached to ensure fast response times and prevent rate limits.
    """
    from_currency = (from_currency or 'INR').upper().strip()
    to_currency = (to_currency or 'INR').upper().strip()

    if from_currency == to_currency:
        return Decimal('1.0000')

    cache_key = f"forex_rate_{from_currency}_{to_currency}_{for_date or 'latest'}"
    cached_rate = cache.get(cache_key)
    if cached_rate is not None:
        try:
            return Decimal(str(cached_rate))
        except Exception:
            pass

    rate = None

    # 1. Try Frankfurter API (Supports historical dates too)
    try:
        date_str = for_date.strftime('%Y-%m-%d') if hasattr(for_date, 'strftime') else (str(for_date) if for_date else 'latest')
        url = f"https://api.frankfurter.app/{date_str}?from={from_currency}&to={to_currency}"
        req = urllib.request.Request(url, headers={'User-Agent': 'ODtech-ERP/1.0'})
        with urllib.request.urlopen(req, timeout=3.5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                raw_rate = data.get('rates', {}).get(to_currency)
                if raw_rate:
                    rate = Decimal(str(raw_rate))
    except Exception as e:
        logger.warning(f"Frankfurter API error for {from_currency}->{to_currency}: {e}")

    # 2. Try Open Exchange Rate API (backup)
    if rate is None:
        try:
            url = f"https://open.er-api.com/v6/latest/{from_currency}"
            req = urllib.request.Request(url, headers={'User-Agent': 'ODtech-ERP/1.0'})
            with urllib.request.urlopen(req, timeout=3.5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    raw_rate = data.get('rates', {}).get(to_currency)
                    if raw_rate:
                        rate = Decimal(str(raw_rate))
        except Exception as e:
            logger.warning(f"Open ER API error for {from_currency}->{to_currency}: {e}")

    # 3. Fallback to hardcoded table if live fetch fails
    if rate is None:
        if to_currency == 'INR':
            rate = FALLBACK_RATES_TO_INR.get(from_currency, Decimal('1.0000'))
        else:
            rate = Decimal('1.0000')

    # Quantize to 4 decimal places
    rate = rate.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    # Cache for 6 hours (21600 seconds)
    cache.set(cache_key, str(rate), timeout=21600)

    return rate
