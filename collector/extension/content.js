(async function () {
  try {
    const api = window.AvitoCollectorExtract;
    if (!api) {
      chrome.runtime.sendMessage({
        type: "avitocollector-result",
        ok: false,
        kind: null,
        data: null,
        html: document.documentElement ? document.documentElement.outerHTML : null,
        error: "AvitoCollectorExtract missing (extract.js failed to load)",
      });
      return;
    }

    await api.humanScroll();

    const probeVerified = window.__avitoCollectorProbeVerified === true;
    const probeKind = window.__avitoCollectorProbeKind || null;
    const taskItemId = window.__avitoCollectorTaskItemId || null;
    const probeStillHolds =
      probeVerified && api.quickReady && api.quickReady(probeKind, taskItemId);
    if (!probeStillHolds) {
      await api.waitForPageReady(8000);
    }

    const goneInfo = api.detectGone();
    if (goneInfo.gone) {
      chrome.runtime.sendMessage({
        type: "avitocollector-result",
        ok: false,
        kind: "gone",
        data: null,
        html: document.documentElement ? document.documentElement.outerHTML : null,
        reason: goneInfo.reason,
        url: location.href,
      });
      return;
    }

    if (api.detectEmptySearch()) {
      chrome.runtime.sendMessage({ type: "avitocollector-result", ok: true, kind: "search", data: api.extractSearch(), html: null, url: location.href });
      return;
    }

    const blockInfo = api.detectBlock();
    if (blockInfo.blocked) {
      chrome.runtime.sendMessage({
        type: "avitocollector-block",
        reason: blockInfo.reason,
        url: location.href,
      });
      return;
    }

    const isItem = !!document.querySelector(
      '[data-marker="item-view/title-info"], [data-marker="item-view/item-price"]'
    );
    const isSearch = !isItem && !!document.querySelector('[data-marker="item"]');

    let kind = null;
    let data = null;
    if (isItem) {
      kind = "item";
      data = api.extractItem();
    } else if (isSearch) {
      kind = "search";
      data = api.extractSearch();
    }

    const html = document.documentElement.outerHTML;
    chrome.runtime.sendMessage({
      type: "avitocollector-result",
      ok: !!kind,
      kind,
      data,
      html,
      url: location.href,
    });
  } catch (e) {
    chrome.runtime.sendMessage({
      type: "avitocollector-result",
      ok: false,
      kind: null,
      data: null,
      html: document.documentElement ? document.documentElement.outerHTML : null,
      error: String(e && e.message ? e.message : e),
    });
  }
})();
