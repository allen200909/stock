"""Write-once prospective study registration; does not certify data ignorance."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import pandas as pd

REQUIRED = {"code_commit", "data_source_version", "universe", "price_convention",
            "parameters", "cost_assumptions", "prior_data_exposure",
            "confirmation_start", "confirmation_end", "primary_metric",
            "acceptance_rule", "block_lengths", "outcomes_previously_viewed"}


def freeze(spec, destination):
    if REQUIRED - spec.keys():
        raise ValueError(f"Missing registration fields: {sorted(REQUIRED-spec.keys())}")
    if any(spec[key] is None or spec[key] == "" or spec[key] == [] or spec[key] == {}
           for key in REQUIRED):
        raise ValueError("Registration fields must be populated")
    if not re.fullmatch(r"[0-9a-f]{40}", spec["code_commit"]):
        raise ValueError("code_commit must be the exact 40-character Git SHA")
    if spec["outcomes_previously_viewed"] is not False:
        raise ValueError("Previously viewed outcomes cannot be registered as untouched")
    now = datetime.now(timezone.utc)
    start, end = (pd.Timestamp(spec[k]) for k in ["confirmation_start", "confirmation_end"])
    if (pd.isna(start) or pd.isna(end) or start.tz is not None or end.tz is not None
            or start != start.normalize() or end != end.normalize()
            or start.date() <= now.date() or end < start):
        raise ValueError("Prospective confirmation must start after today's UTC date")
    payload = json.dumps(spec, sort_keys=True, ensure_ascii=False, allow_nan=False)
    document = {"registered_at_utc":now.isoformat(), "spec":spec,
                "spec_sha256":hashlib.sha256(payload.encode()).hexdigest(),
                "status":"REGISTERED_NOT_EVALUATED",
                "provenance":"User declarations; no independent proof of untouched data"}
    with Path(destination).open("x", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("spec_json")
    parser.add_argument("output_json")
    args = parser.parse_args()
    freeze(json.loads(Path(args.spec_json).read_text(encoding="utf-8")), args.output_json)
