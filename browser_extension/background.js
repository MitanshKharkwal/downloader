const NATIVE_HOST = "com.downloadmanager.native_host";
const NON_HANDOFF_SCHEMES = ["blob:", "data:"];

function sendToNativeHost(message) {
  return new Promise((resolve) => {
    chrome.runtime.sendNativeMessage(NATIVE_HOST, message, (response) => {
      if (chrome.runtime.lastError) {
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

// Regular downloads: cancel the browser's own save and hand the URL to
// the desktop app instead, if the user has this turned on.
chrome.downloads.onCreated.addListener(async (item) => {
  if (NON_HANDOFF_SCHEMES.some((scheme) => item.url.startsWith(scheme))) return;
  if (!(await interceptEnabled())) return;

  chrome.downloads.cancel(item.id, () => chrome.downloads.erase({ id: item.id }));
  const result = await sendToNativeHost({ action: "add", source: item.url, filename: item.filename });
  chrome.storage.local.set({ lastResult: { ...result, source: item.url, at: Date.now() } });
});

// Magnet links (from content.js) and popup requests (ping / manual add).
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "magnet") {
    sendToNativeHost({ action: "add", source: msg.url }).then((result) => {
      chrome.storage.local.set({ lastResult: { ...result, source: msg.url, at: Date.now() } });
      sendResponse(result);
    });
    return true; // keep the message channel open for the async response
  }
  if (msg.type === "ping") {
    sendToNativeHost({ action: "ping" }).then(sendResponse);
    return true;
  }
  if (msg.type === "manual-add") {
    sendToNativeHost({ action: "add", source: msg.url }).then((result) => {
      chrome.storage.local.set({ lastResult: { ...result, source: msg.url, at: Date.now() } });
      sendResponse(result);
    });
    return true;
  }
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "send-to-dm",
    title: "Send link to Download Manager",
    contexts: ["link"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== "send-to-dm" || !info.linkUrl) return;
  const result = await sendToNativeHost({ action: "add", source: info.linkUrl });
  chrome.storage.local.set({ lastResult: { ...result, source: info.linkUrl, at: Date.now() } });
});
