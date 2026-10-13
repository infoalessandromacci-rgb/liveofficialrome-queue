#!/usr/bin/env python3
"""Read-only readiness check for the next five-category batch."""
import datetime as dt
import json
import pathlib
import sys
from zoneinfo import ZoneInfo
from validate_batch import ROOT, CATEGORIES, load, select_candidates

def main():
    today=dt.datetime.now(ZoneInfo("Europe/Rome")).date()
    start=today+dt.timedelta(days=7-today.weekday())
    end=start+dt.timedelta(days=6)
    existing=load(ROOT/"data/active-events-index.json").get("events",[])
    pools,rejected=select_candidates(ROOT,existing,start,end)
    selected={name:([str(p.relative_to(ROOT)) for p,_ in pools[cid]]) for cid,name in CATEGORIES.items()}
    report={
        "generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),
        "week_start":start.isoformat(),"week_end":end.isoformat(),
        "status":"READY" if all(selected.values()) else "NOT_READY",
        "publication_authorized":False,
        "counts":{name:len(files) for name,files in selected.items()},
        "candidates":selected,"rejected":rejected
    }
    output=ROOT/"reports"/"candidate-readiness.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    sys.exit(main())
