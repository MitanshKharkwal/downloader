const toggle = document.getElementById("intercept-toggle");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const manualUrl = document.getElementById("manual-url");
const manualAddBtn = document.getElementById("manual-add-btn");
const lastResultEl = document.getElementById("last-result");
const downloadAllBtn = document.getElementById("download-all-btn");
const batchFilter = document.getElementById("batch-filter");

async function init() {
  const { interceptDownloads = true } = await chrome.storage.local.get("interceptDownloads");
  toggle.checked = interceptDownloads;

  const { lastResult } = await chrome.storage.local.get("lastResult");
  if (lastResult) {
    const when = new Date(lastResult.at).toLocaleTimeString();
    lastResultEl.textContent = lastResult.ok
      ? `Last sent OK at ${when}: ${lastResult.source}`
      : `Last attempt failed at ${when}: ${lastResult.error}`;
  }

  chrome.runtime.sendMessage({ type: "ping" }, (response) => {
    if (chrome.runtime.lastError || !response || !response.ok) {
      statusDot.className = "dot bad";
      statusText.textContent = response?.error || chrome.runtime.lastError?.message || "App not reachable";
      return;
    }
    if (!response.app_token_found) {
      statusDot.className = "dot bad";
      statusText.textContent = "App has never been run";
      return;
    }
    statusDot.className = "dot ok";
    statusText.textContent = "Connected";
  });
}

toggle.addEventListener("change", () => {
  chrome.storage.local.set({ interceptDownloads: toggle.checked });
});

manualAddBtn.addEventListener("click", () => {
  const url = manualUrl.value.trim();
  if (!url) return;
  manualAddBtn.disabled = true;
  manualAddBtn.textContent = "Sending...";
  chrome.runtime.sendMessage({ type: "manual-add", url }, (response) => {
    manualAddBtn.disabled = false;
    manualAddBtn.textContent = "Send to Download Manager";
    lastResultEl.textContent =
      response && response.ok ? `Sent: ${url}` : `Failed: ${response && response.error}`;
    if (response && response.ok) manualUrl.value = "";
  });
});

downloadAllBtn.addEventListener("click", async () => {
  downloadAllBtn.disabled = true;
  downloadAllBtn.textContent = "Scanning page...";
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    lastResultEl.textContent = "No active page is available.";
    downloadAllBtn.disabled = false;
    downloadAllBtn.textContent = "Find and add links";
    return;
  }
  chrome.tabs.sendMessage(tab.id, { type: "scan-page", filter: batchFilter.value }, (scan) => {
    if (chrome.runtime.lastError || !scan?.ok) {
      lastResultEl.textContent = "This page cannot be scanned.";
      downloadAllBtn.disabled = false;
      downloadAllBtn.textContent = "Find and add links";
      return;
    }
    if (!scan.items.length) {
      lastResultEl.textContent = "No matching links found.";
      downloadAllBtn.disabled = false;
      downloadAllBtn.textContent = "Find and add links";
      return;
    }
    downloadAllBtn.textContent = `Adding ${scan.items.length} links...`;
    chrome.runtime.sendMessage({ type: "batch-add", items: scan.items, pageUrl: scan.pageUrl }, (result) => {
      lastResultEl.textContent = result?.ok
        ? `Added ${result.added}; ${result.skipped} duplicates; ${result.failed} failed.`
        : `Failed: ${result?.error || 'No response'}`;
      downloadAllBtn.disabled = false;
      downloadAllBtn.textContent = "Find and add links";
    });
  });
});

init();
