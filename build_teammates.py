#!/usr/bin/env python3
"""
Teammates Score build script.

Outputs:
  data/teammates.json      data for the interactive app
  p/<slug>.html            pre-rendered, SEO-friendly stub per player (title, meta, OG)
  og.png                   default social-share image (link unfurls)

Run:  python build_teammates.py
Skip the static pages with:  python build_teammates.py --no-pages
Set your live origin with:    python build_teammates.py --site https://jsierrahoopshype.github.io/hh-teammates
"""
import csv, json, os, argparse, unicodedata, re, html
from collections import defaultdict, Counter

SCORES = {
    "Most Valuable Player": 10, "Finals MVP": 10,
    "All-NBA First Team": 4, "Defensive Player of the Year": 4,
    "All-NBA Second Team": 3, "All-NBA Third Team": 2,
    "All-Star": 1, "All-Defensive First Team": 1,
    "Rookie of the Year": 0.5, "Sixth Man of the Year": 0.5,
    "All-Defensive Second Team": 0.5, "All-Star MVP": 0.5,
    "Most Improved Player": 0.25, "All-Rookie First Team": 0.25,
    "All-Rookie Second Team": 0.125,
}
ALLNBA = {"All-NBA First Team", "All-NBA Second Team", "All-NBA Third Team"}
AWARD_LABEL = {
    "Most Valuable Player":"MVP","All-NBA First Team":"All-NBA 1st Team",
    "All-NBA Second Team":"All-NBA 2nd Team","All-NBA Third Team":"All-NBA 3rd Team",
    "All-Defensive First Team":"All-Defensive 1st Team","All-Defensive Second Team":"All-Defensive 2nd Team",
    "All-Rookie First Team":"All-Rookie 1st Team","All-Rookie Second Team":"All-Rookie 2nd Team",
}
TEAM_FALLBACK = {
    "WSC":"Washington Capitols","DTF":"Detroit Falcons","PRO":"Providence Steamrollers",
    "STB":"St. Louis Bombers","CLR":"Cleveland Rebels","CHS":"Chicago Stags","TOH":"Toronto Huskies",
    "PIT":"Pittsburgh Ironmen","BAL":"Baltimore Bullets","INJ":"Indianapolis Jets",
    "DNN":"Denver Nuggets (1949-50)","INO":"Indianapolis Olympians","AND":"Anderson Packers",
    "SHE":"Sheboygan Red Skins","WAT":"Waterloo Hawks",
}

def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii","ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+","-",s).strip("-").lower()
    return s or "player"
def lab(a): return AWARD_LABEL.get(a, a)

