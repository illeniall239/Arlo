"""
Export service — converts structured_data (JSON string from DB) to
downloadable JSON or CSV bytes.
"""

import csv
import io
import json
from typing import Any


def to_json_bytes(structured_data: str) -> bytes:
    """Pretty-print the JSON array as UTF-8 bytes."""
    records: list[Any] = json.loads(structured_data)
    return json.dumps(records, indent=2, ensure_ascii=False).encode("utf-8")


def to_csv_bytes(structured_data: str) -> bytes:
    """Convert JSON array of dicts to CSV bytes."""
    records: list[dict] = json.loads(structured_data)
    if not records:
        return b""

    # Collect all keys across all records (some may have extra fields)
    all_keys: list[str] = []
    seen: set[str] = set()
    for record in records:
        for k in record.keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=all_keys, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow({k: record.get(k, "") for k in all_keys})

    return buf.getvalue().encode("utf-8")
