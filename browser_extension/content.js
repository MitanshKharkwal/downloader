// Chrome has no built-in handler for magnet: links, so a click on one
// normally either does nothing or triggers an OS-level "open with"
// prompt. Catch it in the capture phase, before any page script or
// Chrome's own navigation handling sees it, and hand it to the
// extension's background worker instead.
document.addEventListener(
  "click",
  (event) => {
    const link = event.target.closest && event.target.closest('a[href^="magnet:"]');
    if (!link) return;

    event.preventDefault();
    event.stopPropagation();

    chrome.runtime.sendMessage({ type: "magnet", url: link.href }, (response) => {
      if (chrome.runtime.lastError) return; // extension context gone, nothing to do
      if (!response || !response.ok) {
        console.warn("Download Manager: couldn't reach the desktop app for", link.href, response);
      }
    });
  },
  true // capture phase
);
