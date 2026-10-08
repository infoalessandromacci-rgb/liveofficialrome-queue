#!/usr/bin/env python3
"""Controlled WordPress batch importer for five event categories.

Preflight and dry-run never write to WordPress or GitHub.
Apply mode imports verified candidates, checks actual WordPress posts,
archives processed JSON, and synchronizes duplicate indexes per success.
"""
import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from validate_batch import (
    CATEGORIES, ROOT, load, normalize, select_candidates, urlkey, words,
)

SITE = "https://www.liveofficialrome.it"
REPORT = "reports/latest-batch.json"


class BatchFailure(RuntimeError):
    pass


class UncertainImport(BatchFailure):
    """An item may publish later; never enqueue a replacement while pending."""


def api(path, method="GET", payload=None):
    url = SITE + "/wp-json" + path
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "LiveRome-BatchController/2.0"}
    user, password = os.environ.get("WP_APP_USER", ""), os.environ.get("WP_APP_PASSWORD", "")
    token = os.environ.get("WP_IMPORTER_TOKEN", "")
    if user and password:
        pair = (user + ":" + password).encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(pair).decode("ascii")
    elif token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise BatchFailure("WordPress API returned HTTP " + str(exc.code) + " for " + path) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise BatchFailure("WordPress API unavailable for " + path) from exc


