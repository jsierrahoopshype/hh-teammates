#!/usr/bin/env python3
"""
Teammates Score build script.

Outputs:
  data/teammates.json      data for the interactive app
  p/<slug>.html            pre-rendered, SEO-friendly stub per player (title, meta, OG)
  og.png                   default social-share image (link unfurls)
  sitemap.xml, robots.txt  sitemap with per-URL <lastmod>
  data/page_hashes.json    content hash + lastmod date per page (commit it; dates only move when content changes)

Run:  python build_teammates.py
Pages only, from the committed data (no CSVs):  python build_teammates.py --from-json
Skip the static pages with:  python build_teammates.py --no-pages
Set your live origin with:    python build_teammates.py --site https://jsierrahoopshype.github.io/hh-teammates
"""
import csv, json, os, argparse, unicodedata, re, html, hashlib, datetime
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
ALLDEF = {"All-Defensive First Team", "All-Defensive Second Team"}
AWARD_LABEL = {
    "Most Valuable Player":"MVP","All-NBA First Team":"All-NBA 1st Team",
    "All-NBA Second Team":"All-NBA 2nd Team","All-NBA Third Team":"All-NBA 3rd Team",
    "All-Defensive First Team":"All-Defensive 1st Team","All-Defensive Second Team":"All-Defensive 2nd Team",
    "All-Rookie First Team":"All-Rookie 1st Team","All-Rookie Second Team":"All-Rookie 2nd Team",
}
HS_BASE = "https://jsierrahoopshype.github.io/nba-headshots/players/headshots/face/"
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
def norm_name(s):
    s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+"," ",s).strip()
def load_headshots(path):
    if not os.path.exists(path): return {}
    try: data=json.load(open(path,encoding="utf-8"))
    except Exception: return {}
    m={}
    for p in data.get("players",[]):
        fn=(p.get("headshot") or {}).get("filename")
        if fn: m[norm_name(p.get("full_name",""))]=fn
    return m

