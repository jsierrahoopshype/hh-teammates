"""Headshot matching: a player gets a face-fill photo only when his NBA id is certain.
Run:  python -m unittest discover -s tests -v"""
import os, sys, unittest
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import build_teammates as b

# Real ids from data/headshot_ids*.json and nba-headshots' players_all.json.
NBA = [("kobe bryant",977),("jabari smith",2074),("jabari smith jr",1631095),("kevin porter",77876),
       ("kevin porter jr",1629645),("nate williams",78561),("nate williams",1631466),("reggie williams",199),
       ("reggie williams",202130),("chris johnson",202419),("chris johnson",203187),("joel embiid",203954),
       ("gary payton",56),("gary payton ii",1627780),("don smith",78184)]
SINCE = {1631095:"2022",1629645:"2019",1631466:"2021",203954:"2014",1627780:"2016"}
STEMS = {"977-kobe-bryant","1631095-jabari-smith-jr","1629645-kevin-porter-jr","1631466-nate-williams",
         "202130-reggie-williams","202419-chris-johnson","203187-chris-johnson","203954-joel-embiid",
         "56-gary-payton","1627780-gary-payton-ii"}

def index():
    idx = defaultdict(lambda: defaultdict(set))
    for n,i in NBA: idx[b.base_name(n)][i].add(n)
    return idx

def P(name, first, last): return {"name":name, "years":list(range(first,last+1))}

class Match(unittest.TestCase):
    def setUp(self): self.idx = index()
    def m(self, p): return b.match_nba_id(p, self.idx, SINCE)[0]

    def test_unique_name(self): self.assertEqual(self.m(P("Kobe Bryant",1997,2016)), 977)
    def test_jr_without_suffix_in_data(self):      # data says "Jabari Smith", NBA says "Jabari Smith Jr."
        self.assertEqual(self.m(P("Jabari Smith",2023,2026)), 1631095)
        self.assertEqual(self.m(P("Kevin Porter",2020,2026)), 1629645)
    def test_birth_year_names(self):
        self.assertEqual(self.m(P("Kevin Porter (1950)",1973,1983)), 77876)
        self.assertEqual(self.m(P("Reggie Williams (1986)",2010,2017)), 202130)
        self.assertEqual(self.m(P("Reggie Williams (1964)",1988,1997)), 199)
    def test_old_player_never_gets_modern_namesake(self):
        self.assertEqual(self.m(P("Nate Williams",1972,1979)), 78561)
    def test_suffix_in_data(self):
        self.assertEqual(self.m(P("Gary Payton II",2017,2026)), 1627780)
        self.assertEqual(self.m(P("Gary Payton",1991,2007)), 56)
    def test_late_debut(self): self.assertEqual(self.m(P("Joel Embiid",2017,2026)), 203954)
    def test_same_era_namesakes_stay_on_initials(self):
        self.assertIsNone(self.m(P("Chris Johnson",2011,2013)))
    def test_unknown_name(self): self.assertIsNone(self.m(P("Nobody Here",2000,2001)))

    def test_attach(self):
        ps = [P("Kobe Bryant",1997,2016), P("Nate Williams",1972,1979), P("Chris Johnson",2011,2013),
              P("Don Smith (1920)",1947,1948), P("Don Smith (1951)",1974,1975)]
        ps[1]["hs"] = "1631466-nate-williams.png"          # the old name-only match: wrong face, must go
        b.attach_headshots(ps, STEMS, self.idx, SINCE)
        self.assertEqual([p.get("hs") for p in ps], ["977-kobe-bryant.png", None, None, None, None])

class DuplicateIdFiles(unittest.TestCase):
    """nba-headshots has ids with two face-fill files (78049-bill-russell and 78049-jerry-west): the one
    named after the player wins, whatever the order; no file with his name means initials."""
    NBA = [("bill russell",78049),("jerry west",78497),("kevin garnett",708),("patrick ewing",121),
           ("shaquille o neal",406),("paul pierce",1718),("glen rice",431),("dante exum",203957)]
    STEMS = ["78049-jerry-west","78049-bill-russell","78497-oscar-robertson","78497-jerry-west",
             "708-patrick-ewing","708-kevin-garnett","121-patrick-ewing","406-shaquille-oneal",
             "1718-shaquille-oneal","1718-paul-pierce","431-shawn-kemp","431-glen-rice-x",
             "203957-dant-exum","203957-dante-exum"]
    def run_attach(self, stems):
        idx = defaultdict(lambda: defaultdict(set))
        for n,i in self.NBA: idx[b.base_name(n)][i].add(n)
        ps = [P("Bill Russell",1957,1969), P("Jerry West",1961,1974), P("Kevin Garnett",1996,2016),
              P("Patrick Ewing",1986,2002), P("Shaquille O'Neal",1993,2011), P("Paul Pierce",1999,2017),
              P("Glen Rice",1990,2004), P("Dante Exum",2015,2026)]
        b.attach_headshots(ps, set(stems), idx, {})
        return [p.get("hs") for p in ps]
    def test_named_file_wins_in_any_order(self):
        want = ["78049-bill-russell.png","78497-jerry-west.png","708-kevin-garnett.png","121-patrick-ewing.png",
                "406-shaquille-oneal.png","1718-paul-pierce.png",None,"203957-dante-exum.png"]
        self.assertEqual(self.run_attach(self.STEMS), want)
        self.assertEqual(self.run_attach(list(reversed(self.STEMS))), want)
    def test_pick_stem(self):
        self.assertEqual(b.pick_stem(["78049-bill-russell","78049-jerry-west"],"Bill Russell"), "78049-bill-russell")
        self.assertEqual(b.pick_stem(["1718-paul-pierce","1718-shaquille-oneal"],"Shaquille O'Neal"), "1718-shaquille-oneal")
        self.assertEqual(b.pick_stem(["1-a-b-jr","1-c-d"],"A. B. Jr. (1950)"), "1-a-b-jr")
        self.assertIsNone(b.pick_stem(["431-shawn-kemp","431-glen-rice-x"],"Glen Rice"))   # no file with his name
        self.assertEqual(b.pick_stem(["977-kobe-bryant"],"Kobe Bryant"), "977-kobe-bryant")  # one file: kept
        self.assertEqual(b.name_key("Nikola Jokić"), b.name_key("nikola-jokic"))

if __name__ == "__main__":
    unittest.main()
