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

const downloadFilters = {
  all: null,
  documents: new Set(['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv']),
  media: new Set(['mp4', 'mkv', 'avi', 'mov', 'webm', 'mp3', 'wav', 'flac', 'm4a', 'jpg', 'jpeg', 'png', 'gif', 'webp']),
  archives: new Set(['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'iso']),
  programs: new Set(['exe', 'msi', 'msix', 'apk', 'dmg', 'pkg', 'deb', 'rpm']),
};

function linksOnPage(filter = 'all') {
  const extensions = downloadFilters[filter] || null;
  const seen = new Set();
  const items = [];
  for (const anchor of document.querySelectorAll('a[href]')) {
    let url;
    try {
      url = new URL(anchor.href, document.baseURI);
    } catch (_) {
      continue;
    }
    if (!['http:', 'https:', 'magnet:'].includes(url.protocol)) continue;
    let filename = anchor.download || url.pathname.split('/').pop() || '';
    try {
      filename = decodeURIComponent(filename);
    } catch (_) {
      // Keep the encoded path when a page contains malformed percent escapes.
    }
    const extension = filename.includes('.') ? filename.split('.').pop().toLowerCase() : '';
    if (extensions && !extensions.has(extension)) continue;
    const source = url.href;
    if (seen.has(source)) continue;
    seen.add(source);
    items.push({ source, filename: filename || undefined });
    if (items.length === 200) break;
  }
  return items;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== 'scan-page') return;
  sendResponse({
    ok: true,
    title: document.title,
    pageUrl: location.href,
    items: linksOnPage(message.filter),
  });
});
