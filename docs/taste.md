# Interior taste profile (calibrated by the client, 2026-11-12)

Rating scale = predicted client rating 1..5 of the flat itself (ignore price/location).

## Client ratings on calibration sheets (data/calib/<n>_<cianId>.jpg)
- 1 → 2: empty, old-fashioned feel (flowered old wallpaper, old kitchen furniture, bare walls).
- 2 → 4: modern-ish laminate, light walls, new sofa, simple new furniture, decent bathroom tiles. Not luxury, but fresh and lived-in-able.
- 3 → 2: ultra-Soviet furniture.
- 4 → 2: scary old floor/carpet-linoleum, Soviet wood wardrobes, dated wooden kitchen, crystal chandelier.
- 5 → 3: too little shown, not enough information.
- 6 → 3: photos were mostly exterior, interior not shown (unknown = 3 at best).
- 7 → 4: fresh modern renovation: light grey walls, spot lights, laminate, white modern furniture, new bed.
- 8 → 1: no finishing at all (bare concrete / unfinished).
- 9 → 3: average.
- 10 → 2: "совок" — 80s polished wardrobe-wall ("стенка"), striped wallpaper, old armchairs, chandelier, tapestry-like fabrics.

## Two layers: fixed vs. replaceable (client rule)
- BASE (cannot change, dominates the rating ~80%): floor, walls/ceiling, kitchen units + appliances, bathroom (tiles, bath/shower, plumbing), interior doors, windows, radiators/pipes, overall light.
- SOFT (cheap/easy to remove or replace, ~20%): a single old wardrobe/armchair/chairs, carpet/rug, curtains, chandelier, bedspread, decor. If the base is good, dated soft items lower the rating by at most ~0.5 — note them as "можно убрать/заменить".
- A full "стенка" wall unit or a whole room of heavy Soviet furniture is borderline: note as "попросить вывезти", lower by ~1.
- Output both: base_score (1-5), soft_score (1-5), predicted rating = mostly base, and a list `fixable` of what to remove/replace.

## Alignment round 2 (client agreed with 7/8 of data/reviews/align_opus.json)
- Tidy Soviet flat (walls not faded, bathroom ok, Soviet furniture) → 2-2.5, still "нет".
- Lived-in granny flat 1927 with carpets/crystal → client says 2 (not 1): 1 is reserved for unfinished/dirty/damaged.
- Bright saturated wall colours (blue/orange) are usually a minus; acceptable only when the rest is fresh (then still 4 max, note "перекрасить").

## Rules distilled
- 5: stylish modern renovation, cohesive design, good light, modern kitchen + bathroom.
- 4: clean fresh modern-ish renovation (light walls, laminate/clean parquet, new simple furniture, modern kitchen fronts, tiled bathroom in good shape). IKEA-level is fine.
- 3: neutral/average, OR not enough interior photos to judge (kitchen/bathroom not shown, mostly exterior/floor plan).
- 2: dated "бабушатник"/"совок": Soviet stenka wardrobes, old polished furniture, crystal chandeliers, old wallpaper patterns, worn parquet/old linoleum, old wooden kitchen, carpets on walls/floors.
- 1: no renovation/unfinished, dirty, damaged, mold, "horror film" vibes.
- NOTE: calibration showed only the first 3 photos per flat, so ratings for 5 and 6 reflect our sampling, not the listing. In real review you see up to 12 photos spread across the whole gallery; judge "not enough info" only if the listing itself truly lacks interior photos (kitchen, bathroom, room).
- Penalize: listing has fewer than 4 interior photos in total; only renders; cluttered with owner's stuff; dark small kitchen; old bathtub/rusty pipes; windows straight onto a highway.
- Client priorities (2026-11-12): toilet squeezed against washing machine/bath/sink/wall is a strong minus (−0.5); no wardrobes/closets at all is a strong minus (−0.5). A missing balcony does not matter (laundry dries on a rack). No spot for a work desk is a minus (−0.5; he works from home). No toilet photo caps the rating at 3.5. A narrow separate WC is only a note. Decent owner furniture that stays is a plus; stored belongings/junk is a bargaining point (ask to remove). Storage for her florist/decor materials is a plus.
- Neutral: Soviet ARCHITECTURE of the building (she likes it) — only the interior must be modern.
