#!/usr/bin/env python3
import json, pathlib, urllib.request, urllib.error
root=pathlib.Path(__file__).resolve().parents[1]
paths=["archive/rejected/2026-10-13/2026-10-23-j-ax-atlantico.json","archive/rejected/2026-10-13/2026-10-24-minu-jovonn-illuminati.json"]
extra=[
"https://admin.vivoconcerti.com/uploads/xlarge_jax_vmm26_3456x2160_sito_4ade1200f1.jpg",
"https://binaries.radioitalia.it/2026/03/19/094923004-58b5d249-b6ba-45bb-a39f-e43058207c0e.jpg",
"https://images.ra.co/ee288ef5ced7536da901ea24bd182bd029c4100f.jpg",
"https://imgproxy.ra.co/_/quality%3A66/aHR0cHM6Ly9pbWFnZXMucmEuY28vZWUyODhlZjVjZWQ3NTM2ZGE5MDFlYTI0YmQxODJiZDAyOWM0MTAwZi5qcGc%3D",
"https://teatrobrancaccio.it/wp-content/uploads/2026/06/amelie-1920X560.jpg"]
extra.extend(["https://www.teatro.it/images/2026/03/spettacoli/main-image/teatroit-sayf-santissimo-tour-2026-concerti-date-biglietti.jpg","https://operaroma.b-cdn.net/wp-content/uploads/2025/07/Goecke-Robbins-Bausch-2025-2026-2400x870-1-130x95.jpg","https://www.estateromana.com/wp-content/uploads/2026/10/halloween-sonja-moonear-circolo-degli-illuminati-31-ottobre-2026-1.jpg","https://dkemhji6i1k0x.cloudfront.net/000_clients/461308/page/exhibition-rome-echo-a5a520.jpg","https://vive.cultura.gov.it/_cms/sites/default/files/styles/original/public/blocco-intro/1%20%281%29.jpg?itok=IsQG0OmS"])
seen=set()
for p in paths:
 d=json.loads((root/p).read_text(encoding="utf-8"))
 extra.append(d["image"]["url"])
for url in extra:
 if url in seen:continue
 seen.add(url)
 for method in ["HEAD","GET"]:
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; WordPress/6.0)","Accept":"image/avif,image/webp,image/*,*/*;q=0.8"},method=method)
   with urllib.request.urlopen(req,timeout=15) as r:
    print(json.dumps({"url":url,"method":method,"status":r.status,"content_type":r.headers.get("Content-Type"),"length":r.headers.get("Content-Length")}),flush=True)
  except Exception as e:print(json.dumps({"url":url,"method":method,"error":str(e)[:150]}),flush=True)

# read-only diagnostic execution