def load(awards_path, stats_path):
    awards_by = defaultdict(list); rings = defaultdict(int); award_team = {}
    with open(awards_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a=(row.get("AWARD") or "").strip(); p=(row.get("PLAYER / COACH") or "").strip()
            y=(row.get("YEAR") or "").strip(); t=(row.get("TEAM") or "").strip()
            if not p: continue
            if a=="NBA Champion": rings[p]+=1
            if y.isdigit() and t: award_team[(p,int(y))]=t
            if a in SCORES and y.isdigit(): awards_by[(p,int(y))].append(a)
    rosters=defaultdict(set); pseasons=defaultdict(set); pyears=defaultdict(set); ptc=defaultdict(set)
    with open(stats_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            p=(row.get("PLAYER") or "").strip(); y=(row.get("YEAR") or "").strip(); t=(row.get("TEAM") or "").strip()
            if p and y.isdigit() and t:
                yr=int(y); rosters[(yr,t)].add(p); pseasons[p].add((yr,t)); pyears[p].add(yr); ptc[(p,yr)].add(t)
    a2n=defaultdict(Counter)
    for (p,yr),abbrs in ptc.items():
        if len(abbrs)==1:
            fn=award_team.get((p,yr))
            if fn: a2n[next(iter(abbrs))][fn]+=1
    teams={ab:c.most_common(1)[0][0] for ab,c in a2n.items()}
    for ab in {t for (_,t) in rosters}: teams.setdefault(ab, TEAM_FALLBACK.get(ab,ab))
    return awards_by, rings, rosters, pseasons, pyears, teams

def build_players(awards_by, rings, rosters, pseasons, pyears):
    players=[]
    for p,seasons in pseasons.items():
        detail=[]; total=0.0; cM=cN=cS=0
        for (yr,t) in sorted(seasons):
            mates=[]; spts=0.0
            for mate in rosters[(yr,t)]:
                if mate==p: continue
                aws=awards_by.get((mate,yr))
                if not aws: continue
                mp=round(sum(SCORES[a] for a in aws),3); spts+=mp
                for a in aws:
                    if a=="Most Valuable Player": cM+=1
                    elif a in ALLNBA: cN+=1
                    elif a=="All-Star": cS+=1
                mates.append({"n":mate,"a":sorted(aws,key=lambda x:-SCORES[x]),"p":mp})
            if mates:
                mates.sort(key=lambda m:-m["p"])
                detail.append({"y":yr,"t":t,"pts":round(spts,3),"mates":mates}); total+=spts
        ns=len(pyears[p])
        players.append({"name":p,"score":round(total,3),"seasons":ns,
            "perSeason":round(total/ns,3) if ns else 0,"rings":rings.get(p,0),
            "mvp":cM,"allnba":cN,"allstar":cS,"years":sorted(pyears[p]),"detail":detail})
    players.sort(key=lambda x:-x["score"])
    used=set()
    for i,pl in enumerate(players,1):
        pl["rank"]=i; s=slugify(pl["name"]); base=s; k=2
        while s in used: s=f"{base}-{k}"; k+=1
        used.add(s); pl["slug"]=s
    return players

def write_stub(p, teams, site, outdir):
    name=html.escape(p["name"]); sc=p["score"]
    scs=str(int(sc)) if sc==int(sc) else str(round(sc,2))
    rings="🏆"*p["rings"]
    # top contributors with their headline accolades
    agg={}
    for s in p["detail"]:
        for m in s["mates"]:
            d=agg.setdefault(m["n"],Counter()); d["__p"]+=m["p"]
            for a in m["a"]: d[a]+=1
    top=sorted(agg.items(), key=lambda kv:-kv[1]["__p"])[:5]
    items=""
    for nm,c in top:
        accs=[f'{c[a]}× {lab(a)}' for a in SCORES if c.get(a)]
        items+=f"<li><b>{html.escape(nm)}</b> — {html.escape(', '.join(accs[:4]))}</li>"
    desc=(f'{p["name"]} has a Teammates Score of {scs}, ranked #{p["rank"]} of all time. '
          f'See every accolade won by the teammates {p["name"]} shared a roster with.')
    url=f'{site}/p/{p["slug"]}.html'
    doc=f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} Teammates Score — #{p['rank']} all-time | HoopsMatic</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:title" content="{name} — NBA Teammates Score">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{site}/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{name} — NBA Teammates Score">
<meta name="twitter:description" content="{html.escape(desc)}">
<meta name="twitter:image" content="{site}/og.png">
<script>location.replace("../?p={p['slug']}");</script>
</head><body>
<main>
<h1>{name} {rings}</h1>
<p>Teammates Score <strong>{scs}</strong> · #{p['rank']} all-time · {p['seasons']} seasons · {p['rings']} NBA titles.</p>
<h2>Most valuable teammates</h2>
<ul>{items}</ul>
<p><a href="../?p={p['slug']}">Open the interactive Teammates Score &rarr;</a></p>
</main></body></html>"""
    with open(os.path.join(outdir, f'{p["slug"]}.html'), "w", encoding="utf-8") as f:
        f.write(doc)

def write_default_og(path):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        print("Pillow not installed; skipping og.png (pip install pillow)"); return
    W,H=1200,630; img=Image.new("RGB",(W,H),"#0f1115"); d=ImageDraw.Draw(img)
    d.rectangle([0,0,W,16], fill="#3b82f6")
    def font(sz,bold=True):
        for p in ["C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
            try: return ImageFont.truetype(p,sz)
            except Exception: pass
        return ImageFont.load_default()
    d.text((64,150),"NBA TEAMMATES SCORE",font=font(34),fill="#8a93a6")
    d.text((60,205),"How much help did",font=font(78),fill="#f5f5f7")
    d.text((60,290),"every player have?",font=font(78),fill="#3b82f6")
    d.text((64,470),"Every teammate's accolades, scored. · HoopsMatic",font=font(30,False),fill="#8a93a6")
    img.save(path); print("Wrote", path)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--awards", default="All-Time_Database_2_0_-_Awards.csv")
    ap.add_argument("--stats",  default="All-Time_Database_2_0_-_RS_Stats__3_.csv")
    ap.add_argument("--out",    default="data/teammates.json")
    ap.add_argument("--site",   default="https://jsierrahoopshype.github.io/hh-teammates")
    ap.add_argument("--no-pages", action="store_true")
    args=ap.parse_args()

    awards_by,rings,rosters,pseasons,pyears,teams=load(args.awards,args.stats)
    players=build_players(awards_by,rings,rosters,pseasons,pyears)

    os.makedirs(os.path.dirname(args.out),exist_ok=True)
    with open(args.out,"w",encoding="utf-8") as f:
        json.dump({"scores":SCORES,"teams":teams,"players":players},f,ensure_ascii=False,separators=(",",":"))
    print(f"Wrote {args.out}: {len(players)} players, {os.path.getsize(args.out)/1024:.0f} KB")

    if not args.no_pages:
        os.makedirs("p",exist_ok=True)
        for p in players: write_stub(p, teams, args.site.rstrip("/"), "p")
        print(f"Wrote {len(players)} pre-rendered pages to p/")
        write_default_og("og.png")
        site=args.site.rstrip("/")
        sm=['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            f"<url><loc>{site}/</loc></url>"]
        for p in players:
            if p["score"]>0: sm.append(f'<url><loc>{site}/p/{p["slug"]}.html</loc></url>')
        sm.append("</urlset>")
        open("sitemap.xml","w",encoding="utf-8").write("\n".join(sm))
        open("robots.txt","w").write(f"User-agent: *\nAllow: /\nSitemap: {site}/sitemap.xml\n")
        print("Wrote sitemap.xml and robots.txt")

if __name__=="__main__":
    main()