def load(awards_path, stats_path):
    awards_by = defaultdict(list); rings = defaultdict(int); award_team = {}
    title_years = defaultdict(set)
    with open(awards_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a=(row.get("AWARD") or "").strip(); p=(row.get("PLAYER / COACH") or "").strip()
            y=(row.get("YEAR") or "").strip(); t=(row.get("TEAM") or "").strip()
            if not p: continue
            if a=="NBA Champion":
                rings[p]+=1
                if y.isdigit(): title_years[p].add(int(y))
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
    return awards_by, rings, rosters, pseasons, pyears, teams, title_years

def build_players(awards_by, rings, rosters, pseasons, pyears, title_years):
    players=[]
    for p,seasons in pseasons.items():
        detail=[]; total=0.0; cM=cN=cS=0
        for (yr,t) in sorted(seasons):
            mates=[]; spts=0.0
            for mate in rosters[(yr,t)]:
                if mate==p: continue
                aws=awards_by.get((mate,yr))
                if not aws: continue
                sset=set(aws); has_mvp="Most Valuable Player" in sset; has_dpoy="Defensive Player of the Year" in sset
                ordered=sorted(aws,key=lambda x:-SCORES[x]); sp=[]
                for a in ordered:
                    pts=SCORES[a]
                    if has_mvp and a in ALLNBA: pts=0          # MVP already covers the All-NBA nod
                    elif has_dpoy and a in ALLDEF: pts=0       # DPOY already covers All-Defensive
                    sp.append(pts)
                mp=round(sum(sp),3); spts+=mp
                for a in aws:
                    if a=="Most Valuable Player": cM+=1
                    elif a in ALLNBA: cN+=1
                    elif a=="All-Star": cS+=1
                mates.append({"n":mate,"a":ordered,"sp":[round(x,3) for x in sp],"p":mp})
            if mates:
                mates.sort(key=lambda m:-m["p"])
                detail.append({"y":yr,"t":t,"pts":round(spts,3),"mates":mates}); total+=spts
        ns=len(pyears[p])
        players.append({"name":p,"score":round(total,3),"seasons":ns,
            "perSeason":round(total/ns,3) if ns else 0,"rings":rings.get(p,0),
            "mvp":cM,"allnba":cN,"allstar":cS,"years":sorted(pyears[p]),
            "titleYears":sorted(title_years.get(p,[])),"detail":detail})
    players.sort(key=lambda x:-x["score"])
    used=set()
    for i,pl in enumerate(players,1):
        pl["rank"]=i; s=slugify(pl["name"]); base=s; k=2
        while s in used: s=f"{base}-{k}"; k+=1
        used.add(s); pl["slug"]=s
    return players

# Shared look for p/<slug>.html: colors, fonts and card style mirror index.html. Mobile first.
STUB_CSS = """:root{--bg:#f5f5f7;--surface:#fff;--surface-hover:#f0f0f2;--border:#d1d1d6;--text:#1d1d1f;--text-secondary:#6e6e73;--accent:#3b82f6;--accent-dim:rgba(59,130,246,.15)}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'DM Sans',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;-webkit-font-smoothing:antialiased;overflow-wrap:anywhere}
a{color:var(--accent);text-decoration:none}
.container{max-width:760px;margin:0 auto;padding:1rem 1rem 3rem}
.kick{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:.7rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.08em;margin-bottom:1rem}
.kick:hover{color:var(--accent)}
.phead{display:flex;align-items:center;gap:.9rem;margin-bottom:1rem}
.hs{flex:none;width:72px;height:72px;border-radius:14px;object-fit:cover;object-position:50% 16%;background:var(--surface-hover);border:1px solid var(--border)}
.hs.imgfail{display:none}
.phead div{min-width:0}
h1{font-size:1.65rem;font-weight:800;letter-spacing:-.03em;line-height:1.1}
.rings{display:block;font-size:.95rem;margin-top:.3rem}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.4rem;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:.8rem .5rem;margin-bottom:1rem;font-family:'JetBrains Mono',monospace;text-align:center}
.num{font-size:1.15rem;font-weight:700;line-height:1.2}
.num.accent{color:var(--accent)}
.lbl{font-size:.6rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.05em;line-height:1.25;margin-top:.2rem}
.cta{display:block;text-align:center;font-family:'JetBrains Mono',monospace;font-size:.85rem;font-weight:600;padding:.85rem 1rem;border-radius:10px;background:var(--accent);color:#fff;margin-bottom:1.5rem}
.cta:hover{opacity:.92}
h2{font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:var(--text-secondary);font-weight:700;margin-bottom:.6rem}
.mates{list-style:none;display:flex;flex-direction:column;gap:.6rem}
.mate{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:.8rem .9rem}
.mate b{font-weight:600;font-size:.98rem}
.accs{list-style:none;display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.4rem}
.accs li{font-family:'JetBrains Mono',monospace;font-size:.7rem;font-weight:600;padding:.15rem .5rem;border-radius:5px;background:var(--accent-dim);color:#1d4ed8}
.empty{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1rem;color:var(--text-secondary);font-size:.9rem}
.foot{font-size:.72rem;color:var(--text-secondary);margin-top:1.6rem;font-family:'JetBrains Mono',monospace;line-height:1.7}
@media(min-width:640px){.container{padding:1.5rem 1.5rem 4rem}h1{font-size:2.1rem}.hs{width:96px;height:96px}.num{font-size:1.4rem}.cta{display:inline-block;padding:.75rem 1.4rem}}"""
FONTS_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
              '<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">')
FOOT = ("Teammates Score adds up the accolades of every teammate a player shared a season with: MVP &amp; Finals MVP 10, "
        "All-NBA 1st 4, DPOY 4, All-NBA 2nd 3, 3rd 2, All-Star &amp; All-D 1st 1, down to All-Rookie 2nd 0.125. "
        "A teammate's MVP already covers his All-NBA selection that season (and DPOY covers All-Defensive), so those aren't counted twice.")

