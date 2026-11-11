(function () {
  function txt(root, selector) {
    try {
      const el = root.querySelector(selector);
      return el ? el.textContent.trim().replace(/\s+/g, " ") : null;
    } catch (e) {
      return null;
    }
  }

  function spaced(el) {
    if (!el) return null;
    const parts = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const t = walker.currentNode.textContent.trim();
      if (t) parts.push(t);
    }
    return parts.join(" ").replace(/\s+/g, " ").trim() || null;
  }

  function num(str) {
    if (!str) return null;
    const cleaned = String(str).replace(/[\s  ]/g, "");
    const m = cleaned.match(/-?\d+/);
    return m ? parseInt(m[0], 10) : null;
  }

  function stripContext(url) {
    if (!url) return url;
    try {
      const u = new URL(url, location.origin);
      u.searchParams.delete("context");
      const s = u.toString();
      return s.endsWith("?") ? s.slice(0, -1) : s;
    } catch (e) {
      return url.replace(/([?&])context=[^&]*&?/, "$1").replace(/[?&]$/, "");
    }
  }

  function bestFromSrcset(srcset) {
    if (!srcset) return null;
    let best = null;
    let bestSize = -1;
    for (const part of srcset.split(",")) {
      const bits = part.trim().split(/\s+/);
      if (!bits[0]) continue;
      const size = bits[1] ? parseFloat(bits[1]) : 0;
      if (size >= bestSize) {
        bestSize = size;
        best = bits[0];
      }
    }
    return best;
  }

  function imgUrl(img) {
    if (!img) return null;
    return (
      bestFromSrcset(img.getAttribute("srcset")) ||
      bestFromSrcset(img.getAttribute("data-srcset")) ||
      img.getAttribute("src") ||
      img.getAttribute("data-src") ||
      null
    );
  }

  function largestFromSizes(sizes) {
    let best = null;
    let bestArea = -1;
    for (const key of Object.keys(sizes || {})) {
      const m = key.match(/^(\d+)x(\d+)$/);
      const area = m ? parseInt(m[1], 10) * parseInt(m[2], 10) : 0;
      if (area > bestArea) {
        bestArea = area;
        best = sizes[key];
      }
    }
    return best;
  }

  const ITEM_MARKER_SELECTOR = '[data-marker="item-view/title-info"], [data-marker="item-view/item-price"]';
  const SEARCH_MARKER_SELECTOR = '[data-marker="item"]';

  const GONE_PATTERNS = [
    /Ошибка\s*404/i,
    /Страница не найдена/i,
    /Объявление не посмотреть/i,
    /Оно ещё на проверке/i,
    /Объявление снято с публикации/i,
    /Объявление закрыто/i,
    /Товар продан/i,
    /Объявление удалено/i,
    /Срок размещения истёк/i,
    /\b404\b/,
  ];

  const EMPTY_SEARCH_PATTERNS = [/Ничего не нашлось/i, /Ничего не найдено/i, /Объявлений не найдено/i, /нет подходящих объявлений/i];

  const BLOCKED_PHRASES = ["Доступ ограничен", "captcha", "Подтвердите, что вы не робот", "403 Forbidden", "Ошибка 429"];

  const CLOSED_ITEM_PATTERNS = [/Объявление снято/i, /продан[оa]?\b/i];

  function detectGone() {
    if (document.querySelector(ITEM_MARKER_SELECTOR) || document.querySelector(SEARCH_MARKER_SELECTOR)) return { gone: false, reason: null };
    const bodyText = document.body ? document.body.innerText : "";
    const haystack = (document.title || "") + "\n" + bodyText;
    if (/search|kvartiry/.test(location.pathname) && EMPTY_SEARCH_PATTERNS.some((p) => p.test(haystack))) return { gone: false, reason: null };
    for (const pattern of GONE_PATTERNS) {
      if (pattern.test(haystack)) return { gone: true, reason: pattern.source };
    }
    return { gone: false, reason: null };
  }

  function detectEmptySearch() {
    if (document.querySelector(SEARCH_MARKER_SELECTOR) || document.querySelector(ITEM_MARKER_SELECTOR)) return false;
    const bodyText = document.body ? document.body.innerText : "";
    return EMPTY_SEARCH_PATTERNS.some((p) => p.test(bodyText));
  }

  async function waitForPageReady(maxWaitMs) {
    maxWaitMs = maxWaitMs || 8000;
    const start = Date.now();
    function ready() {
      const bodyText = document.body ? document.body.innerText : "";
      return document.readyState === "complete" && bodyText.trim().length > 0;
    }
    while (!ready() && Date.now() - start < maxWaitMs) {
      await new Promise((r) => setTimeout(r, 250));
    }
    return ready();
  }

  function detectBlock() {
    const bodyText = document.body ? document.body.innerText : "";
    for (const phrase of BLOCKED_PHRASES) {
      if (bodyText.includes(phrase)) return { blocked: true, reason: phrase };
    }
    if (!document.querySelector(ITEM_MARKER_SELECTOR) && !document.querySelector(SEARCH_MARKER_SELECTOR)) {
      return { blocked: true, reason: "no known page markers found" };
    }
    return { blocked: false, reason: null };
  }

  function readHydration() {
    for (const script of document.querySelectorAll("script:not([src])")) {
      const text = script.textContent || "";
      if (!text.includes("__staticRouterHydrationData")) continue;
      const m = text.match(/JSON\.parse\(("(?:[^"\\]|\\.)*")\)/);
      if (!m) continue;
      try {
        return JSON.parse(JSON.parse(m[1]));
      } catch (e) {
        return null;
      }
    }
    return null;
  }

  function hydrationBuyerItem(data) {
    const loader = data && data.loaderData;
    if (!loader) return null;
    for (const key of Object.keys(loader)) {
      const v = loader[key];
      if (v && v.buyerItem && v.buyerItem.item) return v.buyerItem;
    }
    return null;
  }

  function extractParams() {
    const params = {};
    const selector = '[data-marker^="item-view/"][data-marker*="params"] li, #bx_item-params li';
    for (const li of document.querySelectorAll(selector)) {
      const labelEl = li.querySelector("span");
      const label = labelEl ? labelEl.textContent.replace(/[:\s ]+$/, "").trim() : null;
      if (!label) continue;
      const full = li.textContent.replace(/\s+/g, " ").trim();
      const value = full.slice(full.indexOf(labelEl.textContent.trim()) + labelEl.textContent.trim().length).replace(/^[:\s ]+/, "").trim();
      if (!(label in params)) params[label] = value;
    }
    return params;
  }

  function extractGalleryPhotos(hItem) {
    const urls = [];
    const fromJson = hItem && Array.isArray(hItem.imageUrls) ? hItem.imageUrls.map((s) => largestFromSizes(s)).filter(Boolean) : [];
    urls.push(...fromJson);
    if (!urls.length) {
      const imgs = document.querySelectorAll('[data-marker="item-view/main-gallery"] img');
      for (const img of imgs) {
        const u = imgUrl(img);
        if (u) urls.push(u);
      }
      for (const el of document.querySelectorAll('[data-marker="item-view/main-gallery"] [data-url]')) {
        urls.push(el.getAttribute("data-url"));
      }
    }
    return Array.from(new Set(urls.filter(Boolean)));
  }

  function extractCoords(hItem) {
    const el = document.querySelector("[data-map-lat][data-map-lon]");
    if (el) {
      const lat = parseFloat(el.getAttribute("data-map-lat"));
      const lon = parseFloat(el.getAttribute("data-map-lon"));
      if (!isNaN(lat) && !isNaN(lon)) return { lat, lon, source: "dom" };
    }
    const c = hItem && hItem.geo && hItem.geo.coords;
    if (c && typeof c.lat === "number" && typeof c.lng === "number") return { lat: c.lat, lon: c.lng, source: "hydration" };
    return null;
  }

  function extractItem() {
    const hydration = readHydration();
    const buyer = hydrationBuyerItem(hydration);
    const hItem = buyer ? buyer.item : null;

    const titleInfo = txt(document, '[data-marker="item-view/title-info"]');
    const h1 = document.querySelector("h1");
    const title = titleInfo || (h1 ? h1.textContent.trim() : null) || (hItem && hItem.title) || null;

    const idBlock = txt(document, '[data-marker="item-view/item-id"]') || "";
    const idMatch = idBlock.match(/№\s*(\d+)/);
    const pathMatch = location.pathname.match(/_(\d+)(?:$|\/)/);
    const item_id = idMatch ? idMatch[1] : pathMatch ? pathMatch[1] : null;

    const price = num(txt(document, '[data-marker="item-view/item-price"]')) || (hItem && hItem.price) || null;
    const breadcrumbs = Array.from(document.querySelectorAll('[data-marker="breadcrumbs"] a')).map((a) => a.textContent.trim());

    const descEl = document.querySelector('[data-marker="item-view/item-description"]');
    const description = (descEl ? descEl.innerText.trim() : null) || (hItem && hItem.description) || null;

    const addressEl = document.querySelector('[data-marker="item-view/item-address"], [itemprop="address"], .style-item-address__string');
    const address = (addressEl ? spaced(addressEl) : null) || (hItem && hItem.geo && hItem.geo.address) || (hItem && hItem.address) || null;

    const photos = extractGalleryPhotos(hItem);
    const coords = extractCoords(hItem);
    const params = extractParams();

    const total_views = num(txt(document, '[data-marker="item-view/total-views"]'));
    const today_views = num(txt(document, '[data-marker="item-view/today-views"]'));
    const date_raw = txt(document, '[data-marker="item-view/item-date"]');
    const seller_name = txt(document, '[data-marker="seller-info/name"]');
    const seller_label = txt(document, '[data-marker="seller-info/label"]');

    const bodyText = document.body ? document.body.innerText : "";
    const sellerBlob = [seller_label, seller_name].filter(Boolean).join(" ");
    let seller_type = "unknown";
    if (/Агентств|Компания|ООО|\bИП\b|Застройщик/i.test(sellerBlob) || (buyer && buyer.isCompany)) seller_type = "agency";
    else if (/Собственник|Частное лицо/i.test(sellerBlob)) seller_type = "owner";
    const no_commission = /Без комиссии/i.test(bodyText) || /без комиссии/i.test(params["Комиссия"] || "");

    const seller_badges =
      Array.from(document.querySelectorAll('[data-marker^="badgeBar/option"]'))
        .map((e) => e.textContent.trim())
        .filter(Boolean)
        .join(" | ") || null;

    const hydration_extra = hItem
      ? {
          houseParams: hItem.houseParams || null,
          rentTermsParams: hItem.rentTermsParams || null,
          rulesParams: hItem.rulesParams || null,
          sortFormatedDate: hItem.sortFormatedDate || null,
          finishTime: hItem.finishTime || null,
          categoryId: hItem.categoryId || null,
        }
      : null;

    const closed = CLOSED_ITEM_PATTERNS.some((p) => p.test(bodyText));

    return {
      item_id,
      url: stripContext(location.href),
      title,
      price,
      breadcrumbs,
      address,
      coords,
      description,
      params,
      photos,
      photo_count: photos.length,
      total_views,
      today_views,
      date_raw,
      seller_name,
      seller_label,
      seller_type,
      no_commission,
      seller_badges,
      hydration_extra,
      closed,
    };
  }

  function cardPhoto(card) {
    const imgs = card.querySelectorAll('[data-marker="item-photo"] img, [data-marker="photo-slider"] img, img');
    for (const img of imgs) {
      const u = imgUrl(img);
      if (u && !u.startsWith("data:")) return u;
    }
    return null;
  }

  function cardAddress(card) {
    const el = card.querySelector('[data-marker="item-address"]');
    if (!el) return null;
    const clone = el.cloneNode(true);
    clone.querySelectorAll('[data-marker^="item-address-georeferences"]').forEach((n) => n.remove());
    return spaced(clone);
  }

  function extractSearch() {
    const cards = Array.from(document.querySelectorAll(SEARCH_MARKER_SELECTOR));
    const qs = new URLSearchParams(location.search);
    const page = parseInt(qs.get("p") || "1", 10);
    const phrases = ["Агентство", "Собственник", "Частное лицо", "Без комиссии", "Застройщик"];

    const hits = cards.map((card, idx) => {
      const linkEl = card.querySelector('[data-marker="item-title"]') || card.querySelector("a[href]");
      const url = linkEl ? stripContext(linkEl.href) : null;
      const title = linkEl ? linkEl.textContent.trim() : null;
      const urlId = url ? (url.match(/_(\d+)(?:$|[/?])/) || [])[1] : null;
      const item_id = card.getAttribute("data-item-id") || urlId || null;
      const metaPrice = card.querySelector('meta[itemprop="price"]');
      const price = num(metaPrice ? metaPrice.getAttribute("content") : null) || num(txt(card, '[data-marker="item-price-value"]')) || num(txt(card, '[data-marker="item-price"]'));
      const price_text = spaced(card.querySelector('[data-marker="item-price"]'));
      const geoEl = card.querySelector('[data-marker^="item-address-georeferences"]');
      const metro_text = spaced(geoEl);
      const address = cardAddress(card);
      const locEl = card.querySelector('[data-marker="item-location"]');
      const location_ = spaced(locEl) || [address, metro_text].filter(Boolean).join(" ");
      const date_text = txt(card, '[data-marker="item-date"]') || txt(card, '[data-marker="item-date-wrapper"]');
      const seller_name = txt(card, '[data-marker="seller-info/name"]') || txt(card, '[data-marker="iva-item/sellerInfo"]');
      const cardText = (card.innerText || "").replace(/\s+/g, " ");
      const badges = phrases.filter((p) => cardText.includes(p));
      card.querySelectorAll('[data-marker^="badge-title-"]').forEach((el) => {
        const t = el.textContent.trim();
        if (t && !badges.includes(t)) badges.push(t);
      });
      return {
        item_id,
        url,
        title,
        price,
        price_text,
        location: location_,
        address,
        metro_text,
        date_text,
        seller_name,
        badges,
        photo: cardPhoto(card),
        text: cardText.slice(0, 1500),
        position: idx + 1,
      };
    });

    const bodyText = document.body ? document.body.innerText : "";
    const countMatch = bodyText.match(/([\d\s  ]{1,12})\s+объявлени/);
    const total_results = countMatch ? parseInt(countMatch[1].replace(/[\s  ]/g, ""), 10) || null : null;

    const pageNums = Array.from(document.querySelectorAll('[data-marker="pagination-button"]'))
      .map((a) => parseInt(a.textContent.trim(), 10))
      .filter((n) => !isNaN(n));
    const total_pages = pageNums.length ? Math.max(...pageNums) : null;

    return { page, url: stripContext(location.href), total_results, total_pages, hits };
  }

  async function humanScroll() {
    const steps = 4 + Math.floor(Math.random() * 5);
    const totalDuration = 1000 + Math.random() * 1500;
    const stepDelay = totalDuration / steps;
    for (let i = 0; i < steps; i++) {
      window.scrollTo({ top: document.body.scrollHeight * ((i + 1) / steps), behavior: "auto" });
      await new Promise((r) => setTimeout(r, stepDelay));
    }
    window.scrollTo({ top: document.body.scrollHeight });
    await new Promise((r) => setTimeout(r, 200));
  }

  function itemIdFromUrl(url) {
    try {
      const u = new URL(url, location.origin);
      const m = u.pathname.match(/_(\d+)(?:$|\/)/);
      return m ? m[1] : null;
    } catch (e) {
      return null;
    }
  }

  function domItemId() {
    const el = document.querySelector('[data-marker="item-view/item-id"]');
    const m = ((el && el.textContent) || "").match(/№\s*(\d+)/);
    if (m) return m[1];
    const pm = location.pathname.match(/_(\d+)(?:$|\/)/);
    return pm ? pm[1] : null;
  }

  function quickReady(kind, expectedItemId) {
    if (kind === "item") {
      const el = document.querySelector('[data-marker="item-view/total-views"]');
      if (!(el && el.textContent && el.textContent.trim().length > 0)) return false;
      if (expectedItemId && domItemId() !== expectedItemId) return false;
      return true;
    }
    if (kind === "search") return document.querySelectorAll(SEARCH_MARKER_SELECTOR).length > 0;
    return false;
  }

  function waitForReadyMarkers(timeoutMs, taskInfo) {
    timeoutMs = timeoutMs || 20000;
    const start = Date.now();
    taskInfo = taskInfo || {};
    const taskType = taskInfo.type || null;
    let taskPath = null;
    let taskPage = "1";
    if (taskInfo.url) {
      try {
        const u = new URL(taskInfo.url, location.origin);
        taskPath = u.pathname;
        taskPage = u.searchParams.get("p") || "1";
      } catch (e) {
        taskPath = null;
      }
    }
    const taskItemId = taskInfo.url ? itemIdFromUrl(taskInfo.url) : null;

    function isNewDocument() {
      if (taskInfo.tNavStart != null && !(performance.timeOrigin > taskInfo.tNavStart)) return false;
      if (taskPath == null) return true;
      const curPath = location.pathname;
      if (taskType === "search") {
        if (curPath !== taskPath) return false;
        return (new URLSearchParams(location.search).get("p") || "1") === taskPage;
      }
      if (curPath === taskPath) return true;
      if (taskItemId) {
        const m = curPath.match(/_(\d+)(?:$|\/)/);
        if (m && m[1] === taskItemId) return true;
      }
      return false;
    }

    function itemReady() {
      const el = document.querySelector('[data-marker="item-view/total-views"]');
      if (!(el && el.textContent && el.textContent.trim().length > 0)) return false;
      if (!document.querySelector('[data-marker="item-view/title-info"]') && !document.querySelector("h1")) return false;
      if (taskItemId && domItemId() !== taskItemId) return false;
      return true;
    }

    function quickGoneOrBlock() {
      const bodyText = document.body ? document.body.innerText : "";
      const haystack = (document.title || "") + "\n" + bodyText;
      if (taskType === "search" && EMPTY_SEARCH_PATTERNS.some((p) => p.test(haystack))) return { kind: "search", reason: "empty" };
      for (const pattern of GONE_PATTERNS) {
        if (pattern.test(haystack)) return { kind: "gone", reason: pattern.source };
      }
      for (const phrase of BLOCKED_PHRASES) {
        if (bodyText.includes(phrase)) return { kind: "block", reason: phrase };
      }
      return null;
    }

    return new Promise((resolve) => {
      function check() {
        if (!isNewDocument()) {
          if (Date.now() - start >= timeoutMs) {
            resolve({ ready: false, kind: "timeout" });
            return;
          }
          setTimeout(check, 300);
          return;
        }
        if (itemReady()) {
          resolve({ ready: true, verified: true, kind: "item" });
          return;
        }
        if (document.querySelectorAll(SEARCH_MARKER_SELECTOR).length > 0) {
          resolve({ ready: true, verified: true, kind: "search" });
          return;
        }
        const goneOrBlock = quickGoneOrBlock();
        if (goneOrBlock) {
          resolve({ ready: true, verified: true, kind: goneOrBlock.kind, reason: goneOrBlock.reason });
          return;
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

  window.AvitoCollectorExtract = {
    detectBlock,
    detectGone,
    detectEmptySearch,
    waitForPageReady,
    waitForReadyMarkers,
    quickReady,
    itemIdFromUrl,
    domItemId,
    extractItem,
    extractSearch,
    humanScroll,
    stripContext,
  };
})();
