"""
Universal field-value normalizer.
No external dependencies — stdlib only (re, datetime, urllib.parse).
"""

import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

# ── Nested-structure flattening ───────────────────────────────────────────────

_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE   = re.compile(r"\s+")


def flatten_value(val: Any, _depth: int = 0) -> Any:
    """
    Recursively reduce any value to a plain scalar (str/int/float/bool).

    Dict strategy (in priority order):
      1. Range / quantity  — has minValue/maxValue or min/max keys  → "X–Y/unit"
      2. Named entity      — has name / @value / text / value       → str(name)
      3. Generic           — anything else                          → "k: v, …" pairs

    List → comma-joined scalars (up to 8 items).
    Strings → returned as-is (HTML stripping happens in flatten_record).
    """
    if _depth > 6 or val is None:
        return val

    if isinstance(val, dict):
        # 1. Range / quantitative value (schema.org QuantitativeValue, price ranges, …)
        lo = val.get("minValue") or val.get("min") or val.get("from") or val.get("lowPrice")
        hi = val.get("maxValue") or val.get("max") or val.get("to")   or val.get("highPrice")
        unit = val.get("unitText") or val.get("unit") or ""
        if lo is not None or hi is not None:
            try:
                lo_s = str(int(float(lo))) if lo is not None else ""
                hi_s = str(int(float(hi))) if hi is not None else ""
            except (ValueError, TypeError):
                lo_s, hi_s = str(lo or ""), str(hi or "")
            s = "–".join(p for p in (lo_s, hi_s) if p)
            return f"{s}/{unit.lower()}" if unit else s

        # 2. Named entity
        name = (val.get("name") or val.get("@value") or
                val.get("text") or val.get("value") or val.get("label"))
        if name:
            return str(name)

        # 3. Generic: recurse into non-@ fields, join as "key: value" pairs
        parts = []
        for k, v in val.items():
            if k.startswith("@") or v in (None, "", [], {}):
                continue
            fv = flatten_value(v, _depth + 1)
            if fv not in (None, ""):
                parts.append(f"{k}: {fv}")
        return ", ".join(parts) or None

    if isinstance(val, list):
        items = []
        for v in val[:8]:
            fv = flatten_value(v, _depth + 1)
            if fv not in (None, ""):
                items.append(str(fv))
        return ", ".join(items) if items else None

    return val  # str, int, float, bool — already scalar


def flatten_record(record: dict) -> dict:
    """
    Normalize one extracted record for storage and display:
    - Flatten every nested dict/list value to a human-readable scalar
    - Strip HTML tags from string values
    - Drop keys whose value is empty/None after normalization
    """
    out = {}
    for k, v in record.items():
        v = flatten_value(v)
        if isinstance(v, str):
            v = _HTML_RE.sub(" ", v)
            v = _WS_RE.sub(" ", v).strip()
        if v not in (None, ""):
            out[k] = v
    return out

# ── Date format list (most-specific first) ────────────────────────────────────

_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%B %d, %Y",    # January 5, 2024
    "%b %d, %Y",    # Jan 5, 2024
    "%d %B %Y",     # 5 January 2024
    "%d %b %Y",     # 5 Jan 2024
    "%m/%d/%Y",     # 01/05/2024
    "%d/%m/%Y",     # 05/01/2024
    "%d-%m-%Y",     # 05-01-2024
    "%Y/%m/%d",     # 2024/01/05
]

# ── Boolean vocabulary ────────────────────────────────────────────────────────

_BOOL_TRUE  = {"yes", "true", "available", "in stock", "active",
               "open", "enabled", "on", "1", "published", "live"}
_BOOL_FALSE = {"no", "false", "unavailable", "out of stock", "inactive",
               "closed", "sold out", "disabled", "off", "0", "draft"}


# ── Public API ────────────────────────────────────────────────────────────────

def normalize_value(val, field_type: str, base_url: str = ""):
    """
    Normalize a single extracted value by semantic type.
    Returns the original string unchanged if normalization fails — never loses data.

    field_type: "text" | "number" | "url" | "date" | "list" | "boolean"
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None

    try:
        if field_type == "number":
            return _to_number(s)
        if field_type == "date":
            return _to_date(s)
        if field_type == "url":
            return urljoin(base_url, s) if base_url else s
        if field_type == "list":
            return [item.strip() for item in re.split(r"[,;|]", s) if item.strip()]
        if field_type == "boolean":
            return _to_bool(s)
    except Exception:
        pass  # always fall back to raw string

    # "text" or unknown — just return stripped string
    return s


def normalize_records(records: list, field_types: dict, base_url: str = "") -> list:
    """Apply field_types normalization to every record in the list."""
    if not field_types or not records:
        return records
    out = []
    for rec in records:
        if not isinstance(rec, dict):
            out.append(rec)
            continue
        nr = dict(rec)
        for field, ftype in field_types.items():
            if field in nr:
                nr[field] = normalize_value(nr[field], ftype, base_url)
        out.append(nr)
    return out


# ── Internal helpers ──────────────────────────────────────────────────────────

def _to_number(s: str):
    """
    Strip currency symbols, units, commas → float or int.
    "£1,299.99"    → 1299.99
    "$45.00/month" → 45.0
    "4.5 out of 5" → 4.5   (first numeric group)
    "Free"         → 0.0
    """
    # Special case: free / zero
    if re.match(r"^(free|zero|n/?a)$", s, re.IGNORECASE):
        return 0.0

    # Extract first clean numeric sequence
    # Remove thousands-separator commas, then find first decimal number
    cleaned = re.sub(r"(\d),(\d)", r"\1\2", s)   # 1,299 → 1299
    m = re.search(r"\d+\.\d+|\d+", cleaned)
    if not m:
        return s   # no digits found — return raw
    num_str = m.group()
    return float(num_str) if "." in num_str else int(num_str)


def _to_date(s: str) -> str:
    """
    Parse common date string formats → ISO 8601 date string "YYYY-MM-DD".
    Returns original string if unparseable.
    """
    clean = s.strip()

    # Already ISO-ish
    if re.match(r"^\d{4}-\d{2}-\d{2}", clean):
        return clean[:10]

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(clean, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return s  # unparseable — return original


def _to_bool(s: str):
    """
    Map availability/yes-no strings to Python bool.
    Returns original string if ambiguous.
    """
    lower = s.lower().strip()
    if lower in _BOOL_TRUE:
        return True
    if lower in _BOOL_FALSE:
        return False
    return s  # ambiguous — return raw string
