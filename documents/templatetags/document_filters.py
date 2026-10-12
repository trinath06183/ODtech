from django import template

register = template.Library()

@register.filter
def indian_currency(value):
    if value is None:
        return ""
    try:
        amount = float(value)
        if amount == 0:
            return "-"
        is_negative = amount < 0
        s = f"{abs(amount):.2f}"
        parts = s.split('.')
        dec = parts[1]
        num = parts[0]
        
        if len(num) <= 3:
            formatted = f"{num}.{dec}"
        else:
            last_three = num[-3:]
            remaining = num[:-3]
            groups = []
            while remaining:
                groups.append(remaining[-2:])
                remaining = remaining[:-2]
            groups.reverse()
            formatted = ",".join(groups) + "," + last_three + "." + dec
            
        if is_negative:
            return f"-{formatted}"
        return formatted
    except (ValueError, TypeError):
        return value


@register.filter
def gst_state(gstin):
    if not gstin or len(gstin) < 2:
        return ""
    code = str(gstin)[:2]
    states = {
        "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
        "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
        "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
        "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
        "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
        "25": "Daman & Diu", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
        "28": "Andhra Pradesh", "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
        "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman & Nicobar Islands", "36": "Telangana",
        "37": "Andhra Pradesh", "38": "Ladakh"
    }
    state_name = states.get(code)
    if state_name:
        return f"{code}-{state_name}"
    return ""


@register.filter
def add_months(date_value, months):
    """
    Add `months` months to a date and return a formatted string (d/m/Y).
    Used for computing warranty end dates on the installation certificate.
    Supports integers, strings like '36 Months', '12', etc.
    """
    if not date_value or not months:
        return "–"
    try:
        import datetime, re, calendar
        # Extract numeric months from '36 Months', 36, etc.
        m_match = re.search(r'\d+', str(months))
        if not m_match:
            return "–"
        num_months = int(m_match.group())
        month = date_value.month - 1 + num_months
        year = date_value.year + month // 12
        month = month % 12 + 1
        last_day = calendar.monthrange(year, month)[1]
        day = min(date_value.day, last_day)
        end_date = datetime.date(year, month, day)
        return end_date.strftime('%d/%m/%Y')
    except Exception:
        return "–"


@register.filter
def get_installation_cert(doc):
    """
    Safely retrieve doc.installation_certificate without raising RelatedObjectDoesNotExist.
    """
    if not doc:
        return None
    try:
        return doc.installation_certificate
    except Exception:
        return None
