# Flat hunt Moscow — shared brief for agents

## Client profile
- Couple. He works remotely (no constraints). She: wedding decorator, florist, renders building facades (archviz). No job yet in Moscow.
- She hates long walks/commutes in Moscow, values calm, quiet, not crowded; likes exhibitions; likes Soviet-film Moscow architecture (stalinki, old центр, ВДНХ, etc.).
- Needs green park walkable after work.

## Hard requirements (listing level)
- Long-term rent, budget 60k RUB/mo (stretch tier up to ~70k), area >= 29 m2, NOT apartments (апартаменты).
- Floor > 4 => lift required. Prefer floor 2..7, avoid 1st and very high floors.
- Prefer brick / stalinka / brick-monolith; avoid panel with bad sound insulation (П-44, КОПЭ, П-3 etc.).

## Project layout (repo root: d:/Users/Ruslan/VsCodeProjects/moscow-flat)
- python: `.venv/Scripts/python -I script.py` (py3.12; requests, numpy, shapely, scipy, bs4 installed; pip install more if needed)
- `src/` scripts, `data/<layer>/` outputs (JSON, UTF-8, ensure_ascii=False).
- Shared grid (for heatmaps): lat 55.55..55.92 step 0.0025, lon 37.35..37.86 step 0.004 (~280x250 m). Cell center = min + (i+0.5)*step.
- Unset env vars CURL_CA_BUNDLE SSL_CERT_FILE REQUESTS_CA_BUNDLE before network calls (they point to a missing cert file).
- Do NOT use any anti-bot evasion (no TLS impersonation, no captcha solving, no proxy rotation). Only public APIs with honest headers, polite rate.

## Code style (mandatory)
- No comments/docstrings. Imports at top, never in try/if. Paths via f-strings with forward slashes (no os.path.join/pathlib).
- Inline single-use variables. Keep calls on one line. No README files.
- print only for technical/debug output.
