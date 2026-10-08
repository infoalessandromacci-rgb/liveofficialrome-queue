#!/usr/bin/env python3
"""Publish a prevalidated five-category batch through Live Official Rome importer.

Requires WP_IMPORTER_TOKEN as an authorization credential if endpoint requires it.
Does not invent events, and never reports 5/5 without five confirmed new publications.
"""
import argparse, json, os, pathlib, subprocess, sys, time, urllib.request, urllib.error, base64
from validate_batch import CATEGORIES, ROOT, load, validate
SITE="https://www.liveofficialrome.it"
def request(route, method="GET", payload=None):
    url=SITE+"/wp-json/lor-importer/v1/"+route
    body=json.dumps(payload).encode() if payload is not None else None
    headers={"Accept":"application/json","User-Agent":"LiveRome-BatchController/1.0"}
    token=os.environ.get("WP_IMPORTER_TOKEN","")
    if os.environ.get("WP_APP_USER") and os.environ.get("WP_APP_PASSWORD"):
        raw=(os.environ["WP_APP_USER"]+":"+os.environ["WP_APP_PASSWORD"]).encode()
        headers["Authorization"]="Basic "+base64.b64encode(raw).decode()
    elif token:headers["Authorization"]="Bearer "+token
    if body:headers["Content-Type"]="application/json"
    with urllib.request.urlopen(urllib.request.Request(url,data=body,headers=headers,method=method),timeout=45) as response:
        return json.load(response)
def git(*args):
    subprocess.run(["git",*args],cwd=ROOT,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
def publish_candidate(path):
    destination=ROOT/"queue"/("batch-"+path.name)
    if destination.exists():raise RuntimeError("queue collision: "+destination.name)
    destination.write_bytes(path.read_bytes())
    git("add",str(destination.relative_to(ROOT)))
    git("commit","-m","Queue validated event "+destination.name)
    git("push","origin","HEAD:main")
    return "queue/"+destination.name
def remove_processed(path):
    git("rm","--",path)
    git("commit","-m","Clean processed queue item "+path)
    git("push","origin","HEAD:main")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--apply",action="store_true")
    p.add_argument("--max-retries",type=int,default=3)
    p.add_argument("--poll-seconds",type=int,default=15)
    a=p.parse_args()
    index=load(ROOT/"data/active-events-index.json").get("events",[])
    seen=set();pools={c:[] for c in CATEGORIES};rejected=[]
    for path in sorted((ROOT/"candidates").glob("*.json")):
        try:
            item=load(path)
            if isinstance(item,dict) and "events" in item:raise ValueError("one event per candidate file required")
            problems=validate(item,seen,index)
            if problems:rejected.append({"path":str(path),"errors":problems})
            else:pools[item["category_ids"][0]].append(path)
        except Exception as ex:rejected.append({"path":str(path),"errors":[str(ex)]})
    result={"published":{},"failed":{},"rejected":rejected,"ready":all(pools.values()),"mode":"apply" if a.apply else "dry-run"}
    if not a.apply:
        result["available"]={CATEGORIES[k]:len(v) for k,v in pools.items()}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result["ready"] else 2
    if not result["ready"]:
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 2
    if not (os.environ.get("WP_IMPORTER_TOKEN") or (os.environ.get("WP_APP_USER") and os.environ.get("WP_APP_PASSWORD"))):\n        result["failed"]["configuration"]="Missing WordPress credentials. Configure WP_APP_USER and WP_APP_PASSWORD or a verified WP_IMPORTER_TOKEN."\n        print(json.dumps(result,ensure_ascii=False,indent=2))\n        return 3\n    try:\n        initial_status=request("status")\n        if initial_status.get("lock") or initial_status.get("pending_count",0):\n            raise RuntimeError("Importer busy or queue not empty; refusing unsafe batch")\n    except Exception as ex:\n        result["failed"]["preflight"]=str(ex)\n        print(json.dumps(result,ensure_ascii=False,indent=2))\n        return 3\n    for cat, candidates in pools.items():
        for path in candidates:
            queued=None
            try:
                queued=publish_candidate(path)
                success=False\n                before=initial_status.get("processed",{}).get(queued)\n                if before:raise RuntimeError("Queue item was already processed; refuse stale success")
                for attempt in range(a.max_retries):
                    try:request("run",method="POST",payload={})
                    except urllib.error.HTTPError as ex:
                        if ex.code in (401,403):raise RuntimeError("Importer authorization refused")
                    time.sleep(a.poll_seconds)
                    status=request("status")
                    record=status.get("processed",{}).get(queued,{})
                    if record.get("status")=="published" and record.get("url") and record.get("post_id") and not before:
                        result["published"][CATEGORIES[cat]]={"url":record["url"],"post_id":record["post_id"],"candidate":path.name}
                        success=True
                        break
                    if record.get("status") in ("duplicate","failed"):break
                status=request("status")
                if queued in status.get("processed",{}):remove_processed(queued)
                if success:break
                result["failed"][path.name]="Not confirmed published"
            except Exception as ex:
                result["failed"][path.name]=str(ex)
                # Preserve unprocessed JSON for inspection; never silently discard.
                if "authorization" in str(ex).lower():break
        else:result["failed"][CATEGORIES[cat]]="No candidate published"
    result["count"]=len(result["published"])
    result["complete"]=result["count"]==5
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["complete"] else 1
if __name__=="__main__":sys.exit(main())
