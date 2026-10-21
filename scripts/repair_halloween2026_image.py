#!/usr/bin/env python3
"""One-time, tightly-scoped repair for a rejected Oct 31 candidate; no post publication."""
import base64,datetime as dt,io,json,os,pathlib,sys,urllib.request
from urllib.parse import quote
from PIL import Image
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from publish_batch import ROOT,api,preflight,commit_push,BatchFailure
PATH=ROOT/"control"/"halloween-image-repair.json"
def main():
 req=json.loads(PATH.read_text(encoding="utf-8"))
 if req.get("approved") is not True or req.get("date") != dt.datetime.now(dt.timezone.utc).date().isoformat():
  raise BatchFailure("No valid same-day repair approval")
 name="2026-10-31-minu-halloween-sonja-moonear.json"
 src=ROOT/"archive"/"rejected"/"2026-10-21"/name
 dst=ROOT/"candidates"/name
 if not src.is_file() or dst.exists():raise BatchFailure("Unexpected archive/candidate state")
 event=json.loads(src.read_text(encoding="utf-8"))
 posts=api("/wp/v2/tribe_events?slug="+quote(event["slug"])+"&status=publish")
 if posts:raise BatchFailure("Existing published slug")
 print("Preflight:",preflight(),flush=True)
 u=event["image"]["url"]
 r=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"image/*"})
 with urllib.request.urlopen(r,timeout=35) as response:
  if not (response.headers.get("content-type") or "").startswith("image/"):raise BatchFailure("Not an image")
  raw=response.read(5000001)
 if len(raw)>5000000 or len(raw)<1000:raise BatchFailure("Unsafe source image size")
 img=Image.open(io.BytesIO(raw)).convert("RGB")
 if img.width<500 or img.height<300:raise BatchFailure("Source resolution too small")
 buf=io.BytesIO()
 img.save(buf,format="JPEG",quality=88,optimize=True)
 username=os.environ["WP_APP_USER"];password=os.environ["WP_APP_PASSWORD"]
 auth=base64.b64encode((username+":"+password).encode()).decode()
 target="liverome-minu-sonja-halloween-2026-verified.jpg"
 w=urllib.request.Request("https://www.liveofficialrome.it/wp-json/wp/v2/media",method="POST",data=buf.getvalue(),headers={
  "Authorization":"Basic "+auth,"Content-Type":"image/jpeg","Content-Disposition":'attachment; filename="'+target+'"',"Accept":"application/json","User-Agent":"LiveRome-BatchController/2.0"})
 with urllib.request.urlopen(w,timeout=60) as response:media=json.load(response)
 media_url=media.get("source_url","")
 if not media_url.startswith("https://www.liveofficialrome.it/wp-content/uploads/"):
  raise BatchFailure("Media not verified")
 event["image"]["source_original"]=u
 event["image"]["url"]=media_url
 dst.write_text(json.dumps(event,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 commit_push("Restore MINU Halloween with verified WordPress-hosted JPEG")
 print(json.dumps({"status":"READY","media_id":media["id"],"image":media_url},ensure_ascii=False),flush=True)
if __name__=="__main__": main()
