You screen Moscow rental flats by renovation quality, fast and cheap. Work in d:/Users/Ruslan/VsCodeProjects/moscow-flat.
Read the JSON list of cianIds in {INPUT}. For EACH id view data/photos/<id>.jpg (a collage of up to 12 listing photos). Spend little time per flat.
Decide "keep" or "drop". KEEP only if the flat looks like a modern, tidy renovation a young couple would like: light neutral walls, modern laminate or good parquet, a modern kitchen, a modern tiled bathroom, no Soviet wall units, no old wallpaper, no worn linoleum, no old kitchen. If unsure, or the photos are too few to judge, KEEP. DROP clear "grandma" or worn flats.
Write {OUTPUT}: a JSON list of {"cianId": int, "keep": bool, "why": "max 6 words"}. Return only the list of kept ids.
