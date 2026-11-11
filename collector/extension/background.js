
const SERVER = "http://127.0.0.1:8765";
const HEARTBEAT_ALARM = "avitocollector-heartbeat";
const NAV_ALARM = "avitocollector-navigate";
const HEARTBEAT_MINUTES = 0.33;
const KEEPALIVE_MS = 15_000;
const SHORT_WAIT_MAX_MS = 25_000;
const STORAGE_KEY = "avitocollector_state";
const NAV_TIMEOUT_MS = 90_000;
const EXTRACT_TIMEOUT_MS = 60_000;

const DEFAULT_STATE = {
  running: false,
  workerTabId: null,
  phase: "idle",
  waitFor: null,
  nextActionAt: null,
  phaseDeadline: null,
  phaseStartedAt: null,
  currentTask: null,
  lastDelayMs: null,
  lastStatus: null,
  lastError: null,
};

async function getState() {
  const obj = await chrome.storage.local.get(STORAGE_KEY);
  return { ...DEFAULT_STATE, ...(obj[STORAGE_KEY] || {}) };
}

async function setState(patch) {
  const state = await getState();
  const next = { ...state, ...patch };
  await chrome.storage.local.set({ [STORAGE_KEY]: next });
  return next;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function withTimeout(promise, ms, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("timeout: " + label + " after " + ms + "ms")), ms);
  });
  return Promise.race([Promise.resolve(promise), timeout]).finally(() => clearTimeout(timer));
}

async function serverFetch(path, options) {
  return withTimeout(
    fetch(SERVER + path, options).then((r) => r.json()),
    10_000,
    "fetch " + path
  );
}


async function startCollector() {
  let state = await getState();
  if (state.running && state.workerTabId) {
    return state;
  }
  const tab = await withTimeout(
    chrome.tabs.create({ url: "about:blank", active: false }),
    10_000,
    "tabs.create"
  );
  state = await setState({
    running: true,
    workerTabId: tab.id,
    phase: "idle",
    nextActionAt: null,
    currentTask: null,
    lastError: null,
  });
  await chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: HEARTBEAT_MINUTES });
  await runWaitAction("fetch");
  return state;
}

async function stopCollector() {
  const state = await getState();
  waitToken++;
  await chrome.alarms.clear(HEARTBEAT_ALARM);
  try {
    await chrome.alarms.clear(NAV_ALARM);
  } catch (e) {
  }
  if (state.workerTabId) {
    try {
      await withTimeout(chrome.tabs.remove(state.workerTabId), 5_000, "tabs.remove");
    } catch (e) {
    }
  }
  await setState({
    running: false,
    workerTabId: null,
    phase: "idle",
    nextActionAt: null,
    waitFor: null,
    currentTask: null,
  });
}

let navInFlight = false;
let pendingAction = null;
let waitToken = 0;
let navAttemptId = 0;

async function refreshServerStatus() {
  try {
    const status = await serverFetch("/status");
    await setState({ lastStatus: status });
  } catch (e) {
  }
}

async function armWait(delayMs, waitFor) {
  const now = Date.now();
  const myToken = ++waitToken;
  await setState({ phase: "waiting", waitFor, nextActionAt: now + delayMs, phaseStartedAt: now });
  try {
    await chrome.alarms.clear(NAV_ALARM);
  } catch (e) {
  }
  if (delayMs <= SHORT_WAIT_MAX_MS) {
    scheduleShortWait(delayMs, waitFor, myToken);
  } else {
    await chrome.alarms.create(NAV_ALARM, { when: now + delayMs });
  }
}

function scheduleShortWait(delayMs, waitFor, myToken) {
  const deadline = Date.now() + Math.max(0, delayMs);
  function pump() {
    if (myToken !== waitToken) return;
    const remaining = deadline - Date.now();
    if (remaining <= 0) {
      runWaitAction(waitFor);
      return;
    }
    setTimeout(async () => {
      if (myToken !== waitToken) return;
      try {
        await chrome.storage.local.get("__avitocollector_keepalive_ping");
      } catch (e) {
      }
      pump();
    }, Math.min(remaining, KEEPALIVE_MS));
  }
  pump();
}

