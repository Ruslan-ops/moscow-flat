export const meta = {
  name: 'flat-photo-review',
  description: 'Sonnet reviewers rate renovation quality of new Cian flats from photo sheets using the calibrated taste profile',
  phases: [{ title: 'Review' }],
}
const ROOT = 'd:/Users/Ruslan/VsCodeProjects/moscow-flat'
const NEW = `${ROOT}/data/reviews/new`
const prompt = k => `You are a professional Moscow rental realtor reviewing flats for a young couple. Work in ${ROOT}.
1. Read ${ROOT}/docs/taste.md carefully (client's calibrated taste; BASE vs SOFT split is crucial).
2. Calibrate: read ${ROOT}/data/reviews/align_opus.json (8 reference reviews the client agreed with) and view these reference sheets: ${ROOT}/data/photos/335144120.jpg (pred 4), ${ROOT}/data/photos/335470102.jpg (pred 4), ${ROOT}/data/photos/194394424.jpg (pred 2), ${ROOT}/data/photos/335545996.jpg (pred 2).
3. Read ${NEW}/batch_${k}.json (flats with facts + description). For EACH flat view ${ROOT}/data/photos/full/<cianId>.jpg (a contact sheet with ALL listing photos, up to 28) and use the description too.
4. Write ${NEW}/out_${k}.json — a JSON list (UTF-8, Russian text) of objects:
{"cianId": int, "base": 1-5 (step 0.5), "soft": 1-5, "pred": 1-5 (predicted client rating, mostly base), "verdict": "смотреть"|"запасной"|"под вопросом"|"нет", "summary": "1-2 Russian sentences, concrete: floor, walls, kitchen, bathroom, light, style", "fixable": ["what can be removed/replaced cheaply"], "red_flags": ["e.g. окна на проспект, плесень, мало фото интерьера, фото-рендеры, вещи хозяев, старая сантехника, совмещённый санузел, кухня-ниша, следы протечек, старые деревянные окна, газовая колонка, нет стиральной машины"], "kitchen_ok": bool, "bathroom_ok": bool, "light": "светло"|"средне"|"темно", "exterior": "short note on building/entrance/view if visible", "toilet": "тесно"|"норм"|"не видно", "toilet_note": "short note", "storage": "есть"|"мало"|"нет"|"не видно", "storage_note": "short note", "other": ["other concrete issues, short"]}
Verdict rule: смотреть if pred >= 4; запасной if pred 3.5; под вопросом if 3; нет if <= 2.5. Be strict and consistent; the client dislikes Soviet furniture walls, old wallpaper, worn floors, old kitchens; bright saturated walls are a minus.
CLIENT PRIORITIES: (A) toilet clearance — toilet squeezed against the washing machine, bath, sink or wall (touching or under ~20 cm free) is "тесно" and lowers pred by 0.5; (B) storage — no wardrobe/closet/built-in storage at all is "нет" and lowers pred by 0.5. Include these penalties in pred. Use "не видно" honestly when photos do not show it. Never mention a missing balcony: the client does not care.
Also look like an experienced realtor for things a layperson misses: stains on ceilings, old wooden windows, mismatched photos (different flats), photos that look years old, missing bathroom photos, owner's belongings stored in a room. Put them in red_flags.
Write the file incrementally (rewrite the whole list after every 4 flats) so progress is never lost.
Return only: count reviewed, distribution of pred, list of cianIds with pred >= 4.`
const res = await parallel(args.batches.map(k => () => agent(prompt(k), { label: `review:batch_${k}`, phase: 'Review', model: 'sonnet' })))
return res
