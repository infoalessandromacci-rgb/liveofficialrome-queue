#!/usr/bin/env python3
import json,re,urllib.request,html,pathlib,datetime
pages={
"concert":"https://www.teatro.it/spettacoli/roma/atlantico-live/2026-2027/sayf-santissimo-tour",
"theater":"https://www.operaroma.it/spettacoli/goecke-robbins-bausch/",
"club":"https://www.estateromana.com/proposte/halloween-sonja-moonear-circolo-degli-illuminati-31-ottobre-2026/",
"museum":"https://www.museodiromaintrastevere.it/it/mostra-evento/thin-line",
"manifestation":"https://vive.cultura.gov.it/it/gli-etruschi-di-frontiera-nuove-scoperte-nuove-ricerche-nuove-storie"}
out={}
for name,url in pages.items():
 try:
  request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"text/html"})
  with urllib.request.urlopen(request,timeout=20) as r: src=r.read(2000000).decode("utf-8","replace")
  og=re.findall(r'<meta\\s+[^>]*?(?:property|name)=[\'"](og:image|twitter:image)[\'"][^>]*?content=[\'"]([^\'"]+)',src,re.I)
  og+= [(b,a) for a,b in re.findall(r'<meta\\s+[^>]*?content=[\'"]([^\'"]+)[\'"][^>]*?(?:property|name)=[\'"](og:image|twitter:image)[\'"]',src,re.I)]
  imgs=re.findall(r'<img[^>]+(?:src|data-src)=[\'"]([^\'"]+)',src,re.I)
  out[name]={"source":url,"og":og[:8],"images":imgs[:25],"length":len(src)}
 except Exception as e:out[name]={"error":str(e)[:300]}
p=pathlib.Path("reports/source-images-2026-10-26.json");p.parent.mkdir(exist_ok=True)
p.write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False)[:16000])

# one-time non-publishing source verification
