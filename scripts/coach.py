#!/usr/bin/env python3
"""Immutable private lesson files and evidence-based 1/3/7-day review dates."""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

STATES = {"not_learned", "exposed", "passive", "prompted", "independent", "reconsolidate"}
SUPPORT = {"none", "intent_hint", "keyword_hint", "model"}
MODES = {"daily", "free", "mistakes", "exam"}
OFFSETS = (1, 3, 7)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def validate(session):
    require(isinstance(session, dict), "session must be an object")
    require(type(session.get("version")) is int and session["version"] == 1, "version must be 1")
    sid = session.get("id")
    require(isinstance(sid, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", sid), "invalid session id")
    stamp = datetime.fromisoformat(session["created_at"])
    require(stamp.tzinfo is not None, "created_at needs a timezone")
    require(session.get("mode") in MODES, "invalid mode")
    require(session.get("language") == "ja", "language must be ja")
    require(nonempty(session.get("summary")), "summary required")
    focus = session.get("focus_next")
    require(isinstance(focus, list) and len(focus) <= 3 and all(nonempty(x) for x in focus), "focus_next must contain at most 3 strings")
    audio = session.get("audio_observed")
    require(type(audio) is bool, "audio_observed must be boolean")
    findings = session.get("pronunciation_notes", [])
    require(isinstance(findings, list) and all(nonempty(x) for x in findings), "invalid pronunciation_notes")
    require(audio or not findings, "pronunciation findings require original audio")
    items = session.get("items")
    require(isinstance(items, list), "items must be a list")
    seen = set()
    for item in items:
        require(isinstance(item, dict), "item must be an object")
        key = item.get("key")
        require(nonempty(key) and key not in seen, "knowledge keys must be nonempty and unique per session")
        seen.add(key)
        require(item.get("kind") in {"vocabulary", "grammar"}, "invalid item kind")
        require(nonempty(item.get("expression")), "expression required")
        require(type(item.get("observed")) is bool, "observed must be boolean")
        if not item["observed"]:
            # Keep the missed opportunity in the lesson, but do not rewrite history.
            require(not any(k in item for k in ("state", "evidence", "is_review", "independent_correct", "transfer", "support")), "unobserved items cannot make learning claims")
            continue
        require(item.get("state") in STATES, "invalid knowledge state")
        require(nonempty(item.get("evidence")), "real lesson evidence required")
        require(item.get("support") in SUPPORT, "invalid support")
        for field in ("is_review", "independent_correct", "transfer"):
            require(type(item.get(field)) is bool, f"{field} must be boolean")
        successful = item["independent_correct"]
        require(not successful or (item["support"] == "none" and item["transfer"] and item["state"] == "independent"), "independent success needs no hints and correct transfer evidence")
        require(item["state"] != "independent" or successful, "independent state needs independent success")
        require(item["state"] != "not_learned" or not item["is_review"], "unlearned is not a failed review")
    return session


def read_json(path):
    with Path(path).open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_sessions(data_dir):
    records = [validate(read_json(path)) for path in sorted((Path(data_dir) / "coach-sessions").glob("*.json"))]
    return sorted(records, key=lambda s: (datetime.fromisoformat(s["created_at"]), s["id"]))


def archive(data_dir, session):
    validate(session)
    data_dir = Path(data_dir)
    require(data_dir.is_absolute(), "data-dir must be absolute")
    folder = data_dir / "coach-sessions"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (session["id"] + ".json")
    if target.exists():
        require(read_json(target) == session, "same id has different content; refusing overwrite")
        return target
    # Publish a complete file atomically, without replacing an existing record.
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(session, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        try:
            os.link(temporary, target)
        except FileExistsError:
            require(read_json(target) == session, "concurrent conflicting record; refusing overwrite")
    finally:
        temporary.unlink(missing_ok=True)
    require(read_json(target) == session, "saved file verification failed")
    return target


def review_queue(sessions, on):
    history = {}
    for session in sorted(sessions, key=lambda s: (datetime.fromisoformat(s["created_at"]), s["id"])):
        validate(session)
        day = datetime.fromisoformat(session["created_at"]).date()
        if day > on:
            continue
        for item in session["items"]:
            if not item["observed"] or item["state"] == "not_learned":
                continue
            key = item["key"]
            if key not in history:
                history[key] = {"key": key, "anchor": day, "round": 0, "due": day + timedelta(days=1), "last_pass": None}
            row = history[key]
            row.update(expression=item["expression"], kind=item["kind"], state=item["state"])
            if item["is_review"]:
                if not item["independent_correct"]:
                    row.update(anchor=day, round=0, due=day + timedelta(days=1))
                elif row["due"] is not None and day >= row["due"] and day != row["last_pass"]:
                    row["round"] += 1
                    row["last_pass"] = day
                    row["due"] = None if row["round"] == len(OFFSETS) else max(row["anchor"] + timedelta(days=OFFSETS[row["round"]]), day + timedelta(days=1))
    result = []
    for row in history.values():
        if row["due"] is not None and row["due"] <= on:
            result.append({"key": row["key"], "expression": row["expression"], "kind": row["kind"], "state": row["state"], "due_date": row["due"].isoformat(), "completed_rounds": row["round"]})
    return sorted(result, key=lambda r: (r["due_date"], r["key"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("archive")
    save.add_argument("--data-dir", type=Path, required=True)
    save.add_argument("--input", type=Path, required=True)
    due = commands.add_parser("due")
    due.add_argument("--data-dir", type=Path, required=True)
    due.add_argument("--on", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    try:
        require(args.data_dir.is_absolute(), "data-dir must be absolute")
        if args.command == "archive":
            print(json.dumps({"saved": str(archive(args.data_dir, read_json(args.input)))}, ensure_ascii=False))
        else:
            print(json.dumps({"on": args.on.isoformat(), "due": review_queue(load_sessions(args.data_dir), args.on)}, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