async function runWaitAction(waitFor) {
  if (navInFlight) {
    pendingAction = waitFor;
    return;
  }
  navInFlight = true;
  try {
    if (waitFor === "navigate") {
      await beginNavigate();
    } else {
      await fetchNextAndSchedule();
    }
  } catch (e) {
    await setState({ lastError: String(e && e.message ? e.message : e) });
  } finally {
    navInFlight = false;
  }
  if (pendingAction) {
    const action = pendingAction;
    pendingAction = null;
    const state = await getState();
    const due = state.nextActionAt == null || Date.now() >= state.nextActionAt;
    if (state.running && action === "fetch" && !state.currentTask) {
      runWaitAction("fetch");
      return;
    }
    if (state.running && action === "navigate" && state.currentTask &&
        state.phase === "waiting" && state.waitFor === "navigate" && due) {
      runWaitAction("navigate");
      return;
    }
  }
  refreshServerStatus();
}

async function watchdogTick(source) {
  const state = await getState();
  if (!state.running) return;
  const now = Date.now();

  if (state.phase === "navigating" || state.phase === "extracting") {
    if (state.phaseDeadline != null && now > state.phaseDeadline) {
      navAttemptId++;
      navInFlight = true;
      try {
        await reportFailureAndAdvance("timeout in phase " + state.phase);
        await fetchNextAndSchedule();
      } finally {
        navInFlight = false;
      }
    }
    refreshServerStatus();
    return;
  }

  if (navInFlight) return;

  if (state.phase === "waiting") {
    if (state.nextActionAt != null && now >= state.nextActionAt) {
      await runWaitAction(state.waitFor || "fetch");
    }
  } else if (state.phase === "idle" && source === "heartbeat") {
    await runWaitAction("fetch");
  }

  refreshServerStatus();
}

async function fetchNextAndSchedule() {
  let resp;
  try {
    resp = await serverFetch("/next");
  } catch (e) {
    await setState({ lastError: "server unreachable" });
    await armWait(15_000, "fetch");
    return;
  }
  if (resp.idle) {
    await setState({ currentTask: null });
    await armWait(10_000, "fetch");
  } else if (resp.paused) {
    await setState({ currentTask: null, lastError: "paused: " + resp.reason });
    await armWait(30_000, "fetch");
  } else if (resp.task) {
    await setState({ currentTask: resp.task, lastDelayMs: resp.delay_ms, lastError: null });
    await armWait(resp.delay_ms, "navigate");
  }
}

const PROBE_TIMEOUT_MS = 20_000;

