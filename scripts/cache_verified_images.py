#!/usr/bin/env python3
"""Authorized one-time repair: upload source images to WP media, restore candidates. Never publishes posts."""
import base64
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.request
from urllib.parse import urlsplit
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from publish_batch import ROOT, api, git, commit_push, BatchFailure, preflight

REQ=ROOT/"control"/"media-repair-request.json"
ALLOWED={
 "2026-10-23-j-ax-atlantico.json":"https://binaries.radioitalia.it/2026/03/19/094923004-58b5d249-b6ba-45bb-a39f-e43058207c0e.jpg",
 "2026-10-24-minu-jovonn-illuminati.json":"https://images.ra.co/ee288ef5ced7536da901ea24bd182bd029c4100f.jpg",
}
def main():
 request=json.loads(REQ.read_text(encoding="utf-8"))
 if request.get("approved") is not True or request.get("mode")!="cache_verified_images" or request.get("created_on")!=dt.datetime.now(dt.timezone.utc).date().isoformat():
  raise BatchFailure("Invalid or expired media repair authorization")
 selected=request.get("files",[])
 if not selected or len(set(selected))!=len(selected) or any(x not in ALLOWED for x in selected):
  raise BatchFailure("Invalid repair selection")
 conn=preflight()
 user,pw=os.environ["WP_APP_USER"],os.environ["WP_APP_PASSWORD"]
 auth="Basic "+base64.b64encode((user+":"+pw).encode()).decode()
 done=[]
 for name in selected:
  src=ROOT/"archive"/"rejected"/"2026-10-13"/name
  if not src.is_file():raise BatchFailure("Missing archived candidate")
  item=json.loads(src.read_text(encoding="utf-8"))
  matches=api("/wp/v2/tribe_events?slug="+item["slug"]+"&status=publish")
  if matches:raise BatchFailure("Event slug already published; refuse duplicate: "+item["slug"])
  image=ALLOWED[name]
  r=urllib.request.Request(image,headers={"User-Agent":"Mozilla/5.0","Accept":"image/*"})
  with urllib.request.urlopen(r,timeout=45) as resp:
   mime=(resp.headers.get("Content-Type") or "").split(";")[0].lower()
   if mime not in ("image/jpeg","image/png","image/webp"):raise BatchFailure("Bad MIME: "+mime)
   data=resp.read(5000001)
   if not data or len(data)>5000000:raise BatchFailure("Invalid image size")
  filename="liverome-"+name.replace(".json",".jpg")
  req=urllib.request.Request("https://www.liveofficialrome.it/wp-json/wp/v2/media",
    data=data,method="POST",headers={"Authorization":auth,"Content-Type":mime,
     "Content-Disposition":'attachment; filename="'+filename+'"',
     "Accept":"application/json","User-Agent":"LiveRome-Controller/2.0"})
  with urllib.request.urlopen(req,timeout=60) as resp:
   obj=json.load(resp)
  remote=obj.get("source_url")
  if not remote or not remote.startswith("https://www.liveofficialrome.it/wp-content/uploads/"):
   raise BatchFailure("WP media upload has not returned a trusted image URL")
  item["source_original_image"]=item["image"]["url"]
  item["image"]["url"]=remote
  target=ROOT/"candidates"/name
  if target.exists():raise BatchFailure("Candidate exists; refuse overwrite")
  target.write_text(json.dumps(item,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  done.append({"candidate":name,"media_id":obj["id"],"media_url":remote})
  print(json.dumps(done[-1],ensure_ascii=False),flush=True)
 commit_push("Restore two candidates with verified locally hosted official images")
 print(json.dumps({"status":"IMAGES_READY","count":len(done),"items":done,"connection":conn},ensure_ascii=False))
if __name__=="__main__":
 try: main()
 except Exception as e:
  print("Media repair stopped safely:",str(e),file=sys.stderr)
  raise
