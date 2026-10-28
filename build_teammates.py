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
Pages and headshots only, from the committed data (no CSVs):  python build_teammates.py --from-json
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
# Page headshot: nba-headshots' face-fill files, the one HoopsMatic headshot (face fills the circle).
# The data's "hs" is the player's file stem ("<nba_id>-<slug>") plus ".png", set by attach_headshots()
# only when the player's NBA id is certain; face-fill uses the same stems as .webp.
# og:image keeps the PNG in face/: social previews need an opaque image.
HS_BASE = "https://jsierrahoopshype.github.io/nba-headshots/players/headshots/face-fill/"
OG_HS_BASE = "https://jsierrahoopshype.github.io/nba-headshots/players/headshots/face/"
FACE_FILL_LIST = "https://raw.githubusercontent.com/jsierrahoopshype/nba-headshots/main/players/headshots/face-fill/.hashes.json"
PLAYERS_ALL = "https://raw.githubusercontent.com/jsierrahoopshype/nba-headshots/main/players/metadata/players_all.json"

def fetch_json(url):
    import urllib.request
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())

def load_face_fill():
    """The stems that have a face-fill file (public file, no key). None if it can't be fetched:
    then every photo is kept and the page's onerror shows initials for any that is missing."""
    try:
        stems=set(fetch_json(FACE_FILL_LIST)["files"])
        print(f"face-fill list: {len(stems)} players")
        return stems
    except Exception as e:
        print(f"face-fill list not fetched ({e}); keeping every photo, initials if one fails to load")
        return None

# ---- Which NBA id is this player? Only certain answers get a photo; anything else stays on initials. ----
NAME_SUFFIXES = {"jr","sr","ii","iii","iv"}
def base_name(n):
    """normalized name without Jr./Sr./II/III/IV"""
    return " ".join(w for w in n.split() if w not in NAME_SUFFIXES)
def strip_birth_year(name):
    """The stats data tells same-name players apart with a birth year: 'Kevin Porter (1950)'."""
    return re.sub(r"\s*\(\d{4}\)\s*$","",name)
def birth_year(name):
    m=re.search(r"\((\d{4})\)\s*$",name)
    return int(m.group(1)) if m else None

def era_ok(nba_id, first, last, seasons_from=None, born=None):
    """Can this NBA id belong to a career running first..last (season end years)? NBA.com hands out ids in
    blocks by era, so some careers rule an id out for sure. Used only to rule ids out, never to pick one.
      76000-79999  players who were done before 1996-97 (NBA.com's legacy block): last season <= 1998
      1-4999       ids handed out 1996-2004 (latest debut seen: 2010, a draft-and-stash): first season <= 2012
      200000-209999  ids handed out from 2005-06 on: first season >= 2005
      1626000+     ids handed out from 2015-16 on: first season >= 2015
    born (the data's "(1986)" birth year, when there is one): ids 1-999 went to the 1996-97 players and the
    1996 draft (Kobe Bryant, 977, born 1978), so their players were born by 1980 (Reggie Williams (1986)
    can't be 199, the 1987-97 Reggie Williams); ids 1000-4999 were handed out by 2004: born by 1987.
    seasons_from (current players in nba-headshots) is NBA.com's first year for him: the data's first season
    (an end year) can't come before it, and at most 5 years after it (Joel Embiid: 2014, first season 2017)."""
    if 76000<=nba_id<80000 and last>1998: return False
    if nba_id<5000 and first>2012: return False
    if 200000<=nba_id<210000 and first<2005: return False
    if nba_id>=1626000 and first<2015: return False
    if born and nba_id<1000 and born>1980: return False
    if born and nba_id<5000 and born>1987: return False
    if seasons_from:
        try:
            if not int(seasons_from)<=first<=int(seasons_from)+5: return False
        except ValueError: pass
    return True

def load_nba_index(ids_path, dupes_path, players_all):
    """{base name: {nba_id: set of full normalized names}} over every NBA player: data/headshot_ids.json
    (one id per name), data/headshot_ids_dupes.json (every id when several players share a name) and
    nba-headshots' players_all.json (adds the newest players). Also {nba_id: seasons_from}."""
    idx=defaultdict(lambda: defaultdict(set)); since={}
    def add(name,i):
        n=norm_name(name); idx[base_name(n)][int(i)].add(n)
    for n,i in json.load(open(ids_path,encoding="utf-8")).items(): add(n,i)
    if os.path.exists(dupes_path):
        for n,v in json.load(open(dupes_path,encoding="utf-8")).items():
            for i in v["all_ids"]: add(n,i)
    for p in players_all:
        add(p["full_name"],p["nba_id"])
        if p.get("seasons_from"): since[int(p["nba_id"])]=p["seasons_from"]
    return idx, since

