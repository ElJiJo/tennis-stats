#!/usr/bin/env python3
"""
Refreshes players.js with the current ATP top 100.

  rank / name / country  -> scraped from Tennis Abstract (updated weekly)
  height / hand / backhand -> read from player-details.json (these never change)

It also refreshes grand-slams.js (active Grand Slam winners and their titles) from
Wikipedia's year-by-year table of Grand Slam champions; see update_grand_slams() below.
And masters.js (this year's Masters 1000 champions) from Wikipedia's page for the season;
see update_masters() below.

If a player in the new top 100 is not in player-details.json, the script looks
them up on Wikipedia and saves the result there (entries marked "auto"). If
nothing is found, they still appear in the rankings but are left out of the
stats, and the lookup is retried on the next run.

Usage:
  python3 update_rankings.py                 # download and update
  python3 update_rankings.py --html page.html  # use a saved page (for testing)

Only uses the Python standard library.
"""
import argparse
import datetime
import html
import json
import re
import sys
import time
import unicodedata
from html.parser import HTMLParser
import urllib.parse
import urllib.request
from pathlib import Path

URL = "https://www.tennisabstract.com/reports/atpRankings.html"
HERE = Path(__file__).parent


def normalize(name):
    """'Félix Auger-Aliassime' -> 'felixaugeraliassime' (for matching names)."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", name.lower())


def spelling_variant(name, details, used):
    """Same last name + same first letter as exactly one known player not yet matched
    (e.g. 'Alexander Shevchenko' vs 'Aleksandr Shevchenko')."""
    parts = normalize(name.split()[-1]), normalize(name)[:1]
    candidates = [n for n in details
                  if n not in used and normalize(n.split()[-1]) == parts[0] and normalize(n)[:1] == parts[1]]
    return candidates[0] if len(candidates) == 1 else None


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "tennis-stats-site/1.0 (https://github.com/ElJiJo/tennis-stats; personal hobby project)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ---------- Automatic lookup of new players (Wikipedia) ----------

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_HEADERS = {"User-Agent": "tennis-stats-site/1.0 (https://github.com/ElJiJo/tennis-stats; personal hobby project)"}


def wiki_get_json(params):
    """Calls the Wikipedia API and returns parsed JSON."""
    url = WIKI_API + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def infobox_field(wikitext, field):
    """Returns the raw text of one infobox field, e.g. '| plays = Right-handed ...'."""
    m = re.search(r"^\s*\|\s*" + field + r"\s*=\s*(.*?)\s*(?=^\s*\|\s*\w+\s*=|\n\}\}|\Z)",
                  wikitext, re.S | re.M | re.I)
    return m.group(1) if m else ""


def parse_infobox(wikitext):
    """Extracts (height_cm, hand, backhand) from a tennis infobox, or None if incomplete."""
    if "infobox tennis biography" not in wikitext.lower():
        return None

    # Reject obviously wrong people (e.g. a retired player with the same name).
    born = re.search(r"(\d{4})", infobox_field(wikitext, "birth_date"))
    if born and int(born.group(1)) < 1982:
        return None

    plays = infobox_field(wikitext, "plays").lower()
    hand = "L" if "left" in plays else "R" if "right" in plays else None
    backhand = "1H" if "one-hand" in plays or "one hand" in plays else \
               "2H" if "two-hand" in plays or "two hand" in plays else None

    h = infobox_field(wikitext, "height")
    height = None
    if (m := re.search(r"(\d)\.(\d{2})\s*\|?\s*m\b", h)) or (m := re.search(r"m\s*=\s*(\d)\.(\d{2})", h)):
        height = int(m.group(1)) * 100 + int(m.group(2))             # 1.88 m
    elif m := re.search(r"(\d{3})\s*\|?\s*cm", h):
        height = int(m.group(1))                                      # 188 cm
    elif m := re.search(r"ft\s*=\s*(\d)\D+in\s*=\s*(\d+)", h) or \
              re.search(r"(\d)\s*(?:ft|'|\|ft)\D{0,4}(\d{1,2})\s*(?:in|\"|\|in)", h):
        height = round((int(m.group(1)) * 12 + int(m.group(2))) * 2.54)  # 6 ft 2 in

    if not (height and 160 <= height <= 215 and hand and backhand):
        return None
    return height, hand, backhand


def lookup_new_player(name):
    """Tries to find a player's details on Wikipedia. Returns a dict or None. Never raises."""
    try:
        found = wiki_get_json({"action": "query", "list": "search", "srlimit": 4,
                               "srsearch": f"{name} tennis player"})
        last = normalize(name.split()[-1])
        for hit in found["query"]["search"]:
            title = hit["title"]
            if last not in normalize(title):          # the page must be about this name
                continue
            page = wiki_get_json({"action": "query", "prop": "revisions", "rvprop": "content",
                                  "rvslots": "main", "titles": title})
            wikitext = page["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
            parsed = parse_infobox(wikitext)
            if parsed:
                height, hand, backhand = parsed
                return {"height": height, "hand": hand, "backhand": backhand,
                        "auto": f"wikipedia: {title}"}
            time.sleep(1)
    except Exception as e:                            # network error, odd page format, ...
        print(f"  (lookup failed for {name}: {e})")
    return None


def parse_rankings(page):
    """Returns (list of {rank, name, country}, last_update_string)."""
    text = re.sub(r"<[^>]+>", " ", page)          # drop tags
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)

    # A row looks like:  1 Alexander Zverev GER 1997-04-20
    row = re.compile(r"(?<!\d)(\d{1,3}) ([^\d]+?) ([A-Z]{3}) \d{4}-\d{2}-\d{2}")
    rows = {}
    for m in row.finditer(text):
        rank = int(m.group(1))
        if 1 <= rank <= 100 and rank not in rows:
            rows[rank] = {"rank": rank, "name": m.group(2).strip(), "country": m.group(3)}

    updated = re.search(r"Last update:\s*(\d{4}-\d{2}-\d{2})", text)
    return [rows[r] for r in sorted(rows)], (updated.group(1) if updated else "unknown")


