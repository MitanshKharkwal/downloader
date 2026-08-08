const toggle = document.getElementById("intercept-toggle");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const manualUrl = document.getElementById("manual-url");
const manualAddBtn = document.getElementById("manual-add-btn");
const lastResultEl = document.getElementById("last-result");

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
      statusText.textContent = "App not reachable";
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

init();
