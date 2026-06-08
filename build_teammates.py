#!/usr/bin/env python3
"""
Teammates Score build script -> data/teammates.json
Run:  python build_teammates.py

Per player: score, perSeason, rank, seasons, rings (own titles),
mvp/allnba/allstar (teammate-accolade counts), slug (SEO URL), and detail.
Output also carries a `teams` map: abbreviation -> full franchise name,
inferred from the data so the front-end can show "Boston Celtics" not "BOS".
"""
import csv, json, os, argparse, unicodedata, re
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

# fallbacks for abbreviations the data can't map on its own (mostly 1940s-50s clubs)
TEAM_FALLBACK = {
    "WSC":"Washington Capitols","DTF":"Detroit Falcons","PRO":"Providence Steamrollers",
    "STB":"St. Louis Bombers","CLR":"Cleveland Rebels","CHS":"Chicago Stags",
    "TOH":"Toronto Huskies","PIT":"Pittsburgh Ironmen","BAL":"Baltimore Bullets",
    "INJ":"Indianapolis Jets","DNN":"Denver Nuggets (1949-50)","INO":"Indianapolis Olympians",
    "AND":"Anderson Packers","SHE":"Sheboygan Red Skins","WAT":"Waterloo Hawks",
    "STL":"St. Louis Hawks","SFW":"San Francisco Warriors","PHW":"Philadelphia Warriors",
    "SYR":"Syracuse Nationals","MNL":"Minneapolis Lakers","ROC":"Rochester Royals",
    "FTW":"Fort Wayne Pistons","CIN":"Cincinnati Royals","SDC":"San Diego Clippers",
    "KCK":"Kansas City Kings","WSB":"Washington Bullets","NJN":"New Jersey Nets",
    "CHH":"Charlotte Hornets","NOH":"New Orleans Hornets","NOK":"New Orleans/Oklahoma City Hornets",
    "VAN":"Vancouver Grizzlies","SEA":"Seattle SuperSonics",
}

def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii","ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+","-",s).strip("-").lower()
    return s or "player"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--awards", default="All-Time_Database_2_0_-_Awards.csv")
    ap.add_argument("--stats",  default="All-Time_Database_2_0_-_RS_Stats__3_.csv")
    ap.add_argument("--out",    default="data/teammates.json")
    args = ap.parse_args()

    awards_by = defaultdict(list)
    rings = defaultdict(int)
    award_team = {}                     # (player, year) -> full team name
    with open(args.awards, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a = (row.get("AWARD") or "").strip()
            p = (row.get("PLAYER / COACH") or "").strip()
            y = (row.get("YEAR") or "").strip()
            t = (row.get("TEAM") or "").strip()
            if not p: continue
            if a == "NBA Champion": rings[p] += 1
            if y.isdigit() and t: award_team[(p, int(y))] = t
            if a in SCORES and y.isdigit(): awards_by[(p, int(y))].append(a)

    rosters = defaultdict(set)
    pseasons = defaultdict(set)
    pyears = defaultdict(set)
    pteam_count = defaultdict(set)      # (player, year) -> set of abbrevs
    with open(args.stats, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            p = (row.get("PLAYER") or "").strip()
            y = (row.get("YEAR") or "").strip()
            t = (row.get("TEAM") or "").strip()
            if p and y.isdigit() and t:
                yr = int(y)
                rosters[(yr, t)].add(p)
                pseasons[p].add((yr, t))
                pyears[p].add(yr)
                pteam_count[(p, yr)].add(t)

    # infer abbreviation -> full name using clean single-team seasons
    abbr2name = defaultdict(Counter)
    for (p, yr), abbrs in pteam_count.items():
        if len(abbrs) == 1:
            ab = next(iter(abbrs))
            fn = award_team.get((p, yr))
            if fn: abbr2name[ab][fn] += 1
    teams = {ab: c.most_common(1)[0][0] for ab, c in abbr2name.items()}
    all_abbr = {t for (_, t) in rosters}
    for ab in all_abbr:
        teams.setdefault(ab, TEAM_FALLBACK.get(ab, ab))

    players = []
    for p, seasons in pseasons.items():
        seasons_detail = []
        total = 0.0; cMvp = cAllNba = cAllStar = 0
        for (yr, t) in sorted(seasons):
            mates = []; spts = 0.0
            for mate in rosters[(yr, t)]:
                if mate == p: continue
                aws = awards_by.get((mate, yr))
                if not aws: continue
                mp = round(sum(SCORES[a] for a in aws), 3); spts += mp
                for a in aws:
                    if a == "Most Valuable Player": cMvp += 1
                    elif a in ALLNBA: cAllNba += 1
                    elif a == "All-Star": cAllStar += 1
                mates.append({"n": mate, "a": sorted(aws, key=lambda x: -SCORES[x]), "p": mp})
            if mates:
                mates.sort(key=lambda m: -m["p"])
                seasons_detail.append({"y": yr, "t": t, "pts": round(spts, 3), "mates": mates})
                total += spts
        nseasons = len(pyears[p])
        players.append({
            "name": p, "score": round(total, 3), "seasons": nseasons,
            "perSeason": round(total / nseasons, 3) if nseasons else 0,
            "rings": rings.get(p, 0), "mvp": cMvp, "allnba": cAllNba, "allstar": cAllStar,
            "detail": seasons_detail,
        })

    players.sort(key=lambda x: -x["score"])
    used = set()
    for i, pl in enumerate(players, 1):
        pl["rank"] = i
        s = slugify(pl["name"]); base = s; k = 2
        while s in used: s = f"{base}-{k}"; k += 1
        used.add(s); pl["slug"] = s

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"scores": SCORES, "teams": teams, "players": players}, f,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {args.out}: {len(players)} players, {len(teams)} teams, {os.path.getsize(args.out)/1024:.0f} KB")

if __name__ == "__main__":
    main()
