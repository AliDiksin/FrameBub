"""Durable standard-library storage for scheduled reminders."""
# Atomic replacement keeps a failed process from truncating the durable reminder state.

from __future__ import annotations

import datetime as _datetime
import json
import os
import tempfile
from pathlib import Path

STORE_VERSION = 1


def store_path() -> Path:
    configured = str(os.getenv("REMINDER_STORE_FILE") or "reminders.json").strip()
    return Path(configured).expanduser()


def _parse_utc(value):
    if isinstance(value, _datetime.datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            normalized = value.strip()
            if normalized.endswith(("Z", "z")):
                normalized = normalized[:-1] + "+00:00"
            parsed = _datetime.datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_datetime.timezone.utc)
    return parsed.astimezone(_datetime.timezone.utc)


def _serialize_record(record):
    try:
        user_id = int(record["user_id"])
        channel_id = int(record["channel_id"])
        task = str(record["task"]).strip()
        reminder_id = str(record["id"]).strip()
        when_utc = _parse_utc(record["when_utc"])
        raw_created_at = record.get("created_at_utc") or record.get("created_at")
        created_at = _parse_utc(raw_created_at) if raw_created_at is not None else None
        raw_next_attempt = record.get("next_attempt_utc")
        next_attempt = _parse_utc(raw_next_attempt) if raw_next_attempt is not None else None
        if not reminder_id or not task or when_utc is None:
            return None
        if raw_created_at is not None and created_at is None:
            return None
        if raw_next_attempt is not None and next_attempt is None:
            return None
        if created_at is None:
            created_at = _datetime.datetime.now(_datetime.timezone.utc)
        if "notify_user_ids" in record:
            raw_targets = record["notify_user_ids"]
            if not isinstance(raw_targets, list):
                return None
        else:
            raw_targets = [user_id]
        targets = []
        for raw_id in raw_targets:
            try:
                target_id = int(raw_id)
            except (TypeError, ValueError):
                return None
            if target_id not in targets:
                targets.append(target_id)
        if not targets:
            targets = [user_id]
        raw_attempts = record.get("attempts", 0)
        if isinstance(raw_attempts, bool):
            return None
        attempts = int(raw_attempts)
        if attempts < 0:
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return {
        "id": reminder_id,
        "user_id": user_id,
        "channel_id": channel_id,
        "task": task,
        "when_utc": when_utc,
        "notify_user_ids": targets,
        "created_at_utc": created_at,
        "attempts": attempts,
        "next_attempt_utc": next_attempt,
    }


def _to_json_record(record):
    normalized = _serialize_record(record)
    if normalized is None:
        raise ValueError("invalid reminder record")
    result = dict(normalized)
    for key in ("when_utc", "created_at_utc", "next_attempt_utc"):
        value = result.get(key)
        result[key] = value.isoformat() if value is not None else None
    return result


def load_records(path=None):
    path = Path(path or store_path())
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        quarantine_corrupt(path)
        return []
    if not isinstance(payload, dict):
        quarantine_corrupt(path)
        return []
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != STORE_VERSION:
        quarantine_corrupt(path)
        return []
    raw_records = payload.get("reminders")
    if not isinstance(raw_records, list):
        quarantine_corrupt(path)
        return []
    records = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            continue
        normalized = _serialize_record(raw_record)
        if normalized is not None:
            records.append(normalized)
    return records


def save_records(records, path=None):
    path = Path(path or store_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STORE_VERSION,
        "reminders": [_to_json_record(record) for record in records],
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def quarantine_corrupt(path=None):
    path = Path(path or store_path())
    if not path.exists():
        return None
    stamp = _datetime.datetime.now(_datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = path.with_name(f"{path.name}.corrupt-{stamp}")
    counter = 1
    while destination.exists():
        destination = path.with_name(f"{path.name}.corrupt-{stamp}-{counter}")
        counter += 1
    try:
        os.replace(path, destination)
    except OSError:
        return None
    return destination
