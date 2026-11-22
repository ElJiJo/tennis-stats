#!/usr/bin/env python3
"""
Refreshes players.js with the current ATP top 100.

  rank / name / country  -> scraped from Tennis Abstract (updated weekly)
  height / hand / backhand -> read from player-details.json (these never change)

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
import html
import json
import re
import sys
import time
import unicodedata
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


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "tennis-stats-site/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ---------- Automatic lookup of new players (Wikipedia) ----------

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_HEADERS = {"User-Agent": "tennis-stats-site/1.0 (personal hobby project; GitHub Actions)"}


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

    lines, missing, auto_added = [], [], []
    for p in ranking:
        match = lookup.get(normalize(p["name"]))
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
