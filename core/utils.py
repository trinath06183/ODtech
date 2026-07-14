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

