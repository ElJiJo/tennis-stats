# ATP Top 100 Stats

Open `index.html` in a browser (all the site files must be in the same folder).

## How the data stays up to date

- `update_rankings.py` downloads the current ATP top 100 (rank, name, country) from
  Tennis Abstract and rewrites `players.js`. It needs only Python 3, no installs.
- `player-details.json` holds each player's height, hand and backhand. These don't change,
  so they are kept by hand.
- `.github/workflows/update-rankings.yml` runs the script every Tuesday and commits
  `players.js` if the rankings changed. You can also run it from the repo's **Actions** tab
  ("Run workflow").

## Grand Slam winners tab (automatic)

The same weekly run also refreshes `grand-slams.js`. It reads Wikipedia's year-by-year table of
Grand Slam champions, counts each player's titles per tournament, and keeps only players who
are still ranked and have no "retired" date on their Wikipedia page. A new champion or a
retirement is picked up on the next run, so there is nothing to edit by hand.

Safety: if the table can't be read, a count disagrees with Wikipedia's own "(n/total)" figure,
or a player's titles would go down, the script leaves `grand-slams.js` as it was and prints
`GRAND SLAMS NOT UPDATED` plus the reason in the Action's log. Wikipedia can take a few days to
record a new title, so the tab may lag a Slam by up to a week.

## One-time setup (GitHub Pages)

1. Create a GitHub repository and upload everything in this folder (including `.github`).
2. Settings > Pages > "Deploy from a branch" > `main` / root.
3. Settings > Actions > General > Workflow permissions > "Read and write permissions".

## When a new player enters the top 100

Nothing to do. The script looks the player up on Wikipedia (height, hand, backhand) and saves
them in `player-details.json`, marked `"auto"`, so the stats include them straight away.

If nothing usable is found (new players sometimes have no height listed), they appear in the
country tab, are left out of the other stats, and the lookup is retried every week. The
workflow log names them (the website itself shows nothing). You can fill one in by hand:

    "New Player": { "height": 185, "hand": "R", "backhand": "2H" }

Automatic entries come from Wikipedia and could occasionally be wrong; the Action's log lists
each one so you can double-check if you like.

## Run it yourself

    python3 update_rankings.py
