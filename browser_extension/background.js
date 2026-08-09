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

async function getHeadersForUrl(url) {
  try {
    const cookies = await chrome.cookies.getAll({ url });
    const cookieHeader = cookies.map((c) => `${c.name}=${c.value}`).join('; ');
    const headers = {
      'User-Agent': navigator.userAgent
    };
    if (cookieHeader) {
      headers['Cookie'] = cookieHeader;
    }
    return headers;
  } catch (e) {
    console.warn("[DM] Failed to get cookies:", e);
    return { 'User-Agent': navigator.userAgent };
  }
}

// Keep the service worker alive by creating an alarm that fires periodically.
// MV3 service workers go dormant after ~30 seconds of inactivity, which breaks
// the downloads.onCreated listener. This heartbeat prevents that.
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("keepalive", { periodInMinutes: 0.4 });

  chrome.contextMenus.create({
    id: "send-to-dm",
    title: "Send link to Download Manager",
    contexts: ["link"],
  });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "keepalive") {
    // Just wake up the service worker - no real work needed
  }
});

// Regular downloads: cancel the browser's own save and hand the URL to
// the desktop app instead, if the user has this turned on.
chrome.downloads.onCreated.addListener(async (item) => {
  if (NON_HANDOFF_SCHEMES.some((scheme) => item.url.startsWith(scheme))) return;
  if (!(await interceptEnabled())) return;

  console.log("[DM] Intercepting download:", item.url);

  // Cancel the browser's download immediately
  chrome.downloads.cancel(item.id, () => {
    chrome.downloads.erase({ id: item.id });
  });

  const headers = await getHeadersForUrl(item.url);
  const result = await sendToNativeHost({ action: "add", source: item.url, filename: item.filename, headers });
  console.log("[DM] Native host response:", result);
  chrome.storage.local.set({ lastResult: { ...result, source: item.url, at: Date.now() } });
});

// Magnet links (from content.js) and popup requests (ping / manual add).
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "magnet") {
    getHeadersForUrl(msg.url).then(headers => {
      sendToNativeHost({ action: "add", source: msg.url, headers }).then((result) => {
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
      sendToNativeHost({ action: "add", source: msg.url, headers }).then((result) => {
        chrome.storage.local.set({ lastResult: { ...result, source: msg.url, at: Date.now() } });
        sendResponse(result);
      });
    });
    return true;
  }
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== "send-to-dm" || !info.linkUrl) return;
  const headers = await getHeadersForUrl(info.linkUrl);
  const result = await sendToNativeHost({ action: "add", source: info.linkUrl, headers });
  chrome.storage.local.set({ lastResult: { ...result, source: info.linkUrl, at: Date.now() } });
});
