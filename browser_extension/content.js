let captureMagnets = true;
chrome.storage.local.get('interceptDownloads').then(({ interceptDownloads = true }) => {
  captureMagnets = interceptDownloads;
});
chrome.storage.onChanged.addListener((changes) => {
  if (changes.interceptDownloads) captureMagnets = changes.interceptDownloads.newValue;
});
// Chrome has no built-in handler for magnet: links, so a click on one
// normally either does nothing or triggers an OS-level "open with"
// prompt. Catch it in the capture phase, before any page script or
// Chrome's own navigation handling sees it, and hand it to the
// extension's background worker instead.
document.addEventListener(
  "click",
  (event) => {
    const link = event.target.closest && event.target.closest('a[href^="magnet:"]');
    if (!link || !captureMagnets) return;

    event.preventDefault();
    event.stopPropagation();

    chrome.runtime.sendMessage({ type: "magnet", url: link.href }, (response) => {
      if (chrome.runtime.lastError) return; // extension context gone, nothing to do
      if (!response || !response.ok) {
        window.alert("Download Manager could not accept this magnet link. Disable capture in the extension to open it with another app.");
      }
    });
  },
  true // capture phase
);
