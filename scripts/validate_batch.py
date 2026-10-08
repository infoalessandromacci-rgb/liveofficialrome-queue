#!/usr/bin/env python3
"""Editorial gate for Live Official Rome. This module NEVER publishes events."""
import argparse
import datetime as dt
import html
import json
import pathlib
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlsplit

CATEGORIES = {
    169: "Concerti e Live",
    268: "Teatro e Cinema",
    269: "Disco e Club",
    271: "Musei e Mostre",
    270: "Eventi e Manifestazioni",
}
ROOT = pathlib.Path(__file__).resolve().parents[1]


def normalize(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]+", " ", text.encode("ascii", "ignore").decode().lower()).strip()


def urlkey(value):
    try:
        u = urlsplit(value or "")
        return (u.netloc.lower().removeprefix("www.") + u.path.rstrip("/")).lower()
    except (TypeError, ValueError):
        return ""


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def words(value):
    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    return len(html.unescape(text).split())


def comparable(event):
    venue = event.get("venue") or {}
    if isinstance(venue, dict):
        venue = venue.get("name", "")
    seo = event.get("seo") or {}
    if not isinstance(seo, dict):
        seo = {}
    start = str(event.get("start") or event.get("start_day") or "")
    return {
        "url": urlkey(event.get("event_url", "")),
        "slug": normalize(event.get("slug")),
        "day": start[:10],
        "datetime": start[:19],
        "venue": normalize(venue),
        "focus": normalize(event.get("focus_keyphrase") or seo.get("focus_keyphrase")),
        "title": normalize(event.get("title")),
    }


def duplicate_reason(new, old):
    a, b = comparable(new), comparable(old)
    if a["url"] and a["url"] == b["url"]:
        return "duplicate event URL"
    if a["slug"] and a["slug"] == b["slug"]:
        return "duplicate slug"
    if a["venue"] and a["datetime"] and a["datetime"] == b["datetime"] and a["venue"] == b["venue"]:
        return "duplicate start datetime and venue"
    if a["day"] and a["focus"] and a["focus"] == b["focus"] and a["day"] == b["day"]:
        return "duplicate focus keyphrase and day"
    if a["day"] and a["venue"] and a["day"] == b["day"] and a["venue"] == b["venue"]:
        title_similarity = SequenceMatcher(None, a["title"], b["title"]).ratio()
        if title_similarity >= 0.68:
            return "similar title at same venue and day"
    return None


def validate(event, existing, window_start=None, window_end=None):
    problems = []
    if not isinstance(event, dict):
        return ["event must be a JSON object"]
    required = ("title", "content", "slug", "start", "end", "event_url",
                "venue", "image", "seo", "category_ids", "cost")
    problems.extend("missing " + key for key in required if not event.get(key))
    cats = event.get("category_ids")
    if not isinstance(cats, list) or len(cats) != 1 or cats[0] not in CATEGORIES:
        problems.append("must specify exactly one supported category")
    if event.get("timezone") != "Europe/Rome":
        problems.append("timezone must be Europe/Rome")
    if event.get("all_day") is not False:
        problems.append("all_day must be false")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(event.get("slug", ""))):
        problems.append("slug must use lowercase ASCII and hyphens")
    try:
        start = dt.datetime.strptime(event["start"], "%Y-%m-%d %H:%M:%S")
        end = dt.datetime.strptime(event["end"], "%Y-%m-%d %H:%M:%S")
        if end <= start:
            problems.append("end must be later than start")
        if window_start and start.date() < window_start:
            problems.append("event starts before requested week")
        if window_end and start.date() > window_end:
            problems.append("event starts after requested week")
    except (KeyError, ValueError, TypeError):
        problems.append("start/end must be valid datetimes")
    content = str(event.get("content", ""))
    if words(content) < 800:
        problems.append("article must have at least 800 actual words")
    headings = re.findall(r"<h2(?:\s[^>]*)?>(.*?)</h2\s*>", content, re.I | re.S)
    if not headings or normalize(html.unescape(re.sub("<[^>]+>", "", headings[-1]))) != "informazioni sull evento":
        problems.append("last H2 must be Informazioni sull'evento")
    for key in ("event_url",):
        if not str(event.get(key, "")).startswith("https://"):
            problems.append(key + " must be HTTPS")
    for group, keys in (
        ("venue", ("name", "address", "city")),
        ("image", ("url", "alt", "title")),
        ("seo", ("focus_keyphrase", "title", "meta_description")),
    ):
        obj = event.get(group)
        if not isinstance(obj, dict) or any(not obj.get(k) for k in keys):
            problems.append("incomplete " + group)
    image = event.get("image")
    if not isinstance(image, dict) or not str(image.get("url", "")).startswith("https://"):
        problems.append("image URL must be HTTPS")
    if isinstance(event.get("seo"), dict):
        meta = event["seo"].get("meta_description", "")
        if len(meta) > 180:
            problems.append("SEO meta description is longer than 180 characters")
    for previous in existing:
        reason = duplicate_reason(event, previous)
        if reason:
            problems.append(reason)
            break
    return problems


def priority(event):
    level = str(event.get("importance_level", "B")).upper().strip()
    tier = {"A": 0, "B": 1, "C": 2}.get(level, 3)
    try:
        number = int(event.get("priority", 100))
    except (ValueError, TypeError):
        number = 100
    return tier, number


def select_candidates(root, existing, start=None, end=None):
    pools = {key: [] for key in CATEGORIES}
    rejected = []
    accepted = []
    for path in sorted((root / "candidates").glob("*.json")):
        try:
            event = load(path)
            if isinstance(event, dict) and "events" in event:
                raise ValueError("use one event per candidate JSON")
            problems = validate(event, existing + accepted, start, end)
            if problems:
                rejected.append({"file":str(path.relative_to(root)), "title":event.get("title", "") if isinstance(event, dict) else "", "errors":problems})
            else:
                accepted.append(event)
                pools[event["category_ids"][0]].append((path, event))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            rejected.append({"file": str(path.relative_to(root)), "errors":[str(exc)]})
    for pool in pools.values():
        pool.sort(key=lambda item: (priority(item[1]), item[0].name))
    return pools, rejected


def next_monday(today=None):
    today = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=2))).date()
    return today + dt.timedelta(days=(7 - today.weekday()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="first allowed event date YYYY-MM-DD")
    parser.add_argument("--end", help="last allowed event date YYYY-MM-DD")
    parser.add_argument("--output", default="reports/validation.json")
    args = parser.parse_args()
    try:
        start = dt.date.fromisoformat(args.start) if args.start else None
        end = dt.date.fromisoformat(args.end) if args.end else None
        existing = load(ROOT / "data/active-events-index.json").get("events", [])
        pools, rejected = select_candidates(ROOT, existing, start, end)
        ready = all(pools.values())
        result = {
            "status": "READY" if ready else "NOT_READY",
            "ready": ready,
            "categories": {
                CATEGORIES[k]: {
                    "selected": str(v[0][0].relative_to(ROOT)) if v else None,
                    "alternates": max(0, len(v)-1),
                } for k, v in pools.items()
            },
            "rejected": rejected,
        }
        target = ROOT / args.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if ready else 2
    except Exception as exc:
        print("Validation failed: " + str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