def git(*args):
    process = subprocess.run(
        ["git", *map(str, args)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if process.returncode:
        raise BatchFailure("Git operation failed (" + " ".join(args[:2]) + "): "
                           + (process.stderr or process.stdout)[-350:])
    return process.stdout


def commit_push(message):
    git("add", "-A")
    if not git("status", "--porcelain").strip():
        return
    git("commit", "-m", message)
    git("push", "origin", "HEAD:main")


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def preflight():
    if not ((os.environ.get("WP_APP_USER") and os.environ.get("WP_APP_PASSWORD"))
            or os.environ.get("WP_IMPORTER_TOKEN")):
        raise BatchFailure("Missing GitHub Actions WordPress application credentials.")
    account = api("/wp/v2/users/me?context=edit")
    if not isinstance(account, dict) or not account.get("id"):
        raise BatchFailure("WordPress did not confirm the authenticated user.")
    status = api("/lor-importer/v1/status")
    if not isinstance(status, dict) or status.get("status") not in ("ok", "healthy"):
        raise BatchFailure("Invalid importer status response.")
    if status.get("lock"):
        raise BatchFailure("Importer is locked: do not start a new batch.")
    if status.get("pending_count", 0):
        raise BatchFailure("Importer has pending items: do not overlap batches.")
    if status.get("stale_processed_count", 0):
        raise BatchFailure("Importer reports stale items; investigate before publishing.")
    # This proves that the application password authenticates on WordPress.
    return {"user_id": account["id"], "importer_version": status.get("version"),
            "pending_count": status.get("pending_count", 0)}


def verify_published(event, record):
    """Require independent published WordPress post, image, category and Yoast metadata."""
    if record.get("status") != "published":
        raise BatchFailure("Importer has not confirmed publication.")
    post_id = record.get("post_id")
    permalink = record.get("url")
    if not isinstance(post_id, int) or not permalink or not permalink.startswith(SITE + "/event/"):
        raise BatchFailure("Importer returned an invalid post ID or URL.")
    public = api("/tribe/events/v1/events/" + str(post_id))
    seo_post = api("/wp/v2/tribe_events/" + str(post_id))
    if public.get("status") != "publish" or seo_post.get("status") != "publish":
        raise BatchFailure("WordPress post is not published.")
    if public.get("slug") != event["slug"] or urlkey(public.get("url")) != urlkey(permalink):
        raise BatchFailure("Published post slug or permalink does not match the candidate.")
    if public.get("start_date") != event["start"] or public.get("end_date") != event["end"]:
        raise BatchFailure("Published start/end differs from candidate.")
    categories = public.get("categories") or []
    if {x.get("id") for x in categories if isinstance(x, dict)} != set(event["category_ids"]):
        raise BatchFailure("Published category is incorrect.")
    if not (public.get("image") or {}).get("url") or not (public.get("image") or {}).get("id"):
        raise BatchFailure("Published featured image missing.")
    if words(public.get("description")) < 800:
        raise BatchFailure("Published article contains fewer than 800 words.")
    if urlkey(public.get("website")) != urlkey(event.get("event_url")):
        raise BatchFailure("Published official event source differs from candidate.")
    yoast = seo_post.get("yoast_head_json") or {}
    if (normalize(yoast.get("title")) != normalize(event["seo"]["title"])
            or normalize(yoast.get("description")) != normalize(event["seo"]["meta_description"])):
        raise BatchFailure("Yoast SEO title or description was not saved.")
    if urlkey(yoast.get("canonical")) != urlkey(permalink):
        raise BatchFailure("Published canonical URL is incorrect.")
    return {"post_id": post_id, "url": permalink,
            "category": CATEGORIES[event["category_ids"][0]], "image": public["image"]["url"],
            "words": words(public["description"]), "seo_verified": True}


def index_entry(event, post_id):
    venue = normalize(event["venue"]["name"])
    keyphrase = normalize(event["seo"]["focus_keyphrase"])
    title = normalize(event["title"])
    day = event["start"][:10]
    source = urlkey(event["event_url"])
    return {
        "post_id": post_id, "title": event["title"], "slug": event["slug"],
        "start": event["start"], "end": event["end"],
        "start_day": day, "start_time": event["start"][11:],
        "venue_id": None, "venue": event["venue"]["name"],
        "category_ids": event["category_ids"], "event_url": event["event_url"],
        "focus_keyphrase": event["seo"]["focus_keyphrase"],
        "normalized": {"title": title, "focus": keyphrase, "venue": venue,
                       "event_url": source},
        "duplicate_keys": {
            "datetime_venue": event["start"] + "|" + venue,
            "day_venue": day + "|" + venue,
            "focus_day": keyphrase + "|" + day, "url": source,
        },
    }


def synchronize_indexes(event, post_id):
    active_path = ROOT / "data/active-events-index.json"
    published_path = ROOT / "data/published-events-index.json"
    active = load(active_path)
    published = load(published_path)
    entry = index_entry(event, post_id)
    for items in (active["events"], published["all_events"]):
        if not any(x.get("post_id") == post_id for x in items):
            items.append(entry)
            items.sort(key=lambda item: str(item.get("start", "")))
    active["total_active_or_future_events"] = len(active["events"])
    published["total_events"] = len(published["all_events"])
    published["active_index"] = active["events"]
    published["active_or_future_events"] = len(active["events"])
    active["generated_on"] = dt.datetime.now(ZoneInfo("Europe/Rome")).date().isoformat()
    published["generated_on"] = active["generated_on"]
    write_json(active_path, active)
    write_json(published_path, published)


def stage(path):
    """Commit unique path; old importer SHA records cannot be counted as new."""
    git("pull", "--ff-only", "origin", "main")
    name = "batch-" + uuid.uuid4().hex[:12] + "-" + path.name
    queue_path = ROOT / "queue" / name
    if queue_path.exists():
        raise BatchFailure("Queue path collision.")
    queue_path.write_bytes(path.read_bytes())
    commit_push("Queue verified event " + name)
    return "queue/" + name


def finish(path, queue_name, outcome, event=None, post_id=None):
    """Atomic local index changes + queue removal + candidate archival."""
    archived = ROOT / "archive" / ("candidates" if outcome == "published" else "rejected") \
               / dt.datetime.now(ZoneInfo("Europe/Rome")).date().isoformat() / path.name
    if archived.exists():
        raise BatchFailure("Archive file already exists: " + str(archived))
    archived.parent.mkdir(parents=True, exist_ok=True)
    queued = ROOT / queue_name
    if not queued.is_file() or not path.is_file():
        raise BatchFailure("Candidate or queue file missing before cleanup.")
    if event is not None and post_id is not None:
        synchronize_indexes(event, post_id)
    path.rename(archived)
    queued.unlink()
    commit_push("Archive " + outcome + " event " + path.name)


def process(path, event, retries, poll_seconds):
    queued = stage(path)
    # The unique queue filename cannot inherit a stale importer result.
    previous = api("/lor-importer/v1/status").get("processed", {}).get(queued)
    if previous:
        raise UncertainImport("Queue key was already processed; abort to avoid false success.")
    record = None
    for attempt in range(retries):
        try:
            api("/lor-importer/v1/run", method="POST", payload={})
        except BatchFailure:
            # A transient error can occur even after the importer processed the queue.
            pass
        status = api("/lor-importer/v1/status")
        record = (status.get("processed") or {}).get(queued)
        if record and record.get("status") in ("published", "duplicate", "failed"):
            break
        if attempt + 1 < retries:
            time.sleep(poll_seconds)
    if not record or record.get("status") not in ("published", "duplicate", "failed"):
        raise UncertainImport("Importer outcome is unknown; keep queue item; do not replace.")
    if record["status"] != "published":
        finish(path, queued, "rejected")
        return {"status": record["status"], "candidate": path.name}
    verified = verify_published(event, record)
    finish(path, queued, "published", event, verified["post_id"])
    return {"status": "published", "candidate": path.name, **verified}


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="publish live events")
    mode.add_argument("--preflight", action="store_true", help="test credentials without publishing")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--start", help="first event date, YYYY-MM-DD")
    parser.add_argument("--end", help="last event date, YYYY-MM-DD")
    args = parser.parse_args()
    report = {"mode": "publish" if args.apply else "preflight" if args.preflight else "dry-run",
              "status": "NOT_READY", "published": {}, "rejected": [], "failures": {},
              "generated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    result_code = 0
    try:
        if args.preflight:
            report["connection"] = preflight()
            report["status"] = "CONNECTED"
        else:
            existing = load(ROOT / "data/active-events-index.json").get("events", [])
            start = dt.date.fromisoformat(args.start) if args.start else None
            end = dt.date.fromisoformat(args.end) if args.end else None
            pools, report["rejected"] = select_candidates(ROOT, existing, start, end)
            report["available"] = {CATEGORIES[k]: len(v) for k, v in pools.items()}
            if not all(pools.values()):
                report["status"] = "NOT_READY"
                # Dry-run with no candidates is an informational result, not a broken workflow.
                result_code = 2 if args.apply else 0
            elif not args.apply:
                report["status"] = "READY"
            else:
                report["connection"] = preflight()
                git("pull", "--ff-only", "origin", "main")
                for category, pool in pools.items():
                    completed = False
                    for path, event in pool:
                        result = process(path, event, args.max_retries, args.poll_seconds)
                        if result["status"] == "published":
                            report["published"][CATEGORIES[category]] = result
                            completed = True
                            break
                        report["failures"][path.name] = result["status"]
                    if not completed:
                        report["failures"][CATEGORIES[category]] = "No confirmed publication"
                report["count"] = len(report["published"])
                report["status"] = "COMPLETE" if report["count"] == 5 else "PARTIAL"
                result_code = 0 if report["count"] == 5 else 1
    except (BatchFailure, ValueError, KeyError, OSError) as exc:
        report["status"] = "HALTED"
        report["failures"]["controller"] = str(exc)
        result_code = 3
    finally:
        target = ROOT / REPORT
        write_json(target, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return result_code


if __name__ == "__main__":
    sys.exit(main())
