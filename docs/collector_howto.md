1. Chrome: open chrome://extensions, enable Developer mode, Load unpacked, pick `collector/extension` (log in to avito.ru in this Chrome first).
2. Seed search pages (from repo root, server can be stopped or running): `.venv/Scripts/python collector/server.py seed-pages --pages 60`
3. Optional: `seed-searches urls.txt` (search URLs, one per line) or `seed-items items.txt` (item URLs, one per line); add `--force` to re-queue done URLs.
4. Start server: `.venv/Scripts/python collector/server.py serve` (port/paths are constants at top of the file).
5. Click the extension icon, press Start. It opens a background tab and visits one page every ~12-180 s; leave Chrome running. A block pauses the queue 3 min; 3 blocks in 30 min pauses until the server is restarted.
6. Export: `.venv/Scripts/python src/avito_export.py` writes `data/avito/cards.json` and `data/avito/items.json`.
7. First 3 search and item pages are saved to `data/avito/samples/` for selector debugging.