def stub_content(p, site):
    """Everything a player page says, without markup. The page is rendered from this, and its hash drives sitemap <lastmod>."""
    sc=p["score"]; scs=str(int(sc)) if sc==int(sc) else str(round(sc,2))
    # top contributors with their headline accolades
    agg={}
    for s in p["detail"]:
        for m in s["mates"]:
            d=agg.setdefault(m["n"],Counter()); d["__p"]+=m["p"]
            for a in m["a"]: d[a]+=1
    top=sorted(agg.items(), key=lambda kv:-kv[1]["__p"])[:5]
    mates=[[nm,[f'{c[a]}× {lab(a)}' for a in SCORES if c.get(a)][:4]] for nm,c in top]
    desc=(f'{p["name"]} has a Teammates Score of {scs}, ranked #{p["rank"]} of all time. '
          f'See every accolade won by the teammates {p["name"]} shared a roster with.')
    return {"name":p["name"],"slug":p["slug"],"score":scs,"rank":p["rank"],"seasons":p["seasons"],
            "rings":p["rings"],"hs":p.get("hs") or "","desc":desc,"url":f'{site}/p/{p["slug"]}.html',
            "og_img":(HS_BASE+p["hs"]) if p.get("hs") else f"{site}/og.png","mates":mates}

def content_hash(c):
    return hashlib.sha256(json.dumps(c,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()[:16]

def write_stub(c, outdir):
    name=html.escape(c["name"]); desc=html.escape(c["desc"]); slug=c["slug"]
    def plural(n,one,many): return one if n==1 else many
    photo=(f'<img class="hs" src="{HS_BASE}{html.escape(c["hs"])}" alt="{name}" width="96" height="96" '
           f'onerror="this.classList.add(\'imgfail\')">') if c["hs"] else ""
    rings=(f'<span class="rings" role="img" aria-label="{c["rings"]} NBA {plural(c["rings"],"title","titles")}">'
           f'{"🏆"*c["rings"]}</span>') if c["rings"] else ""
    items=""
    for nm,accs in c["mates"]:
        chips="".join(f"<li>{html.escape(a)}</li>" for a in accs)
        items+=f'<li class="mate"><b>{html.escape(nm)}</b><ul class="accs">{chips}</ul></li>'
    mates=f'<ul class="mates">{items}</ul>' if items else '<p class="empty">No award-winning teammates on record.</p>'
    # <head> tags (title, meta, canonical, OG/Twitter, redirect line) are unchanged from the original stub;
    # the hoopsmatic.com Worker strips the location.replace line, so keep it on its own line.
    doc=f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} Teammates Score — #{c['rank']} all-time | HoopsMatic</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{c['url']}">
<meta property="og:type" content="website">
<meta property="og:title" content="{name} — NBA Teammates Score">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{c['url']}">
<meta property="og:image" content="{c['og_img']}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{name} — NBA Teammates Score">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{c['og_img']}">
<script>location.replace("../?p={slug}");</script>
{FONTS_LINK}
<style>{STUB_CSS}</style>
</head><body>
<main class="container">
<a class="kick" href="../">NBA Teammates Score · HoopsMatic</a>
<header class="phead">{photo}<div><h1>{name}</h1>{rings}</div></header>
<div class="stats">
<div class="stat"><div class="num accent">{c['score']}</div><div class="lbl">Teammates Score</div></div>
<div class="stat"><div class="num">#{c['rank']}</div><div class="lbl">All-time rank</div></div>
<div class="stat"><div class="num">{c['seasons']}</div><div class="lbl">{plural(c['seasons'],"Season","Seasons")}</div></div>
<div class="stat"><div class="num">{c['rings']}</div><div class="lbl">NBA {plural(c['rings'],"title","titles")}</div></div>
</div>
<a class="cta" href="../?p={slug}">Open {name} in Teammates Score &rarr;</a>
<h2>Most valuable teammates</h2>
{mates}
<p class="foot">{FOOT}</p>
</main></body></html>"""
    with open(os.path.join(outdir, f'{slug}.html'), "w", encoding="utf-8") as f:
        f.write(doc)

def update_lastmod(hashes_path, entries, today):
    """entries: {key: content hash}. A key's date moves to today only when its hash changes (or it is new)."""
    old={}
    if os.path.exists(hashes_path):
        with open(hashes_path,encoding="utf-8") as f: old=json.load(f)
    out={}; changed=0
    for k,h in entries.items():
        prev=old.get(k)
        if prev and prev.get("h")==h: out[k]=prev
        else: out[k]={"h":h,"d":today}; changed+=1
    os.makedirs(os.path.dirname(hashes_path),exist_ok=True)
    with open(hashes_path,"w",encoding="utf-8") as f:   # one page per line keeps git diffs readable
        f.write("{\n"+",\n".join(f'{json.dumps(k,ensure_ascii=False)}:{json.dumps(out[k],sort_keys=True)}' for k in sorted(out))+"\n}\n")
    print(f"Page hashes: {changed} new/changed of {len(out)} (dated {today}); {len(set(old)-set(out))} dropped")
    return out

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
    ap.add_argument("--headshots", default="data/headshots.json")
    ap.add_argument("--no-pages", action="store_true")
    ap.add_argument("--hashes", default="data/page_hashes.json", help="per-page content hashes + lastmod dates (commit this)")
    ap.add_argument("--date", help="override the build date (YYYY-MM-DD) used for changed pages' <lastmod>")
    ap.add_argument("--from-json", action="store_true",
                    help="skip the CSVs: rebuild p/, sitemap.xml and robots.txt from the existing --out data file")
    args=ap.parse_args()

    if args.from_json:
        # Rebuild pages/sitemap from the committed data file (no CSVs needed); data is left untouched.
        with open(args.out,encoding="utf-8") as f: data=json.load(f)
        players,teams=data["players"],data["teams"]
        print(f"Loaded {args.out}: {len(players)} players")
    else:
        awards_by,rings,rosters,pseasons,pyears,teams,title_years=load(args.awards,args.stats)
        players=build_players(awards_by,rings,rosters,pseasons,pyears,title_years)
        hs=load_headshots(args.headshots); hits=0
        for p in players:
            f=hs.get(norm_name(p["name"]))
            if f: p["hs"]=f; hits+=1
        print(f"Headshots attached: {hits}/{len(players)} players")

        os.makedirs(os.path.dirname(args.out),exist_ok=True)
        with open(args.out,"w",encoding="utf-8") as f:
            json.dump({"scores":SCORES,"teams":teams,"players":players},f,ensure_ascii=False,separators=(",",":"))
        print(f"Wrote {args.out}: {len(players)} players, {os.path.getsize(args.out)/1024:.0f} KB")

    if not args.no_pages:
        os.makedirs("p",exist_ok=True)
        site=args.site.rstrip("/"); hashes={}
        for p in players:
            c=stub_content(p, site); write_stub(c, "p"); hashes[p["slug"]]=content_hash(c)
        print(f"Wrote {len(players)} pre-rendered pages to p/")
        if not args.from_json: write_default_og("og.png")
        # Home page: its date follows the app file and its data.
        h=hashlib.sha256()
        for fn in ("index.html", args.out):
            if os.path.exists(fn): h.update(open(fn,"rb").read())
        hashes["/"]=h.hexdigest()[:16]
        today=args.date or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        lm=update_lastmod(args.hashes, hashes, today)
        sm=['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            f'<url><loc>{site}/</loc><lastmod>{lm["/"]["d"]}</lastmod></url>']
        for p in players:
            if p["score"]>0: sm.append(f'<url><loc>{site}/p/{p["slug"]}.html</loc><lastmod>{lm[p["slug"]]["d"]}</lastmod></url>')
        sm.append("</urlset>")
        open("sitemap.xml","w",encoding="utf-8").write("\n".join(sm))
        open("robots.txt","w").write(f"User-agent: *\nAllow: /\nSitemap: {site}/sitemap.xml\n")
        print("Wrote sitemap.xml and robots.txt")

if __name__=="__main__":
    main()
