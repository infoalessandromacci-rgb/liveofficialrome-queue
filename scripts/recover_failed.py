#!/usr/bin/env python3
"""Safely archive a definitively failed importer item, never a possible publication."""
import datetime as dt
import json
import pathlib
import sys
from urllib.parse import quote

from publish_batch import ROOT, api, finish, git, load, BatchFailure

def main():
    request = load(ROOT / "control/recovery-request.json")
    today = dt.datetime.now(dt.timezone.utc).date()
    if (request.get("schema_version") != 1 or request.get("approved") is not True
        or request.get("mode") != "recover_definitive_failure"
        or dt.date.fromisoformat(request.get("created_on")) != today):
        raise BatchFailure("Recovery request missing explicit valid same-day authorization")
    queue = request.get("queue")
    candidate = request.get("candidate")
    if not (isinstance(queue, str) and queue.startswith("queue/batch-")
            and queue.endswith(".json") and "/" not in queue[len("queue/"):]
            and isinstance(candidate, str) and candidate.startswith("candidates/")
            and candidate.endswith(".json") and "/" not in candidate[len("candidates/"):]):
        raise BatchFailure("Invalid recovery file paths")
    git("pull", "--ff-only", "origin", "main")
    candidate_file = ROOT / candidate
    queued_file = ROOT / queue
    if not candidate_file.is_file() or not queued_file.is_file():
        raise BatchFailure("Candidate or failed queue file is missing")
    event = load(candidate_file)
    if load(queued_file).get("slug") != event.get("slug"):
        raise BatchFailure("Queued JSON does not match candidate slug")
    status = api("/lor-importer/v1/status")
    if status.get("lock"):
        raise BatchFailure("Importer is currently locked")
    if queue in (status.get("processed") or {}):
        raise BatchFailure("Importer shows a processed result: do not discard")
    pending = [item for item in (status.get("pending") or []) if item.get("path") == queue]
    if len(pending) != 1:
        raise BatchFailure("Expected precisely one matching pending queue item")
    error = (status.get("errors") or {}).get(queue) or {}
    if "Numero massimo di tentativi raggiunto" not in error.get("message", ""):
        raise BatchFailure("No definitive max-attempts error; leave the queue untouched")
    if pending[0].get("attempts", 0) < 2:
        raise BatchFailure("Retry limit not confirmed")
    matches = api("/wp/v2/tribe_events?slug=" + quote(event["slug"]) + "&status=publish")
    if not isinstance(matches, list) or matches:
        raise BatchFailure("WordPress may already contain event slug; do not discard")
    finish(candidate_file, queue, "rejected")
    out={"status":"RECOVERED","failed_slug":event["slug"],"old_queue":queue,
         "reason":error["message"],"discarded_post":False,
         "recovery_time":dt.datetime.now(dt.timezone.utc).isoformat()}
    # Record only after the cleanup succeeded. A separate reporting commit is safe.
    (ROOT/"data"/"last-recovery.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    from publish_batch import commit_push
    commit_push("Record definitive importer failure recovery")
    print(json.dumps(out,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    try:
        sys.exit(main())
    except (BatchFailure,ValueError,KeyError,OSError) as exc:
        print("Safe recovery refused: "+str(exc),file=sys.stderr)
        sys.exit(3)
