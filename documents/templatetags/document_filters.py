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
