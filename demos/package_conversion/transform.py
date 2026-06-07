"""
BEFORE: a plain Python utility — no governance, no observability.

Usage: python transform.py input.json output.json [field1 field2 ...]
"""

import json
import sys


def transform(in_path: str, out_path: str, keep_fields: list[str]) -> int:
    with open(in_path) as f:
        records = json.load(f)

    filtered = [{k: r[k] for k in keep_fields if k in r} for r in records]

    with open(out_path, "w") as f:
        json.dump(filtered, f, indent=2)

    print(f"{len(filtered)} records written to {out_path}")
    return len(filtered)


if __name__ == "__main__":
    in_path  = sys.argv[1]
    out_path = sys.argv[2]
    fields   = sys.argv[3:] if len(sys.argv) > 3 else ["name", "email"]
    transform(in_path, out_path, fields)
