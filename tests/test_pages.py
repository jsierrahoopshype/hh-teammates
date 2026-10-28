"""Every built page: no Google Fonts, fonts self-hosted, no kicker line, and the contact footer at the end.
Checks the committed files (index.html, teammates-video.html, every p/<slug>.html), so run it after a build.
Run:  python -m unittest discover -s tests -v"""
import glob, html, os, re, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
PAGES = [os.path.join(ROOT, "index.html"), os.path.join(ROOT, "teammates-video.html")] + \
        sorted(glob.glob(os.path.join(ROOT, "p", "*.html")))
LINES = ["Anything wrong? Email us at hoopsmatic@hoopsmatic.com",
         "For business inquiries, contact us at ads@hoopsmatic.com"]

def read(p):
    with open(p, encoding="utf-8") as f: return f.read()

def visible_text(s):
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s)))

class Pages(unittest.TestCase):
    def test_pages_found(self):
        self.assertGreater(len(PAGES), 1000, "player pages missing: run the build first")

    def test_no_google_fonts(self):
        bad = [p for p in PAGES if "fonts.googleapis.com" in read(p) or "fonts.gstatic.com" in read(p)]
        self.assertEqual(bad, [])

    def test_fonts_self_hosted(self):
        for p in PAGES:
            s = read(p)
            for fn in ("dm-sans-latin.woff2", "jetbrains-mono-latin.woff2"):
                # hoopsmatic.com's path first, then the repo-relative one; no other section's fonts
                rel = ("../" if os.sep + "p" + os.sep in p else "") + f"assets/fonts/{fn}"
                self.assertIn(f"src:url(/teammates/assets/fonts/{fn}) format('woff2'),url({rel}) format('woff2')", s, p)
                self.assertNotIn("/lineups/fonts/", s, p)
                self.assertTrue(os.path.exists(os.path.join(ROOT, "assets", "fonts", fn)), fn)
        for lic in ("OFL-DMSans.txt", "OFL-JetBrainsMono.txt"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, "assets", "fonts", lic)), lic)

    def test_contact_footer_on_every_page(self):
        for p in PAGES:
            s = read(p); text = visible_text(s)
            for line in LINES:
                self.assertIn(line, text, p)
            self.assertIn('href="mailto:hoopsmatic@hoopsmatic.com"', s, p)
            self.assertIn('href="mailto:ads@hoopsmatic.com"', s, p)
            # the footer is the last thing on the page
            self.assertTrue(text.rstrip().endswith(LINES[1]) or p.endswith("index.html")
                            or p.endswith("teammates-video.html"), p)

    def test_no_kicker_or_generic_footer(self):
        for p in PAGES:
            s = read(p)
            self.assertNotIn('class="kick"', s, p)
            self.assertNotIn('class="brand">HoopsMatic', s, p)
            self.assertNotIn('class="mark"', s, p)
            self.assertNotIn("HoopsHype", visible_text(s), p)
            self.assertIsNone(re.search(r"HoopsMatic ·", visible_text(s)), p)

if __name__ == "__main__":
    unittest.main()