async function beginNavigate() {
  const state = await getState();
  const task = state.currentTask;
  if (!task) {
    await fetchNextAndSchedule();
    return;
  }
  const myAttempt = ++navAttemptId;
  const stale = () => myAttempt !== navAttemptId;

  const tNavStart = Date.now();
  await setState({
    phase: "navigating",
    phaseDeadline: tNavStart + NAV_TIMEOUT_MS,
    tNavStart,
    tReady: null,
    navAttemptId: myAttempt,
  });

  let probeResult = null;
  try {
    await withTimeout(
      chrome.tabs.update(state.workerTabId, { url: task.url }),
      10_000,
      "tabs.update"
    );
    if (stale()) return;

    await waitForRealNavigation(state.workerTabId, task, tNavStart, NAV_TIMEOUT_MS);
    if (stale()) return;

    const remainingMs = () => Math.max(1000, tNavStart + NAV_TIMEOUT_MS - Date.now());

    const isCian = task.type === "cian_search";
    try {
      await withTimeout(
        chrome.scripting.executeScript({
          target: { tabId: state.workerTabId },
          files: isCian ? ["extract.js", "cian.js"] : ["extract.js"],
        }),
        10_000,
        "inject extract.js (probe)"
      );
      if (stale()) return;
      const probeTimeout = Math.min(PROBE_TIMEOUT_MS, remainingMs());
      const results = await withTimeout(
        chrome.scripting.executeScript({
          target: { tabId: state.workerTabId },
          func: (timeoutMs, taskInfo, cianMode) => {
            if (cianMode) {
              const cianApi = window.CianCollectorExtract;
              return cianApi ? cianApi.waitForReady(timeoutMs, taskInfo) : { ready: false, kind: "no-api" };
            }
            const api = window.AvitoCollectorExtract;
            if (!api || !api.waitForReadyMarkers) {
              return { ready: false, kind: "no-api" };
            }
            return api.waitForReadyMarkers(timeoutMs, taskInfo).then((res) => {
              const verified = !!(
                res &&
                res.ready &&
                res.verified &&
                (res.kind === "item" || res.kind === "search")
              );
              window.__avitoCollectorProbeVerified = verified;
              window.__avitoCollectorProbeKind = res ? res.kind : null;
              window.__avitoCollectorTaskItemId = api.itemIdFromUrl
                ? api.itemIdFromUrl(taskInfo.url)
                : null;
              return res;
            });
          },
          args: [probeTimeout, { type: task.type, url: task.url, tNavStart }, isCian],
        }),
        probeTimeout + 5_000,
        "readiness probe"
      );
      if (stale()) return;
      probeResult = results && results[0] && results[0].result;
    } catch (e) {
      probeResult = null;
    }
    if (stale()) return;

    if (!probeResult || !probeResult.ready) {
      await withTimeout(
        waitForTabComplete(state.workerTabId, remainingMs()),
        remainingMs() + 5_000,
        "wait for tab complete"
      );
    }
  } catch (e) {
    if (stale()) return;
    await reportFailureAndAdvance("navigation failed: " + e);
    await fetchNextAndSchedule();
    return;
  }
  if (stale()) return;

  const tReady = Date.now();
  await setState({ tReady });

  await sleep(500 + Math.random() * 1000);
  if (stale()) return;

  await setState({ phase: "extracting", phaseDeadline: Date.now() + EXTRACT_TIMEOUT_MS });
  try {
    await withTimeout(
      chrome.scripting.executeScript({
        target: { tabId: state.workerTabId },
        files: task.type === "cian_search" ? ["extract.js", "cian.js", "cian_content.js"] : ["extract.js", "content.js"],
      }),
      EXTRACT_TIMEOUT_MS,
      "inject extract.js+content.js"
    );
  } catch (e) {
    if (stale()) return;
    await reportFailureAndAdvance("injection failed: " + e);
    await fetchNextAndSchedule();
  }
}

