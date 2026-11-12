(async function () {
  try {
    const cian = window.CianCollectorExtract;
    const ready = await cian.waitForReady(10000, { type: "cian_item" });
    const block = cian.detectBlock();
    if (block.blocked && !(ready.ready && ready.kind === "cian_item")) {
      chrome.runtime.sendMessage({ type: "avitocollector-block", reason: block.reason, url: location.href });
      return;
    }
    const data = cian.extractItem();
    chrome.runtime.sendMessage({ type: "avitocollector-result", ok: data.status !== "unknown", kind: "cian_item", data, html: document.documentElement.outerHTML, url: location.href });
  } catch (e) {
    chrome.runtime.sendMessage({ type: "avitocollector-result", ok: false, kind: null, data: null, html: document.documentElement ? document.documentElement.outerHTML : null, error: String(e && e.message ? e.message : e) });
  }
})();
