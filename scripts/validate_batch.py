#!/usr/bin/env python3
"""Validate candidate event JSONs and produce an auditable 5-category manifest.
No fabricated events, no WordPress writes, no deletion of unverified queue items.
"""
import argparse, datetime as dt, html, json, pathlib, re, sys
from urllib.parse import urlsplit
CATEGORIES = {169:"Concerti e Live",268:"Teatro e Cinema",269:"Disco e Club",271:"Musei e Mostre",270:"Eventi e Manifestazioni"}
ROOT=pathlib.Path(__file__).resolve().parents[1]
def normalize(s):
    import unicodedata
    s=unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+"," ",s).strip()
def urlkey(s):
    u=urlsplit(s or "")
    return (u.netloc.lower().removeprefix("www.")+u.path.rstrip("/")).lower()
def load(path):
    with open(path,encoding="utf-8") as f:return json.load(f)
def validate(e, seen, existing):
    errors=[]
    for field in ("title","content","slug","start","end","event_url","venue","image","seo","category_ids"):
        if not e.get(field):errors.append("missing "+field)
    cat=e.get("category_ids",[])
    if not isinstance(cat,list) or len(cat)!=1 or cat[0] not in CATEGORIES:errors.append("invalid category")
    if e.get("timezone")!="Europe/Rome":errors.append("timezone")
    if e.get("all_day") is not False:errors.append("all_day")
    try:
        start=dt.datetime.strptime(e["start"],"%Y-%m-%d %H:%M:%S")
        end=dt.datetime.strptime(e["end"],"%Y-%m-%d %H:%M:%S")
        if end<=start:errors.append("end before start")
    except (ValueError,KeyError,TypeError):errors.append("invalid datetime");start=None
    plain=html.unescape(re.sub("<[^>]+>"," ",e.get("content","")))
    if len(plain.split())<800:errors.append("content fewer than 800 words")
    if not re.search(r"<h2[^>]*>\s*Informazioni sull.evento\s*</h2>",e.get("content",""),re.I):errors.append("missing final information heading")
    for key in ("event_url",):
        if not str(e.get(key,"")).startswith("https://"):errors.append(key+" must use https")
    for group,keys in (("venue",("name","address","city")),("image",("url","alt","title")),("seo",("focus_keyphrase","title","meta_description"))):
        v=e.get(group,{})
        if not isinstance(v,dict) or any(not v.get(k) for k in keys):errors.append("incomplete "+group)
    if not str(e.get("image",{}).get("url","")).startswith("https://"):errors.append("image must use https")
    if start:
        day=start.date().isoformat()
        venue=normalize(e.get("venue",{}).get("name",""))
        keys={("url",urlkey(e.get("event_url"))),("slug",normalize(e.get("slug"))),("dayvenue",day+"|"+venue),("focusday",normalize(e.get("seo",{}).get("focus_keyphrase"))+"|"+day)}
        for old in existing:
            oday=str(old.get("start",old.get("start_day","")))[:10]
            ov=old.get("venue",{})
            ov=ov.get("name","") if isinstance(ov,dict) else ov
            oldkeys={("url",urlkey(old.get("event_url"))),("slug",normalize(old.get("slug"))),("dayvenue",oday+"|"+normalize(ov)),("focusday",normalize(old.get("focus_keyphrase",old.get("seo",{}).get("focus_keyphrase","")))+"|"+oday)}
            if any(v and (k,v) in oldkeys for k,v in keys):errors.append("duplicate active event");break
        if any(v and (k,v) in seen for k,v in keys):errors.append("duplicate candidate")
        if not errors:seen.update(keys)
    return errors
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--candidates",default="candidates")
    ap.add_argument("--index",default="data/active-events-index.json")
    ap.add_argument("--output",default="reports/validation.json")
    args=ap.parse_args()
    existing=load(ROOT/args.index).get("events",[])
    seen=set();valid={k:[] for k in CATEGORIES};rejected=[]
    for path in sorted((ROOT/args.candidates).glob("*.json")):
        try:
            item=load(path)
            events=item.get("events",[]) if isinstance(item,dict) and "events" in item else [item]
            for e in events:
                problems=validate(e,seen,existing)
                if problems:rejected.append({"file":str(path.relative_to(ROOT)),"title":e.get("title"),"errors":problems})
                else:valid[e["category_ids"][0]].append({"file":str(path.relative_to(ROOT)),"event":e})
        except Exception as exc:rejected.append({"file":str(path.relative_to(ROOT)),"errors":[str(exc)]})
    chosen={str(k):v[0]["file"] if v else None for k,v in valid.items()}
    result={"ready":all(chosen.values()),"categories":{CATEGORIES[k]:{"chosen":chosen[str(k)],"alternates":len(v)-1 if v else 0} for k,v in valid.items()},"rejected":rejected,"generated_at":dt.datetime.now(dt.timezone.utc).isoformat()}
    target=ROOT/args.output;target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["ready"] else 2
if __name__=="__main__":sys.exit(main())