function waitForRealNavigation(tabId, task, tNavStart, timeoutMs) {
  return new Promise((resolve) => {
    let settled = false;

    let taskPath = null;
    let taskPage = "1";
    try {
      const u = new URL(task.url);
      taskPath = u.pathname;
      taskPage = u.searchParams.get("p") || "1";
    } catch (e) {
      taskPath = null;
    }
    let taskItemId = null;
    if (taskPath) {
      const m = taskPath.match(/_(\d+)(?:$|\/)/);
      taskItemId = m ? m[1] : null;
    }

    function matchesTask(rawUrl) {
      if (!rawUrl) return false;
      if (taskPath == null) return true;
      let u;
      try {
        u = new URL(rawUrl);
      } catch (e) {
        return false;
      }
      if (task.type === "cian_search" && u.pathname.includes("captcha")) return true;
      if (task.type === "search" || task.type === "cian_search") {
        if (u.pathname !== taskPath) return false;
        if ((u.searchParams.get("p") || "1") !== taskPage) return false;
        return true;
      }
      if (u.pathname === taskPath) return true;
      if (taskItemId) {
        const m = u.pathname.match(/_(\d+)(?:$|\/)/);
        if (m && m[1] === taskItemId) return true;
      }
      return false;
    }

    const timer = setTimeout(finish, timeoutMs);

    function finish() {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        chrome.webNavigation.onCommitted.removeListener(onCommitted);
      } catch (e) {
      }
      chrome.tabs.onUpdated.removeListener(onUpdated);
      resolve();
    }

    function onCommitted(details) {
      if (details.tabId !== tabId || details.frameId !== 0) return;
      if (details.timeStamp != null && details.timeStamp < tNavStart) return;
      if (!matchesTask(details.url)) return;
      finish();
    }

    function onUpdated(updatedTabId, changeInfo, tab) {
      if (updatedTabId !== tabId) return;
      if (changeInfo.status !== "loading") return;
      const url = changeInfo.url || (tab && tab.url);
      if (!matchesTask(url)) return;
      finish();
    }

    try {
      chrome.webNavigation.onCommitted.addListener(onCommitted);
    } catch (e) {
    }
    chrome.tabs.onUpdated.addListener(onUpdated);
  });
}

function waitForTabComplete(tabId, timeoutMs) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("timeout waiting for tab load"));
    }, timeoutMs);

    function listener(updatedTabId, changeInfo) {
      if (updatedTabId === tabId && changeInfo.status === "complete") {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function reportFailureAndAdvance(reason) {
  const state = await getState();
  const task = state.currentTask;
  if (task) {
    try {
      await serverFetch("/result", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: task.id, ok: false, kind: null, data: null, html: null, reason }),
      });
    } catch (e) {
    }
  }
  await setState({ phase: "idle", currentTask: null, lastError: reason });
}


chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender).then(sendResponse);
  return true;
});

async function handleMessage(message, sender) {
  if (!message) return {};

  if (message.cmd === "start") {
    const state = await startCollector();
    return { ok: true, state };
  }
  if (message.cmd === "stop") {
    await stopCollector();
    return { ok: true };
  }
  if (message.cmd === "get-state") {
    return { ok: true, state: await getState() };
  }

  if (message.type === "avitocollector-result" || message.type === "avitocollector-block") {
    const state = await getState();
    if (!state.workerTabId || !sender.tab || sender.tab.id !== state.workerTabId) {
      return {};
    }
    const task = state.currentTask;
    if (!task) return {};

    const tExtracted = Date.now();
    const tNavStart = state.tNavStart || null;
    const tReady = state.tReady || null;
    const timings = {
      ready_ms: tNavStart != null && tReady != null ? tReady - tNavStart : null,
      extract_ms: tReady != null ? tExtracted - tReady : null,
      total_ms: tNavStart != null ? tExtracted - tNavStart : null,
    };

    if (message.type === "avitocollector-block") {
      try {
        await serverFetch("/block", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task_id: task.id, reason: message.reason, timings }),
        });
      } catch (e) {
      }
      await setState({ currentTask: null, lastError: "blocked: " + message.reason });
    } else {
      try {
        await serverFetch("/result", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            task_id: task.id,
            ok: message.ok,
            kind: message.kind,
            data: message.data,
            html: message.html,
            reason: message.reason || null,
            timings,
          }),
        });
      } catch (e) {
      }
      await setState({ currentTask: null, lastError: message.error || null });
    }
    runWaitAction("fetch");
    return {};
  }

  return {};
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === NAV_ALARM) {
    watchdogTick("nav-alarm");
  } else if (alarm.name === HEARTBEAT_ALARM) {
    watchdogTick("heartbeat");
  }
});

chrome.runtime.onStartup.addListener(async () => {
  const state = await getState();
  if (state.running) {
    await chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: HEARTBEAT_MINUTES });
  }
});
