(function () {
  const SERP_MARKER = /_cianConfig\[['"]frontend-serp['"]\]/;
  const BLOCK_PHRASES = ["captcha", "Подтвердите, что вы не робот", "Доступ ограничен", "Ошибка 429"];
  const RAW_LIMIT = 100000;
  const OFFERS_PER_PAGE = 28;
  const TOTAL_KEYS = ["aggregatedOffers", "aggregatedCount", "offerCount", "offersCount", "totalOffers", "count"];
  const OFFER_KEYS = [
    "category", "flatType", "isApartments", "isPenthouse", "isNewBuilding", "isByHomeowner", "isFromBuilder",
    "totalArea", "livingArea", "kitchenArea", "roomsCount", "floorNumber", "windowsViewType", "repairType",
    "separateWcsCount", "combinedWcsCount", "loggiasCount", "balconiesCount", "hasFurniture", "hasKitchenFurniture",
    "hasWashingMachine", "hasFridge", "hasTv", "hasConditioner", "hasDishwasher", "hasInternet", "hasBathtub",
    "hasShower", "petsAllowed", "childrenAllowed", "added", "creationDate", "editDate", "publicationDate", "status",
  ];
  const BARGAIN_KEYS = ["price", "currency", "paymentPeriod", "deposit", "agentFee", "clientFee", "includesUtilities", "utilitiesTerms", "leaseTermType", "prepayMonths", "priceType"];
  const BUILDING_KEYS = ["floorsCount", "materialType", "buildYear", "passengerLiftsCount", "cargoLiftsCount", "seriesName", "series", "parking", "deadline", "name", "heatingType", "ceilingHeight"];
  const USER_KEYS = ["isAgent", "isHomeowner", "userType", "agencyName", "companyName", "isSelfEmployed", "accountType"];

  function pick(obj, keys) {
    const out = {};
    if (!obj || typeof obj !== "object") return out;
    for (const k of keys) {
      if (obj[k] !== undefined && obj[k] !== null) out[k] = obj[k];
    }
    return out;
  }

  function matchingBracketEnd(text, start) {
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let i = start; i < text.length; i++) {
      const c = text[i];
      if (inString) {
        if (escaped) escaped = false;
        else if (c === "\\") escaped = true;
        else if (c === '"') inString = false;
        continue;
      }
      if (c === '"') inString = true;
      else if (c === "[" || c === "{") depth++;
      else if (c === "]" || c === "}") {
        depth--;
        if (depth === 0) return i;
      }
    }
    return -1;
  }

  function concatArrays(text) {
    const arrays = [];
    const marker = text.search(SERP_MARKER);
    if (marker < 0) return arrays;
    const re = /\.concat\(\s*(?=\[)/g;
    re.lastIndex = marker;
    let m;
    while ((m = re.exec(text))) {
      const start = m.index + m[0].length;
      const end = matchingBracketEnd(text, start);
      if (end < 0) continue;
      try {
        arrays.push(JSON.parse(text.slice(start, end + 1)));
      } catch (e) {
      }
    }
    return arrays;
  }

  function findInitialState(scriptTexts) {
    for (const text of scriptTexts) {
      if (!text.includes("initialState")) continue;
      for (const arr of concatArrays(text)) {
        const entry = Array.isArray(arr) ? arr.find((e) => e && e.key === "initialState") : null;
        if (entry && entry.value) return entry.value;
      }
    }
    return null;
  }

  function isOfferArray(arr) {
    return Array.isArray(arr) && arr.length > 0 && arr.every((o) => o && typeof o === "object" && (o.cianId || o.id) && o.bargainTerms);
  }

  function findOfferArray(node, depth) {
    if (!node || typeof node !== "object" || depth > 8) return null;
    if (isOfferArray(node)) return node;
    for (const k of Object.keys(node)) {
      const found = findOfferArray(node[k], depth + 1);
      if (found) return found;
    }
    return null;
  }

  function findOffers(state) {
    const direct = state && state.results && state.results.offers;
    if (Array.isArray(direct)) return direct;
    return findOfferArray(state, 0) || [];
  }

  function findTotal(state) {
    const results = (state && state.results) || {};
    for (const k of TOTAL_KEYS) {
      if (typeof results[k] === "number") return results[k];
    }
    for (const k of TOTAL_KEYS) {
      if (state && typeof state[k] === "number") return state[k];
    }
    return null;
  }

  function addressText(geo) {
    const parts = geo && Array.isArray(geo.address) ? geo.address : [];
    return parts.map((p) => (p && (p.fullName || p.name || p.shortName)) || "").filter(Boolean).join(", ");
  }

  function compactGeo(geo) {
    if (!geo) return null;
    const parts = Array.isArray(geo.address) ? geo.address : [];
    return {
      coordinates: geo.coordinates || null,
      address: addressText(geo),
      districts: parts.filter((p) => p && /raion|okrug|district/i.test(p.type || "")).map((p) => ({ type: p.type, name: p.fullName || p.name })),
      userInput: geo.userInput || null,
      undergrounds: (geo.undergrounds || []).map((u) => ({
        name: u.name,
        time: u.travelTime !== undefined ? u.travelTime : u.time,
        transportType: u.travelType || u.transportType || null,
        lineColor: u.lineColor || null,
      })),
    };
  }

  function compactOffer(o) {
    const user = o.user || {};
    return {
      cianId: o.cianId || o.id,
      fullUrl: o.fullUrl || null,
      ...pick(o, OFFER_KEYS),
      bargainTerms: pick(o.bargainTerms, BARGAIN_KEYS),
      building: pick(o.building, BUILDING_KEYS),
      geo: compactGeo(o.geo),
      description: o.description || null,
      photos: (o.photos || []).map((p) => (p && (p.fullUrl || p.url)) || null).filter(Boolean),
      user: pick(user, USER_KEYS),
    };
  }

  function scriptTexts() {
    return Array.from(document.querySelectorAll("script:not([src])"), (s) => s.textContent || "");
  }

  function parseSerp() {
    const state = findInitialState(scriptTexts());
    if (!state) return null;
    const offers = findOffers(state);
    return { state, offers, total: findTotal(state) };
  }

  function extractSearch() {
    const parsed = parseSerp();
    if (!parsed) return null;
    const page = parseInt(new URLSearchParams(location.search).get("p") || "1", 10) || 1;
    const offers = parsed.offers.map((o) => {
      const rawText = JSON.stringify(o);
      return { cian_id: String(o.cianId || o.id), compact: compactOffer(o), raw: rawText.length < RAW_LIMIT ? rawText : null };
    });
    const total_pages = parsed.total ? Math.ceil(parsed.total / OFFERS_PER_PAGE) : null;
    return { page, url: location.href, total_results: parsed.total, total_pages, offers };
  }

  function detectBlock() {
    const bodyText = document.body ? document.body.innerText : "";
    const haystack = `${document.title || ""}\n${bodyText}\n${location.pathname}`;
    for (const phrase of BLOCK_PHRASES) {
      if (haystack.toLowerCase().includes(phrase.toLowerCase())) return { blocked: true, reason: phrase };
    }
    if (document.querySelector('form[action*="/captcha"], iframe[src*="captcha"]')) return { blocked: true, reason: "captcha form" };
    return { blocked: false, reason: null };
  }

  function waitForReady(timeoutMs, taskInfo) {
    timeoutMs = timeoutMs || 20000;
    taskInfo = taskInfo || {};
    const start = Date.now();
    let taskPath = null;
    let taskPage = "1";
    if (taskInfo.url) {
      const u = new URL(taskInfo.url, location.origin);
      taskPath = u.pathname;
      taskPage = u.searchParams.get("p") || "1";
    }

    function isNewDocument() {
      if (taskInfo.tNavStart != null && !(performance.timeOrigin > taskInfo.tNavStart)) return false;
      if (taskPath == null) return true;
      if (location.pathname.includes("captcha")) return true;
      return location.pathname === taskPath && (new URLSearchParams(location.search).get("p") || "1") === taskPage;
    }

    return new Promise((resolve) => {
      function check() {
        if (isNewDocument()) {
          if (parseSerp()) {
            resolve({ ready: true, verified: true, kind: "cian_search" });
            return;
          }
          const block = detectBlock();
          if (block.blocked) {
            resolve({ ready: true, verified: true, kind: "block", reason: block.reason });
            return;
          }
        }
        if (Date.now() - start >= timeoutMs) {
          resolve({ ready: false, kind: "timeout" });
          return;
        }
        setTimeout(check, 300);
      }
      check();
    });
  }

  window.CianCollectorExtract = { parseSerp, extractSearch, detectBlock, waitForReady, concatArrays, findInitialState };
})();
