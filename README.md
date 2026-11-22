# ATP Top 100 Stats

Open `index.html` in a browser (all four site files must be in the same folder).

## How the data stays up to date

- `update_rankings.py` downloads the current ATP top 100 (rank, name, country) from
  Tennis Abstract and rewrites `players.js`. It needs only Python 3, no installs.
- `player-details.json` holds each player's height, hand and backhand. These don't change,
  so they are kept by hand.
- `.github/workflows/update-rankings.yml` runs the script every Tuesday and commits
  `players.js` if the rankings changed. You can also run it from the repo's **Actions** tab
  ("Run workflow").

## One-time setup (GitHub Pages)

1. Create a GitHub repository and upload everything in this folder (including `.github`).
2. Settings > Pages > "Deploy from a branch" > `main` / root.
3. Settings > Actions > General > Workflow permissions > "Read and write permissions".

## When a new player enters the top 100

They show up in the country tab straight away, but are left out of the other stats and a
notice on the page names them. To include them, add an entry to `player-details.json`:

    "New Player": { "height": 185, "hand": "R", "backhand": "2H" }

If the source spells a name differently, add `"aliases": ["Source Spelling"]` to the entry.
The workflow log lists who is missing after each run.

## Run it yourself

    python3 update_rankings.py
