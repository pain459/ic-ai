#!/usr/bin/env python3
"""
Ingest incident records from a JSON file into Postgres.

- Stores full record in incident.incidents.raw_json (JSONB)
- Best-effort extraction of normalized columns (service, severity, ttm, etc.)
- Upserts on incident_id (re-runnable)
"""

import argparse
import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import psycopg2
import psycopg2.extras


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="postgresql://user:pass@host:port/dbname")
    p.add_argument("--src", required=True, help="Path to JSON dataset file")
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument("--dry-run", action="store_true", help="Parse and print stats without writing to DB")
    return p.parse_args()


def load_json_records(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Support common shapes:
    # - list[dict]
    # - { "records": [...] }
    # - { "incidents": [...] }
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in ("records", "incidents", "data", "items"):
            if k in data and isinstance(data[k], list):
                return [x for x in data[k] if isinstance(x, dict)]
    raise ValueError(f"Unsupported JSON shape in {path}. Expected list[dict] or dict with list field.")


def get_first(d: Dict[str, Any], keys: Iterable[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def normalize_text(x: Any) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, (dict, list)):
        return json.dumps(x, ensure_ascii=False)
    s = str(x).strip()
    return s if s else None


def parse_ts(x: Any) -> Optional[datetime]:
    """Best-effort timestamp parsing."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        # might be epoch seconds
        try:
            return datetime.fromtimestamp(float(x))
        except Exception:
            return None
    s = str(x).strip()
    if not s:
        return None

    # Try ISO-8601-ish
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass

    # Try to coerce common variants (remove Z)
    s2 = s.replace("Z", "")
    if s2 != s:
        return parse_ts(s2)

    return None


def parse_ttm_minutes(record: Dict[str, Any]) -> Optional[float]:
    """
    Extract ttm_minutes from common fields.
    Supports:
      - numeric minutes field (ttm_minutes, ttm, time_to_mitigate_minutes)
      - numeric seconds field (ttm_seconds, time_to_mitigate_seconds)
      - text like '120', '120 min', '2h 10m'
    """
    val = get_first(
        record,
        [
            "ttm_minutes",
            "time_to_mitigate_minutes",
            "ttm",
            "time_to_mitigate",
            "mitigation_time_minutes",
        ],
    )
    if isinstance(val, (int, float)):
        return float(val)

    val_s = normalize_text(val)
    if val_s:
        # pure numeric
        if re.fullmatch(r"\d+(\.\d+)?", val_s):
            return float(val_s)
        # "2h 10m", "2h", "130m"
        m = re.findall(r"(\d+(\.\d+)?)(\s*)(h|hr|hrs|hour|hours|m|min|mins|minute|minutes)", val_s.lower())
        if m:
            total = 0.0
            for num, _, _, unit in m:
                n = float(num)
                if unit.startswith("h"):
                    total += n * 60.0
                else:
                    total += n
            return total

    # seconds variant
    val2 = get_first(record, ["ttm_seconds", "time_to_mitigate_seconds", "mitigation_time_seconds"])
    if isinstance(val2, (int, float)):
        return float(val2) / 60.0
    val2s = normalize_text(val2)
    if val2s and re.fullmatch(r"\d+(\.\d+)?", val2s):
        return float(val2s) / 60.0

    return None


def extract_root_cause(record: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to extract:
      - root_cause_type (a short label)
      - root_cause_text (freeform / summary)
    """
    rc = record.get("root_cause")

    if isinstance(rc, dict):
        rc_type = normalize_text(get_first(rc, ["type", "category", "root_cause_type"]))
        rc_text = normalize_text(get_first(rc, ["summary", "text", "details", "description"]))
        if not rc_text:
            # if dict but no clear text, store compact json
            rc_text = normalize_text(rc)
        return rc_type, rc_text

    # If root_cause is a string blob, keep it as text
    rc_text = normalize_text(rc)

    # Root cause type might be separate
    rc_type = normalize_text(
        get_first(record, ["root_cause_type", "rc_type", "cause_type", "category", "rootCauseType"])
    )

    return rc_type, rc_text


def extract_followups(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract follow-up actions list from common shapes:
      - record["followup_actions"] as list[str|dict]
      - record["followups"] as list[...]
      - record["actions"] as list[...]
    Returns normalized list of dicts.
    """
    raw = None
    for k in ("followup_actions", "followups", "actions", "action_items"):
        if k in record and record[k] is not None:
            raw = record[k]
            break

    items: List[Dict[str, Any]] = []
    if raw is None:
        return items

    if isinstance(raw, str):
        items.append({"action_text": raw})
        return items

    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, str):
                items.append({"action_text": x})
            elif isinstance(x, dict):
                items.append(
                    {
                        "action_text": normalize_text(get_first(x, ["text", "action", "title", "summary", "description"])),
                        "owner": normalize_text(get_first(x, ["owner", "assignee"])),
                        "status": normalize_text(get_first(x, ["status", "state"])),
                        "due_date": normalize_text(get_first(x, ["due_date", "due", "deadline"])),
                        "raw_json": x,
                    }
                )
    elif isinstance(raw, dict):
        # sometimes grouped dict
        items.append({"action_text": normalize_text(raw), "raw_json": raw})
    return items


def extract_incident_id(record: Dict[str, Any]) -> Optional[int]:
    val = get_first(record, ["incident_id", "id", "arc_incident_id", "incidentId"])
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.strip().isdigit():
        return int(val.strip())
    # try to find first integer in id-like string
    m = re.search(r"(\d+)", str(val))
    return int(m.group(1)) if m else None


def build_incident_row(record: Dict[str, Any]) -> Dict[str, Any]:
    incident_id = extract_incident_id(record)
    title = normalize_text(get_first(record, ["title", "subject", "summary", "name"]))
    service = normalize_text(get_first(record, ["service", "app", "application", "component"]))
    subdept = normalize_text(get_first(record, ["subdepartment", "sub_dept", "team", "org"]))
    severity = normalize_text(get_first(record, ["severity", "sev", "priority"]))
    status = normalize_text(get_first(record, ["status", "state"]))

    start_time = parse_ts(get_first(record, ["start_time", "start", "created_at", "createdAt", "startTime"]))
    end_time = parse_ts(get_first(record, ["end_time", "end", "resolved_at", "resolvedAt", "endTime"]))

    ttm_minutes = parse_ttm_minutes(record)
    root_cause_type, root_cause_text = extract_root_cause(record)

    impact_summary = normalize_text(get_first(record, ["impact", "impact_summary", "customer_impact", "summary_impact"]))

    return {
        "incident_id": incident_id,
        "title": title,
        "service": service,
        "subdept": subdept,
        "severity": severity,
        "status": status,
        "start_time": start_time,
        "end_time": end_time,
        "ttm_minutes": ttm_minutes,
        "root_cause_type": root_cause_type,
        "root_cause_text": root_cause_text,
        "impact_summary": impact_summary,
        "raw_json": record,
    }


UPSERT_INCIDENT_SQL = """
INSERT INTO incident.incidents (
  incident_id, title, service, subdept, severity, status,
  start_time, end_time, ttm_minutes,
  root_cause_type, root_cause_text, impact_summary,
  raw_json
) VALUES (
  %(incident_id)s, %(title)s, %(service)s, %(subdept)s, %(severity)s, %(status)s,
  %(start_time)s, %(end_time)s, %(ttm_minutes)s,
  %(root_cause_type)s, %(root_cause_text)s, %(impact_summary)s,
  %(raw_json)s::jsonb
)
ON CONFLICT (incident_id) DO UPDATE SET
  title = EXCLUDED.title,
  service = EXCLUDED.service,
  subdept = EXCLUDED.subdept,
  severity = EXCLUDED.severity,
  status = EXCLUDED.status,
  start_time = EXCLUDED.start_time,
  end_time = EXCLUDED.end_time,
  ttm_minutes = EXCLUDED.ttm_minutes,
  root_cause_type = EXCLUDED.root_cause_type,
  root_cause_text = EXCLUDED.root_cause_text,
  impact_summary = EXCLUDED.impact_summary,
  raw_json = EXCLUDED.raw_json;
"""

INSERT_FOLLOWUP_SQL = """
INSERT INTO incident.followups (
  incident_id, action_text, owner, due_date, status, raw_json
) VALUES (
  %(incident_id)s, %(action_text)s, %(owner)s,
  %(due_date)s::date, %(status)s, %(raw_json)s::jsonb
);
"""


def chunked(it: List[Any], n: int) -> Iterable[List[Any]]:
    for i in range(0, len(it), n):
        yield it[i : i + n]


def main() -> None:
    args = parse_args()
    records = load_json_records(args.src)

    rows: List[Dict[str, Any]] = []
    followups: List[Dict[str, Any]] = []
    skipped = 0

    for r in records:
        row = build_incident_row(r)
        if row["incident_id"] is None:
            skipped += 1
            continue
        rows.append(row)

        for fu in extract_followups(r):
            action_text = normalize_text(fu.get("action_text"))
            if not action_text:
                continue
            followups.append(
                {
                    "incident_id": row["incident_id"],
                    "action_text": action_text,
                    "owner": normalize_text(fu.get("owner")),
                    "status": normalize_text(fu.get("status")),
                    "due_date": normalize_text(fu.get("due_date")),
                    "raw_json": fu.get("raw_json") if isinstance(fu.get("raw_json"), dict) else None,
                }
            )

    print(f"Loaded records: {len(records)}")
    print(f"Prepared incidents: {len(rows)}")
    print(f"Prepared followups: {len(followups)}")
    print(f"Skipped (no incident_id): {skipped}")

    if args.dry_run:
        return

    conn = psycopg2.connect(args.db)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            # Clear followups for upserted incidents to avoid duplicates
            # (simple approach; can be optimized later)
            incident_ids = [r["incident_id"] for r in rows]
            psycopg2.extras.execute_values(
                cur,
                "DELETE FROM incident.followups WHERE incident_id IN %s",
                [(tuple(incident_ids),)],
                template=None,
                page_size=1,
            )

        with conn.cursor() as cur:
            for batch in chunked(rows, args.batch_size):
                psycopg2.extras.execute_batch(cur, UPSERT_INCIDENT_SQL, batch, page_size=args.batch_size)

        with conn.cursor() as cur:
            for batch in chunked(followups, args.batch_size):
                # handle due_date parse failures by storing null
                for b in batch:
                    # keep only YYYY-MM-DD if present
                    dd = b.get("due_date")
                    if isinstance(dd, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", dd.strip()):
                        b["due_date"] = dd.strip()
                    else:
                        b["due_date"] = None
                psycopg2.extras.execute_batch(cur, INSERT_FOLLOWUP_SQL, batch, page_size=args.batch_size)

        conn.commit()
        print("✅ Ingestion complete.")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