# ---------- Grand Slam winners (Wikipedia year-by-year table) ----------

SLAM_PAGE = "List of Grand Slam men's singles champions"
SLAM_KEYS = ["ao", "rg", "wim", "uso"]       # Australian Open, Roland Garros, Wimbledon, US Open


class _TableParser(HTMLParser):
    """Collects every <table> of a page as a list of rows, each a list of cell texts."""

    def __init__(self):
        super().__init__()
        self.tables, self._row, self._cell, self._skip = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
            self.tables[-1].append(self._row)
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag in ("sup", "style", "script"):       # footnote marks like [1] are ignored
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            text = "".join(self._cell).replace("\xa0", " ")
            self._row.append(re.sub(r"\s+", " ", text).strip())
            self._cell = None
        elif tag in ("sup", "style", "script") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._cell is not None and not self._skip:
            self._cell.append(data)


def parse_all_ranked(page):
    """Every ranked player (not only the top 100): {normalized name: (name, country)}."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    text = re.sub(r"\s+", " ", text)
    row = re.compile(r"(?<!\d)\d{1,4} ([^\d]+?) ([A-Z]{3}) \d{4}-\d{2}-\d{2}")
    return {normalize(m.group(1)): (m.group(1).strip(), m.group(2)) for m in row.finditer(text)}


def parse_slam_table(page_html):
    """Reads the year-by-year champions table. Returns {name: {ao, rg, wim, uso, claimed}} for
    titles won since 2000, where 'claimed' is the career total Wikipedia prints as (n/total).
    Returns None if the table cannot be found."""
    parser = _TableParser()
    parser.feed(page_html)

    best = []
    for table in parser.tables:
        rows = [r for r in table if len(r) >= 5 and re.fullmatch(r"\d{4}", r[0])]
        if len(rows) > len(best):
            best = rows
    if len(best) < 10:
        return None

    wins = {}
    for r in best:
        if int(r[0]) < 2000:
            continue
        for key, cell in zip(SLAM_KEYS, r[1:5]):
            m = re.match(r"(.+?)\s*\((\d+)/(\d+)\)", cell)
            name = (m.group(1) if m else cell).strip(" *†‡")
            if not name:                                  # tournament not played yet this year
                continue
            w = wins.setdefault(name, {"ao": 0, "rg": 0, "wim": 0, "uso": 0, "claimed": 0})
            w[key] += 1
            if m:
                w["claimed"] = max(w["claimed"], int(m.group(3)))
    return wins or None


def is_retired(name):
    """True if the player's Wikipedia infobox has a 'retired' date. Any error -> False."""
    try:
        data = wiki_get_json({"action": "query", "prop": "revisions", "rvprop": "content",
                              "rvslots": "main", "titles": name, "redirects": 1})
        wikitext = data["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
        value = re.sub(r"<!--.*?-->", "", infobox_field(wikitext, "retired"), flags=re.S)
        return bool(value.strip())
    except Exception as e:
        print(f"  (could not check retirement for {name}: {e})")
        return False


def active_slam_winners(wins, ranked, retired_check=is_retired):
    """Keeps players who are still ranked and not retired. Returns (list, problems)."""
    winners, problems = [], []
    for wiki_name, w in wins.items():
        match = ranked.get(normalize(wiki_name))
        if not match:                                     # not on the ranking list: retired long ago
            continue
        name, country = match
        total = w["ao"] + w["rg"] + w["wim"] + w["uso"]
        if w["claimed"] and w["claimed"] != total:        # self-check against Wikipedia's own count
            problems.append(f"{name}: counted {total} titles but Wikipedia says {w['claimed']}")
        if retired_check(wiki_name):
            print(f"  (excluded {name}: retired)")
            continue
        winners.append({"name": name, "country": country,
                        "ao": w["ao"], "rg": w["rg"], "wim": w["wim"], "uso": w["uso"]})
    winners.sort(key=lambda p: (-(p["ao"] + p["rg"] + p["wim"] + p["uso"]), p["name"]))
    return winners, problems


def read_old_slam_totals():
    path = HERE / "grand-slams.js"
    if not path.exists():
        return {}
    return {m.group(1): sum(int(x) for x in m.groups()[1:]) for m in re.finditer(
        r'name: "([^"]+)".*?ao: (\d+),\s*rg: (\d+),\s*wim: (\d+),\s*uso: (\d+)',
        path.read_text(encoding="utf-8"))}


def update_grand_slams(ranking_page):
    """Rewrites grand-slams.js. Never raises: on any doubt it keeps the existing file."""
    try:
        data = wiki_get_json({"action": "parse", "page": SLAM_PAGE, "prop": "text", "redirects": 1})
        wins = parse_slam_table(data["parse"]["text"])
        if not wins:
            print("\nGRAND SLAMS NOT UPDATED: could not find the champions table on Wikipedia.")
            return
        winners, problems = active_slam_winners(wins, parse_all_ranked(ranking_page))

        old = read_old_slam_totals()
        for p in winners:                                 # titles can only go up
            total = p["ao"] + p["rg"] + p["wim"] + p["uso"]
            if p["name"] in old and total < old[p["name"]]:
                problems.append(f'{p["name"]}: {total} titles is fewer than the {old[p["name"]]} already saved')
        if not winners:
            problems.append("no active winners found")
        if problems:
            print("\nGRAND SLAMS NOT UPDATED (data looked wrong, grand-slams.js kept as it was):")
            for pr in problems:
                print("  " + pr)
            return

        lines = ["  { name: %s, country: %s, ao: %d, rg: %d, wim: %d, uso: %d },"
                 % (json.dumps(p["name"]), json.dumps(p["country"]), p["ao"], p["rg"], p["wim"], p["uso"])
                 for p in winners]
        (HERE / "grand-slams.js").write_text(
            "// AUTO-GENERATED by update_rankings.py - do not edit by hand.\n"
            "// Active men's singles Grand Slam winners, from Wikipedia's table of Slam champions.\n"
            "// ao = Australian Open, rg = Roland Garros, wim = Wimbledon, uso = US Open.\n\n"
            "const GRAND_SLAM_WINNERS = [\n" + "\n".join(lines) + "\n];\n", encoding="utf-8")
        print("\ngrand-slams.js updated: " + ", ".join(
            f'{p["name"]} ({p["ao"] + p["rg"] + p["wim"] + p["uso"]})' for p in winners))
        for gone in sorted(set(old) - {p["name"] for p in winners}):
            print(f"  (no longer listed: {gone})")
    except Exception as e:
        print(f"\nGRAND SLAMS NOT UPDATED ({type(e).__name__}: {e}); grand-slams.js kept as it was.")


# ---------- Masters 1000 champions of the current year (Wikipedia season page) ----------

# (id, label shown on the site, lowercase words that identify the row on Wikipedia), in calendar order.
MASTERS_EVENTS = [
    ("indian-wells", "Indian Wells", ["indian wells"]),
    ("miami",        "Miami",        ["miami"]),
    ("monte-carlo",  "Monte-Carlo",  ["monte"]),
    ("madrid",       "Madrid",       ["madrid"]),
    ("rome",         "Rome",         ["italian", "rome"]),
    ("canada",       "Canada",       ["canadian", "toronto", "montreal"]),
    ("cincinnati",   "Cincinnati",   ["cincinnati"]),
    ("shanghai",     "Shanghai",     ["shanghai"]),
    ("paris",        "Paris",        ["paris"]),
]


def parse_masters_table(page_html):
    """Reads the 'Singles champions' table of a season page.
    Returns ({event id: (champion, runner-up)}, problems), or (None, problems) if no table is found.
    Events without a champion yet are simply missing from the result."""
    parser = _TableParser()
    parser.feed(page_html)

    rows = []
    for table in parser.tables:
        if any(len(r) >= 3 and "singles champion" in r[1].lower() for r in table):
            rows = [r for r in table if len(r) >= 3]
            break
    if not rows:
        return None, ["could not find the 'Singles champions' table"]

    found, problems = {}, []
    for r in rows:
        label = r[0].lower()
        event = next((e for e in MASTERS_EVENTS if any(k in label for k in e[2])), None)
        champion = r[1].strip(" *†‡")
        runner_up = r[2].strip(" *†‡")
        if not event or champion.lower() in ("", "tbd", "tba", "-", "—", "–") or "singles champion" in champion.lower():
            continue
        if re.search(r"\d", champion) or len(champion) > 40:
            problems.append(f"{event[1]}: strange champion text {champion!r}")
            continue
        if event[0] in found:
            if found[event[0]][0] != champion:        # the same tournament listed twice, disagreeing
                problems.append(f"{event[1]}: listed with two champions ({found[event[0]][0]} / {champion})")
            continue
        found[event[0]] = (champion, runner_up)
    return found, problems


def read_old_masters():
    """(year, number of champions) of the saved masters.js, or (None, 0)."""
    path = HERE / "masters.js"
    if not path.exists():
        return None, 0
    text = path.read_text(encoding="utf-8")
    year = re.search(r"MASTERS_YEAR = (\d{4})", text)
    return (int(year.group(1)) if year else None), len(re.findall(r'champion: "', text))


def update_masters(ranking_page):
    """Rewrites masters.js. Never raises: on any doubt it keeps the existing file."""
    try:
        year = datetime.date.today().year
        data = wiki_get_json({"action": "parse", "page": f"{year} ATP Masters 1000 tournaments",
                              "prop": "text", "redirects": 1})
        found, problems = parse_masters_table(data["parse"]["text"])
        if found is None or problems:
            print("\nMASTERS NOT UPDATED (masters.js kept as it was):")
            for pr in problems:
                print("  " + pr)
            return

        old_year, old_count = read_old_masters()
        if old_year == year and len(found) < old_count:   # champions can't disappear within a season
            print(f"\nMASTERS NOT UPDATED: found {len(found)} champions, fewer than the {old_count} already saved.")
            return

        ranked = parse_all_ranked(ranking_page)           # for spelling and country of each champion
        lines = []
        for event_id, label, _ in MASTERS_EVENTS:
            if event_id not in found:
                lines.append("  { id: %s, tournament: %s, champion: null, country: null, runnerUp: null },"
                             % (json.dumps(event_id), json.dumps(label)))
                continue
            champion, runner_up = found[event_id]
            name, country = ranked.get(normalize(champion), (champion, None))
            lines.append("  { id: %s, tournament: %s, champion: %s, country: %s, runnerUp: %s },"
                         % (json.dumps(event_id), json.dumps(label), json.dumps(name),
                            json.dumps(country), json.dumps(runner_up or None)))
        (HERE / "masters.js").write_text(
            "// AUTO-GENERATED by update_rankings.py - do not edit by hand.\n"
            "// Singles champions of this year's nine ATP Masters 1000 tournaments, in calendar order,\n"
            "// from Wikipedia. champion: null means the tournament has not been played yet.\n\n"
            f"const MASTERS_YEAR = {year};\n\n"
            "const MASTERS_1000 = [\n" + "\n".join(lines) + "\n];\n", encoding="utf-8")
        print(f"\nmasters.js updated ({year}): {len(found)} of {len(MASTERS_EVENTS)} champions known.")
    except Exception as e:
        print(f"\nMASTERS NOT UPDATED ({type(e).__name__}: {e}); masters.js kept as it was.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="read this saved HTML file instead of downloading")
    ap.add_argument("--no-lookup", action="store_true",
                    help="don't look up new players online (testing)")
    args = ap.parse_args()

    page = Path(args.html).read_text(encoding="utf-8") if args.html else download(URL)
    ranking, updated = parse_rankings(page)

    # Safety check: never overwrite good data with a broken scrape.
    if [p["rank"] for p in ranking] != list(range(1, 101)):
        sys.exit(f"ERROR: expected ranks 1-100, got {len(ranking)} rows. "
                 "The source page may have changed. players.js was NOT modified.")

    details = json.loads((HERE / "player-details.json").read_text(encoding="utf-8"))
    lookup = {}
    for name, d in details.items():
        lookup[normalize(name)] = (name, d)
        for alias in d.get("aliases", []):
            lookup[normalize(alias)] = (name, d)

    # Players matched by exact name first, so the spelling fallback only uses leftovers.
    used = {lookup[normalize(p["name"])][0] for p in ranking if normalize(p["name"]) in lookup}

    lines, missing, auto_added = [], [], []
    for p in ranking:
        match = lookup.get(normalize(p["name"]))
        if not match:
            variant = spelling_variant(p["name"], details, used)
            if variant:
                match = (variant, details[variant])
                used.add(variant)
        if not match and not args.no_lookup:
            # New to the top 100: try to find their details automatically.
            found = lookup_new_player(p["name"])
            if found:
                details[p["name"]] = found
                match = lookup[normalize(p["name"])] = (p["name"], found)
                auto_added.append(f'{p["rank"]}. {p["name"]} -> {found["auto"]}, '
                                  f'{found["height"]} cm, {found["hand"]}, {found["backhand"]}')
            time.sleep(1)
        if match:
            name, d = match
            height, hand, backhand = d["height"], d["hand"], d["backhand"]
        else:
            name, height, hand, backhand = p["name"], None, None, None
            missing.append(f'{p["rank"]}. {p["name"]} ({p["country"]})')
        lines.append(
            "  { rank: %d, name: %s, country: %s, height: %s, hand: %s, backhand: %s },"
            % (p["rank"], json.dumps(name), json.dumps(p["country"]),
               json.dumps(height), json.dumps(hand), json.dumps(backhand))
        )

    out = (
        "// AUTO-GENERATED by update_rankings.py - do not edit by hand.\n"
        "// To change a player's height / hand / backhand, edit player-details.json\n"
        "// and run the script again.\n"
        "// A null height means the player is new and not yet in player-details.json.\n\n"
        f'const LAST_UPDATED = "{updated}"; // date of the source rankings\n\n'
        "const PLAYERS = [\n" + "\n".join(lines) + "\n];\n"
    )
    (HERE / "players.js").write_text(out, encoding="utf-8")

    if auto_added:
        # Remember them, so we don't look them up again next week.
        (HERE / "player-details.json").write_text(
            json.dumps(details, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"players.js updated (rankings dated {updated}).")
    if not args.no_lookup:
        update_grand_slams(page)
        update_masters(page)
    if auto_added:
        print("\nNew players added automatically (entries marked \"auto\" in player-details.json):")
        for m in auto_added:
            print("  " + m)
    if missing:
        print("\nNo details found yet (will retry on the next run; or add them to player-details.json):")
        for m in missing:
            print("  " + m)


if __name__ == "__main__":
    main()
