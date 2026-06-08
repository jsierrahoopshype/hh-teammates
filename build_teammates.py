#!/usr/bin/env python3
"""
Teammates Score build script.
Reads the two All-Time Database CSVs and writes data/teammates.json,
the single file the front-end loads.

Run:  python build_teammates.py
Inputs expected in the same folder (override with --awards / --stats):
    All-Time_Database_2_0_-_Awards.csv
    All-Time_Database_2_0_-_RS_Stats__3_.csv
Output:
    data/teammates.json
"""
import csv, json, os, argparse
from collections import defaultdict

# --- Scoring table (edit here OR in the front-end; front-end recomputes the total) ---
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--awards", default="All-Time_Database_2_0_-_Awards.csv")
    ap.add_argument("--stats",  default="All-Time_Database_2_0_-_RS_Stats__3_.csv")
    ap.add_argument("--out",    default="data/teammates.json")
    args = ap.parse_args()

    # awards_by[(player, year)] = [award, ...]  (scored awards only)
    awards_by = defaultdict(list)
    with open(args.awards, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a = (row.get("AWARD") or "").strip()
            p = (row.get("PLAYER / COACH") or "").strip()
            y = (row.get("YEAR") or "").strip()
            if a in SCORES and p and y.isdigit():
                awards_by[(p, int(y))].append(a)

    # rosters[(year, team)] = set(players); player_seasons[player] = set((year, team))
    rosters = defaultdict(set)
    pseasons = defaultdict(set)
    pyears = defaultdict(set)
    with open(args.stats, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            p = (row.get("PLAYER") or "").strip()
            y = (row.get("YEAR") or "").strip()
            t = (row.get("TEAM") or "").strip()
            if p and y.isdigit() and t:        # skip blank teams
                yr = int(y)
                rosters[(yr, t)].add(p)
                pseasons[p].add((yr, t))
                pyears[p].add(yr)

    players = []
    for p, seasons in pseasons.items():
        seasons_detail = []
        total = 0.0
        for (yr, t) in sorted(seasons):
            mates = []
            spts = 0.0
            for mate in rosters[(yr, t)]:
                if mate == p:
                    continue
                aws = awards_by.get((mate, yr))
                if not aws:
                    continue
                mp = round(sum(SCORES[a] for a in aws), 3)
                spts += mp
                mates.append({"n": mate, "a": sorted(aws, key=lambda x: -SCORES[x]), "p": mp})
            if mates:
                mates.sort(key=lambda m: -m["p"])
                seasons_detail.append({"y": yr, "t": t, "pts": round(spts, 3), "mates": mates})
                total += spts
        nseasons = len(pyears[p])
        players.append({
            "name": p,
            "score": round(total, 3),
            "seasons": nseasons,
            "perSeason": round(total / nseasons, 3) if nseasons else 0,
            "detail": seasons_detail,
        })

    # ranks by career score
    players.sort(key=lambda x: -x["score"])
    for i, pl in enumerate(players, 1):
        pl["rank"] = i

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"scores": SCORES, "players": players}, f,
                  ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(args.out)
    print(f"Wrote {args.out}: {len(players)} players, {size/1024:.0f} KB")
    print("Top 5:", ", ".join(f'{pl["name"]} {pl["score"]:.1f}' for pl in players[:5]))

if __name__ == "__main__":
    main()
