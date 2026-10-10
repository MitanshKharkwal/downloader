const NATIVE_HOST = "com.downloadmanager.native_host";
const NON_HANDOFF_SCHEMES = ["blob:", "data:"];

function sendToNativeHost(message) {
  return new Promise((resolve) => {
    chrome.runtime.sendNativeMessage(NATIVE_HOST, message, (response) => {
      if (chrome.runtime.lastError) {
        console.warn("[DM] Native host error:", chrome.runtime.lastError.message);
        resolve({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        resolve(response || { ok: false, error: "empty response from native host" });
      }
    });
  });
}

async function interceptEnabled() {
  const { interceptDownloads = true } = await chrome.storage.local.get("interceptDownloads");
  return interceptDownloads;
}

async function getHeadersForUrl(url, referrer) {
  const headers = { 'User-Agent': navigator.userAgent };
  if (referrer && /^https?:\/\//i.test(referrer)) {
    headers.Referer = referrer;
  }
  try {
    const cookies = await chrome.cookies.getAll({ url });
    const cookieHeader = cookies.map((c) => `${c.name}=${c.value}`).join('; ').slice(0, 4096);
    if (cookieHeader) {
      headers['Cookie'] = cookieHeader;
    }
    return headers;
  } catch (e) {
    console.warn("[DM] Failed to get cookies:", e);
    return headers;
  }
}

async function sendBatch(rawItems, pageUrl) {
  const candidates = Array.isArray(rawItems) ? rawItems.slice(0, 200) : [];
  const items = await Promise.all(candidates.map(async (item) => ({
    source: item.source,
    filename: item.filename,
    headers: await getHeadersForUrl(item.source, pageUrl),
  })));
  const result = await sendToNativeHost({ action: "batch_add", items });
  await chrome.storage.local.set({
    lastResult: { ...result, source: `${candidates.length} page links`, at: Date.now() },
  });
  return result;
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "send-to-dm",
      title: "Send link to Download Manager",
      contexts: ["link"],
    });
    chrome.contextMenus.create({
      id: "download-all-dm",
      title: "Download all links on this page",
      contexts: ["page"],
    });
  });
});

// Regular downloads: cancel the browser's own save and hand the URL to
// the desktop app instead, if the user has this turned on.
chrome.downloads.onCreated.addListener(async (item) => {
  const source = item.finalUrl || item.url;
  if (NON_HANDOFF_SCHEMES.some((scheme) => source.startsWith(scheme))) return;
  if (!(await interceptEnabled())) return;

  console.log("[DM] Intercepting download:", source);

  const headers = await getHeadersForUrl(source, item.referrer);
  const result = await sendToNativeHost({ action: "add", source, filename: item.filename ? item.filename.split(/[\\/]/).pop() : undefined, headers, verify: true });
  console.log("[DM] Native host response:", result);
  
  if (result && result.ok) {
    chrome.downloads.cancel(item.id, () => {
      chrome.downloads.erase({ id: item.id });
    });
  } else {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "Download Manager Error",
      message: "Failed to send download to app. The browser will download it normally."
    });
  }
  chrome.storage.local.set({ lastResult: { ...result, source, at: Date.now() } });
});

// Magnet links (from content.js) and popup requests (ping / manual add).
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "magnet") {
    getHeadersForUrl(msg.url).then(headers => {
      sendToNativeHost({ action: "add", source: msg.url, headers, verify: true }).then((result) => {
        chrome.storage.local.set({ lastResult: { ...result, source: msg.url, at: Date.now() } });
        sendResponse(result);
      });
    });
    return true; // keep the message channel open for the async response
  }
  if (msg.type === "ping") {
    sendToNativeHost({ action: "ping" }).then(sendResponse);
    return true;
  }
  if (msg.type === "manual-add") {
    getHeadersForUrl(msg.url).then(headers => {
      sendToNativeHost({ action: "add", source: msg.url, headers, verify: true }).then((result) => {
        chrome.storage.local.set({ lastResult: { ...result, source: msg.url, at: Date.now() } });
        sendResponse(result);
      });
    });
    return true;
  }
  if (msg.type === "batch-add") {
    sendBatch(msg.items, msg.pageUrl).then(sendResponse);
    return true;
  }
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "send-to-dm" && info.linkUrl) {
    const headers = await getHeadersForUrl(info.linkUrl, info.pageUrl);
    const result = await sendToNativeHost({ action: "add", source: info.linkUrl, headers, verify: true });
    chrome.storage.local.set({ lastResult: { ...result, source: info.linkUrl, at: Date.now() } });
    return;
  }
  if (info.menuItemId === "download-all-dm" && tab?.id) {
    chrome.tabs.sendMessage(tab.id, { type: "scan-page", filter: "all" }, (scan) => {
      if (chrome.runtime.lastError || !scan?.ok) return;
      sendBatch(scan.items, scan.pageUrl);
    });
  }
});