def match_nba_id(p, idx, since):
    """(nba_id, None) when certain, else (None, why). Every NBA player sharing the name (with or without
    Jr./Sr./II) is a candidate; a name that carries a suffix keeps only the exact-name ones when there are
    any. Candidates whose id era can't fit the career are dropped; exactly one must be left."""
    tn=norm_name(strip_birth_year(p["name"])); tb=base_name(tn)
    cands=idx.get(tb,{})
    if not cands: return None,"no NBA player by that name"
    if tn!=tb:
        exact={i:ns for i,ns in cands.items() if tn in ns}
        if exact: cands=exact
    yrs=p.get("years") or []
    if not yrs: return None,"no seasons"
    keep=[i for i in cands if era_ok(i,yrs[0],yrs[-1],since.get(i),birth_year(p["name"]))]
    if len(keep)==1: return keep[0],None
    if not keep: return None,f"no candidate fits {yrs[0]}-{yrs[-1]}: {sorted(cands)}"
    return None,f"same name, can't tell apart: {sorted(keep)}"

def name_key(s):
    """A name or a file stem's name part, compared the way slugs are: accents stripped, punctuation
    ignored, Jr./Sr./II/III/IV dropped. 'Shaquille O'Neal' and 'shaquille-oneal' both give 'shaquilleoneal'."""
    s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().lower()
    s=re.sub(r"[.'’`]","",s)                       # O'Neal, Jr. -> oneal, jr
    return "".join(w for w in re.split(r"[^a-z0-9]+",s) if w and w not in NAME_SUFFIXES)

def stems_by_id(stems):
    """{nba_id: sorted list of face-fill stems '<id>-<name>'}; some ids have more than one file."""
    out=defaultdict(list)
    for s in stems:
        head=s.split("-",1)[0]
        if head.isdigit(): out[int(head)].append(s)
    return {i:sorted(v) for i,v in out.items()}

def pick_stem(cands, name):
    """The face-fill stem for this player among his id's files. One file: that file. Two or more (the
    shared repo has ids whose files carry different players' names): only the file whose name part
    matches his name, else None (initials). Never by order or at random."""
    if not cands: return None
    if len(cands)==1: return cands[0]
    want=name_key(strip_birth_year(name))
    hits=[s for s in cands if name_key(s.split("-",1)[1] if "-" in s else "")==want]
    return hits[0] if len(hits)==1 else None

def attach_headshots(players, stems, idx, since):
    """Set p["hs"] = '<stem>.png' for players whose NBA id is certain and who have a face-fill file;
    remove it otherwise. An id claimed by two players goes to neither. An id with several files
    gets the one named after the player (pick_stem)."""
    stem_by_id=stems_by_id(stems)
    found={}; why={}
    for p in players:
        i,r=match_nba_id(p,idx,since)
        if i is None: why[p["name"]]=r
        else: found[p["name"]]=i
    claims=Counter(found.values())
    for n,i in list(found.items()):
        if claims[i]>1: why[n]=f"id {i} also matched another player"; del found[n]
    before=sum(1 for p in players if p.get("hs")); hits=0
    for p in players:
        s=pick_stem(stem_by_id.get(found.get(p["name"])),p["name"])
        if s: p["hs"]=f"{s}.png"; hits+=1
        else: p.pop("hs",None)
    print(f"Headshots: {hits}/{len(players)} players have a face-fill photo (was {before}); "
          f"{len(found)} NBA ids certain, {len(why)} not")
    ambiguous={n:r for n,r in why.items() if not r.startswith("no NBA player")}
    for n in sorted(ambiguous): print(f"  initials: {n} - {ambiguous[n]}")
    return hits

def face_fill_file(hs, stems):
    """'<stem>.png' -> '<stem>.webp' when face-fill has that player, else '' (initials)."""
    if not hs: return ""
    stem=hs.rsplit(".",1)[0]
    return f"{stem}.webp" if stems is None or stem in stems else ""

