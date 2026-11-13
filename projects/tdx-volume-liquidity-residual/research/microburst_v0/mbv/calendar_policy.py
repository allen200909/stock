"""R7 study-mode / exchange-calendar policy.

Decisions implemented (R6 review, 2026-11-12):

- ``SYNTHETIC_DEMO``: a fixed generated calendar is allowed and labelled ``SYNTHETIC_GENERATED``. If no calendar
  is supplied to the feature pipeline the baseline falls back to symbol-observed dates, explicitly labelled
  ``NONE_SYMBOL_OBSERVED_DATES`` (synthetic only). The event study always needs a calendar (T16).
- ``EXPLORATORY_REAL_DATA``: an exchange calendar **plus** a provenance record is mandatory. The provenance must
  declare ``kind='EXCHANGE'``, a non-empty ``source`` and ``verified_by``, ``verified: true`` and a
  ``calendar_sha256`` equal to the fingerprint of the supplied dates (the record is bound to the exact calendar).
- ``CONFIRMATORY_OOS``: as above, plus a pre-registration record whose document hash is checked against the file,
  whose registration date precedes the sample start, and whose sample window lies inside the calendar. Every
  analysed trade date must fall inside the registered window. Passing the string alone never upgrades the label:
  the strongest grade reachable offline is ``CONFIRMATORY_OOS_CANDIDATE_PENDING_INDEPENDENT_REVIEW``.
- No silent fallback to symbol-observed dates outside ``SYNTHETIC_DEMO``.
- Gates G1/G2/G3 are never modified here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import pandas as pd

from mbv.schema import DataContractError, normalize_trade_date

VALID_STUDY_LABELS = ("SYNTHETIC_DEMO", "EXPLORATORY_REAL_DATA", "CONFIRMATORY_OOS")
FORMAL_STUDY_MODES = ("EXPLORATORY_REAL_DATA", "CONFIRMATORY_OOS")

CALENDAR_KIND_SYNTHETIC = "SYNTHETIC_GENERATED"
CALENDAR_KIND_EXCHANGE = "EXCHANGE"
CALENDAR_KIND_NONE = "NONE_SYMBOL_OBSERVED_DATES"

PREREG_REQUIRED_KEYS = ("registry_id", "registered_on", "sample_start", "sample_end", "data_source",
                        "document_path", "document_sha256")

RESEARCH_GRADE = {
    "SYNTHETIC_DEMO": "SYNTHETIC_DEMO_ONLY",
    "EXPLORATORY_REAL_DATA": "PROVISIONAL_RESEARCH",
    "CONFIRMATORY_OOS": "CONFIRMATORY_OOS_CANDIDATE_PENDING_INDEPENDENT_REVIEW",
}


def normalize_calendar(trading_calendar: Any) -> list[str]:
    """Sorted, unique, non-empty 'YYYY-MM-DD' list from a list/Series/DataFrame['trade_date']."""
    if trading_calendar is None:
        raise DataContractError("trading_calendar is required")
    if isinstance(trading_calendar, pd.DataFrame):
        if "trade_date" not in trading_calendar.columns:
            raise DataContractError("Calendar DataFrame must contain 'trade_date' column")
        raw = trading_calendar["trade_date"]
    else:
        raw = pd.Series(list(trading_calendar))
    if raw.empty:
        raise DataContractError("trading_calendar must not be empty")
    norm = normalize_trade_date(raw.reset_index(drop=True), "trading_calendar")
    if norm.duplicated().any():
        raise DataContractError("trading_calendar must contain unique trading dates")
    if not norm.is_monotonic_increasing:
        raise DataContractError("trading_calendar must be sorted chronologically")
    return norm.tolist()


def calendar_fingerprint(cal_list: Sequence[str]) -> str:
    """SHA-256 of the newline-joined normalized dates (independent of file format)."""
    return hashlib.sha256("\n".join(cal_list).encode("utf-8")).hexdigest()


def synthetic_calendar_provenance(cal_list: Sequence[str], source: str) -> dict[str, Any]:
    return {"kind": CALENDAR_KIND_SYNTHETIC, "source": source, "verified": False,
            "calendar_sha256": calendar_fingerprint(cal_list)}


def load_json_record(path: Optional[str | Path]) -> Optional[dict[str, Any]]:
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        raise DataContractError(f"Record file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DataContractError(f"Invalid JSON in {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise DataContractError(f"{p} must contain a JSON object")
    data.setdefault("_record_dir", str(p.resolve().parent))
    return data


@dataclass(frozen=True)
class StudyContext:
    study_mode: str
    calendar: Optional[list[str]]
    calendar_kind: str
    calendar_sha256: Optional[str]
    calendar_source: str
    research_grade: str
    preregistration: Optional[dict[str, Any]] = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_formal(self) -> bool:
        return self.study_mode in FORMAL_STUDY_MODES

    def describe(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "study_mode": self.study_mode,
            "research_grade": self.research_grade,
            "calendar_kind": self.calendar_kind,
            "calendar_sha256": self.calendar_sha256,
            "calendar_source": self.calendar_source,
            "calendar_sessions": len(self.calendar) if self.calendar else 0,
        }
        if self.preregistration is not None:
            out["preregistration"] = {k: self.preregistration[k] for k in PREREG_REQUIRED_KEYS
                                      if k != "document_path"}
        return out


def _validate_exchange_provenance(prov: Optional[Mapping[str, Any]], cal_list: list[str], mode: str) -> str:
    if prov is None:
        raise DataContractError(f"{mode} requires calendar provenance (kind/source/verified/verified_by/calendar_sha256)")
    if prov.get("kind") != CALENDAR_KIND_EXCHANGE:
        raise DataContractError(f"{mode} requires calendar provenance kind='{CALENDAR_KIND_EXCHANGE}', "
                                f"got {prov.get('kind')!r}")
    for key in ("source", "verified_by"):
        if not str(prov.get(key) or "").strip():
            raise DataContractError(f"Calendar provenance field '{key}' must be non-empty for {mode}")
    if prov.get("verified") is not True:
        raise DataContractError(f"{mode} requires a verified exchange calendar (verified: true)")
    expected = calendar_fingerprint(cal_list)
    if prov.get("calendar_sha256") != expected:
        raise DataContractError(
            f"Calendar provenance calendar_sha256 does not match supplied calendar (expected {expected})"
        )
    return str(prov["source"])


def _validate_preregistration(prereg: Optional[Mapping[str, Any]], cal_list: list[str]) -> dict[str, Any]:
    if prereg is None:
        raise DataContractError("CONFIRMATORY_OOS requires a pre-registration record")
    missing = [k for k in PREREG_REQUIRED_KEYS if not str(prereg.get(k) or "").strip()]
    if missing:
        raise DataContractError(f"Pre-registration record missing fields: {missing}")
    doc = Path(str(prereg["document_path"]))
    if not doc.is_absolute() and prereg.get("_record_dir"):
        doc = Path(str(prereg["_record_dir"])) / doc
    if not doc.exists():
        raise DataContractError(f"Pre-registration document not found: {doc}")
    actual = hashlib.sha256(doc.read_bytes()).hexdigest()
    if actual != prereg["document_sha256"]:
        raise DataContractError("Pre-registration document_sha256 does not match the document")
    dates = normalize_trade_date(
        pd.Series([prereg["registered_on"], prereg["sample_start"], prereg["sample_end"]]), "preregistration"
    ).tolist()
    reg, start, end = dates
    if not reg < start:
        raise DataContractError("Pre-registration must be dated strictly before sample_start")
    if not start <= end:
        raise DataContractError("Pre-registration sample_start must be <= sample_end")
    if start < cal_list[0] or end > cal_list[-1]:
        raise DataContractError("Pre-registered sample window must lie inside the verified exchange calendar")
    out = {k: prereg[k] for k in PREREG_REQUIRED_KEYS}
    out.update({"registered_on": reg, "sample_start": start, "sample_end": end})
    return out


def resolve_study_context(
    study_mode: str,
    trading_calendar: Any = None,
    *,
    calendar_provenance: Optional[Mapping[str, Any]] = None,
    preregistration: Optional[Mapping[str, Any]] = None,
    require_calendar: bool = True,
) -> StudyContext:
    """Validate study mode + calendar (+ provenance / pre-registration) and return an immutable context."""
    if study_mode not in VALID_STUDY_LABELS:
        raise DataContractError(f"Invalid study_mode '{study_mode}'; must be one of {VALID_STUDY_LABELS}")

    if trading_calendar is None:
        if study_mode in FORMAL_STUDY_MODES:
            raise DataContractError(
                f"{study_mode} requires an explicit verified exchange trading calendar; "
                "falling back to symbol-observed dates is not allowed"
            )
        if require_calendar:
            raise DataContractError(
                "Explicit trading_calendar is required for forward-return / T+1 event study (T16 fail-closed)"
            )
        return StudyContext(study_mode, None, CALENDAR_KIND_NONE, None, "NONE", RESEARCH_GRADE[study_mode],
                            notes=("SYNTHETIC_ONLY: baseline window steps on symbol-observed dates",))

    cal_list = normalize_calendar(trading_calendar)
    fp = calendar_fingerprint(cal_list)

    if study_mode == "SYNTHETIC_DEMO":
        kind = CALENDAR_KIND_SYNTHETIC
        source = "UNSPECIFIED_SYNTHETIC"
        if calendar_provenance is not None:
            if calendar_provenance.get("calendar_sha256") not in (None, fp):
                raise DataContractError("Calendar provenance calendar_sha256 does not match supplied calendar")
            source = str(calendar_provenance.get("source") or source)
        return StudyContext(study_mode, cal_list, kind, fp, source, RESEARCH_GRADE[study_mode])

    source = _validate_exchange_provenance(calendar_provenance, cal_list, study_mode)
    prereg_out = None
    if study_mode == "CONFIRMATORY_OOS":
        prereg_out = _validate_preregistration(preregistration, cal_list)
    elif preregistration is not None:
        prereg_out = _validate_preregistration(preregistration, cal_list)
    return StudyContext(study_mode, cal_list, CALENDAR_KIND_EXCHANGE, fp, source, RESEARCH_GRADE[study_mode],
                        preregistration=prereg_out)


def assert_dates_in_preregistered_window(ctx: StudyContext, dates: pd.Series, *, allow_warmup: bool = False) -> None:
    """CONFIRMATORY_OOS: every analysed trade date must lie inside the registered sample window.

    ``allow_warmup=True`` (feature pipeline) permits dates *before* ``sample_start`` because the past-only baseline
    needs prior history; dates after ``sample_end`` are still rejected.
    """
    if ctx.study_mode != "CONFIRMATORY_OOS" or ctx.preregistration is None:
        return
    d = normalize_trade_date(pd.Series(dates).reset_index(drop=True), "trade_date")
    start, end = ctx.preregistration["sample_start"], ctx.preregistration["sample_end"]
    bad = d > end if allow_warmup else (d < start) | (d > end)
    outside = d[bad]
    if not outside.empty:
        raise DataContractError(
            f"CONFIRMATORY_OOS data contains dates outside pre-registered window [{start}, {end}]: "
            f"{sorted(outside.unique())[:3]}"
        )


def assert_feature_calendar_consistent(ctx: StudyContext, joined_df: pd.DataFrame) -> None:
    """Feature rows must have been computed with the same calendar as the study (formal: mandatory stamp)."""
    has_minute = joined_df["feature_status"] != "MISSING_MINUTE_DATA" if "feature_status" in joined_df.columns \
        else pd.Series(True, index=joined_df.index)
    if "calendar_sha256" not in joined_df.columns:
        if ctx.is_formal and bool(has_minute.any()):
            raise DataContractError(
                f"{ctx.study_mode} requires MBV features stamped with calendar_sha256 (compute with the same "
                "verified calendar)"
            )
        return
    stamps = set(joined_df.loc[has_minute, "calendar_sha256"].dropna().astype(str).unique())
    if ctx.is_formal and joined_df.loc[has_minute, "calendar_sha256"].isna().any():
        raise DataContractError("Some MBV feature rows lack calendar_sha256 in a formal study")
    if stamps and stamps != {ctx.calendar_sha256}:
        raise DataContractError(
            f"MBV features were computed with a different calendar ({sorted(stamps)[:2]}) than the study "
            f"({ctx.calendar_sha256})"
        )
