#!/usr/bin/env python3
"""Run live import only for an explicit, date-bounded GitHub publication request."""
import datetime as dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUEST = ROOT / "control/publish-request.json"


def main():
    try:
        data = json.loads(REQUEST.read_text(encoding="utf-8"))
        now = dt.datetime.now(dt.timezone.utc).date()
        start = dt.date.fromisoformat(data["week_start"])
        end = dt.date.fromisoformat(data["week_end"])
        if not (
            data.get("schema_version") == 1
            and data.get("mode") == "publish"
            and data.get("approved") is True
            and data.get("test_batch") is True
            and dt.date.fromisoformat(data["created_on"]) == now
            and now < start <= end
            and (end - start).days <= 6
            and isinstance(data.get("batch_id"), str)
            and len(data["batch_id"]) >= 8
        ):
            raise ValueError("Invalid, expired or unsafely scoped live publication request.")
    except (KeyError, ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print("No valid publication authorization:", str(exc), file=sys.stderr)
        return 3
    print("Authorized one-shot test batch:", data["batch_id"], start, end, flush=True)
    command = [sys.executable, str(ROOT / "scripts/publish_batch.py"),
               "--apply", "--start", start.isoformat(), "--end", end.isoformat()]
    if data.get("resume") is True:
        command.extend(["--resume-report", "data/batch-run-report.json"])
    result = subprocess.run(command, cwd=ROOT, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