def initials(name):
    w=[x for x in re.sub(r"[.,]","",name).split() if x.lower() not in ("jr","sr","ii","iii","iv")]
    return ((w[0][0]+(w[-1][0] if len(w)>1 else "")).upper()) if w else ""
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
.phead{display:flex;align-items:center;gap:.9rem;margin-bottom:1rem}
.hs{flex:none;width:72px;height:72px;border-radius:50%;overflow:hidden;object-fit:cover;background:#e8e8ed}
.hs.imgfail{display:none}
.hs.ini{display:flex;align-items:center;justify-content:center;font-weight:700;font-size:1.5rem;color:#8e8e93}
.hs.ini[hidden]{display:none}
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
.contact{max-width:760px;margin:0 auto;padding:0 1rem 2rem;text-align:center;font-size:.75rem;color:var(--text-secondary);line-height:1.7}
.contact a{color:inherit;text-decoration:underline}
@media(min-width:640px){.container{padding:1.5rem 1.5rem 4rem}h1{font-size:2.1rem}.hs{width:96px;height:96px}.num{font-size:1.4rem}.cta{display:inline-block;padding:.75rem 1.4rem}}"""
# Fonts are self-hosted (assets/fonts, OFL licences next to the files): nothing loads from Google.
# Same families, latin subset, variable weight, as the Google Fonts files the pages used before.
# First source: /teammates/assets/fonts/, where hoopsmatic.com serves this repo's files (the Worker
# proxies that folder). Second: the path relative to the page, for the github.io copy.
def font_faces(prefix):
    """@font-face rules for DM Sans and JetBrains Mono; prefix leads from the page to the repo root ('' or '../')."""
    return "".join(
        f"@font-face{{font-family:'{fam}';src:url(/teammates/assets/fonts/{fn}) format('woff2'),"
        f"url({prefix}assets/fonts/{fn}) format('woff2');font-weight:{w};font-style:normal;font-display:swap}}\n"
        for fam,fn,w in (("DM Sans","dm-sans-latin.woff2","100 1000"),
                         ("JetBrains Mono","jetbrains-mono-latin.woff2","400 800")))
# Every page ends with these two lines (Jorge's site-wide footer), after the page's own content.
CONTACT_LINES = (("Anything wrong? Email us at ","hoopsmatic@hoopsmatic.com"),
                 ("For business inquiries, contact us at ","ads@hoopsmatic.com"))
CONTACT_FOOTER = ('<footer class="contact">'
                  + "".join(f'<p>{t}<a href="mailto:{a}">{a}</a></p>' for t,a in CONTACT_LINES)
                  + '</footer>')
FOOT = ("Teammates Score adds up the accolades of every teammate a player shared a season with: MVP &amp; Finals MVP 10, "
        "All-NBA 1st 4, DPOY 4, All-NBA 2nd 3, 3rd 2, All-Star &amp; All-D 1st 1, down to All-Rookie 2nd 0.125. "
        "A teammate's MVP already covers his All-NBA selection that season (and DPOY covers All-Defensive), so those aren't counted twice.")

def stub_content(p, site, stems=None):
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
            "rings":p["rings"],"hs":face_fill_file(p.get("hs"),stems),"desc":desc,"url":f'{site}/p/{p["slug"]}.html',
            "og_img":(OG_HS_BASE+p["hs"]) if p.get("hs") else f"{site}/og.png","mates":mates,
            "contact":[t+a for t,a in CONTACT_LINES]}

def content_hash(c):
    return hashlib.sha256(json.dumps(c,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()[:16]

def write_stub(c, outdir):
    name=html.escape(c["name"]); desc=html.escape(c["desc"]); slug=c["slug"]
    def plural(n,one,many): return one if n==1 else many
    # no face-fill file, or one that fails to load: the player's initials in the same circle
    ini=f'<span class="hs ini" aria-hidden="true"{" hidden" if c["hs"] else ""}>{html.escape(initials(c["name"]))}</span>'
    photo=(f'<img class="hs" src="{HS_BASE}{html.escape(c["hs"])}" alt="{name}" width="96" height="96" '
           f'onerror="this.classList.add(\'imgfail\');this.nextElementSibling.hidden=false">' if c["hs"] else "")+ini
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
<style>{font_faces("../")}{STUB_CSS}</style>
</head><body>
<main class="container">
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
</main>
{CONTACT_FOOTER}
</body></html>"""
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
    ap.add_argument("--ids", default="data/headshot_ids.json", help="normalized name -> NBA id")
    ap.add_argument("--ids-dupes", default="data/headshot_ids_dupes.json", help="names several NBA players share -> all their ids")
    ap.add_argument("--no-pages", action="store_true")
    ap.add_argument("--hashes", default="data/page_hashes.json", help="per-page content hashes + lastmod dates (commit this)")
    ap.add_argument("--date", help="override the build date (YYYY-MM-DD) used for changed pages' <lastmod>")
    ap.add_argument("--from-json", action="store_true",
                    help="skip the CSVs: rebuild p/, sitemap.xml and robots.txt from the existing --out data file")
    args=ap.parse_args()

    if args.from_json:
        # Rebuild from the committed data file (no CSVs needed); only the players' headshots ("hs") are refreshed.
        with open(args.out,encoding="utf-8") as f: data=json.load(f)
        players,teams=data["players"],data["teams"]
        print(f"Loaded {args.out}: {len(players)} players")
    else:
        awards_by,rings,rosters,pseasons,pyears,teams,title_years=load(args.awards,args.stats)
        players=build_players(awards_by,rings,rosters,pseasons,pyears,title_years)

    # Headshots: both public nba-headshots files are needed; if either can't be fetched, keep the "hs" already there.
    stems=load_face_fill()
    try: players_all=fetch_json(PLAYERS_ALL)["players"]
    except Exception as e: players_all=None; print(f"players_all.json not fetched ({e})")
    if stems is not None and players_all is not None:
        idx,since=load_nba_index(args.ids,args.ids_dupes,players_all)
        attach_headshots(players,stems,idx,since)
    else:
        print("Headshots left as they were")

    os.makedirs(os.path.dirname(args.out),exist_ok=True)
    with open(args.out,"w",encoding="utf-8") as f:
        json.dump({"scores":SCORES,"teams":teams,"players":players},f,ensure_ascii=False,separators=(",",":"))
    print(f"Wrote {args.out}: {len(players)} players, {os.path.getsize(args.out)/1024:.0f} KB")

    if not args.no_pages:
        os.makedirs("p",exist_ok=True)
        site=args.site.rstrip("/"); hashes={}
        for p in players:
            c=stub_content(p, site, stems); write_stub(c, "p"); hashes[p["slug"]]=content_hash(c)
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
