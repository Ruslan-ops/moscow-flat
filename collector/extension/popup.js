const SERVER = "http://127.0.0.1:8765";

const el = (id) => document.getElementById(id);

function fmtSeconds(ms) {
  if (ms === null || ms === undefined) return "-";
  return Math.round(ms / 1000) + " с";
}

function fmtEventDetail(evt) {
  if (!evt) return "";
  let detail = evt.detail;
  if (typeof detail === "string") {
    try {
      detail = JSON.parse(detail);
    } catch (e) {
    }
  }
  const detailStr = detail && typeof detail === "object" ? JSON.stringify(detail) : String(detail || "");
  return `${evt.ts} · ${evt.type}${detailStr ? " · " + detailStr : ""}`;
}

async function refresh() {
  if (location.search.includes("auto=1")) {
    await chrome.runtime.sendMessage({ cmd: "stop" });
    await chrome.runtime.sendMessage({ cmd: "start" });
    window.close();
    return;
  }
  let stateResp = await chrome.runtime.sendMessage({ cmd: "get-state" });
  let state = (stateResp && stateResp.state) || {};
  if (state.running && String(state.lastError || "").includes("No tab with id")) {
    await chrome.runtime.sendMessage({ cmd: "stop" });
    stateResp = await chrome.runtime.sendMessage({ cmd: "start" });
    state = (stateResp && stateResp.state) || {};
  }

  const badge = el("stateBadge");
  if (state.running) {
    badge.textContent = "работает";
    badge.className = "badge running";
  } else {
    badge.textContent = "остановлен";
    badge.className = "badge stopped";
  }

  let status = null;
  try {
    status = await fetch(SERVER + "/status").then((r) => r.json());
  } catch (e) {
    el("error").textContent = "Сервер не отвечает на 127.0.0.1:8765. Запустите: .venv/Scripts/python collector/server.py serve";
  }

  if (status) {
    el("error").textContent = state.lastError ? String(state.lastError) : "";

    const counts = status.counts || {};
    el("done").textContent = counts.done ?? 0;
    el("queued").textContent = counts.queued ?? 0;
    el("gone").textContent = counts.gone ?? 0;
    el("failed").textContent = counts.failed ?? 0;

    el("intervalTargetActual").textContent =
      fmtSeconds(status.target_interval_ms) + " / " + fmtSeconds(status.actual_interval_median_ms);
    el("readyMs").textContent = fmtSeconds(status.ready_ms_last) + " / " + fmtSeconds(status.ready_ms_median);
    el("itemsPerHour").textContent = (status.items_per_hour ?? 0) + " карт./ч";
    el("eta").textContent = status.eta_minutes != null ? Math.round(status.eta_minutes) + " мин" : "-";
    el("blocks").textContent = `${status.blocks_total ?? 0} / ${status.blocks_recent ?? 0}`;

    el("lastEvent").textContent = status.last_event ? "Событие: " + fmtEventDetail(status.last_event) : "";

    if (status.paused) {
      badge.textContent = "пауза";
      badge.className = "badge paused";
      el("error").textContent = "Пауза: " + (status.pause_reason || "");
    }

    if (!state.lastError && status.last_error) {
      el("error").textContent = "Последняя ошибка: " + fmtEventDetail(status.last_error);
    }
  }
}

el("startBtn").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ cmd: "start" });
  refresh();
});

el("stopBtn").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ cmd: "stop" });
  refresh();
});

refresh();
setInterval(refresh, 2000);
