"""Readable numbers shared by native plots, tooltips and research summaries."""
import math


def format_number(value, *, spacing=None, significant=6):
    number = float(value)
    if not math.isfinite(number):
        return "—"
    if number == 0:
        return "0"
    magnitude = abs(number)
    if magnitude >= 1e9 or magnitude < 1e-7:
        mantissa, exponent = f"{number:.{significant - 1}e}".split("e")
        return mantissa.rstrip("0").rstrip(".") + "e" + str(int(exponent))
    if spacing is not None and math.isfinite(spacing) and spacing != 0:
        decimals = max(0, min(12, -math.floor(math.log10(abs(spacing))) + 1))
    else:
        decimals = max(0, min(12, significant - 1 - math.floor(math.log10(magnitude))))
    text = f"{number:,.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def format_point(x, y):
    return f"({format_number(x)}, {format_number(y)})"
