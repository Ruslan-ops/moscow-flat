(async function () {
  try {
    const cian = window.CianCollectorExtract;
    const avito = window.AvitoCollectorExtract;
    if (!cian || !avito) {
      chrome.runtime.sendMessage({ type: "avitocollector-result", ok: false, kind: null, data: null, html: null, error: "cian.js or extract.js failed to load" });
      return;
    }
    await avito.humanScroll();
    const ready = await cian.waitForReady(10000, {});
    if (!ready.ready || ready.kind === "block") {
      const block = cian.detectBlock();
      if (block.blocked) {
        chrome.runtime.sendMessage({ type: "avitocollector-block", reason: block.reason, url: location.href });
        return;
      }
    }
    const data = cian.extractSearch();
    chrome.runtime.sendMessage({
      type: "avitocollector-result",
      ok: !!data,
      kind: data ? "cian_search" : null,
      data,
      html: document.documentElement.outerHTML,
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
