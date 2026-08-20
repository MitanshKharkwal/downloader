# Command Doc: Fix Bugs in `downloader` (for Gemini)

Repo: https://github.com/MitanshKharkwal/downloader (main branch, reviewed 2026-08-19)

Do not redesign anything. Fix each bug below in place, preserving existing style/behavior otherwise. Test each fix against the relevant file in `tests/` where one exists, and add a small test if none covers it.

---

## BUG 1 (CRITICAL) — Flutter IPC client uses wrong RPC method names/args; every core action is broken
**File:** `flutter_ui/lib/services/ipc_client.dart`

The daemon's `/rpc` dispatcher (`core/ipc_server.py`) only recognizes these methods, all keyed by `task_id`:
`list_tasks, add_video_task, fetch_video_info, pause, resume, retry, pause_all, resume_all, cancel, set_priority, clear_finished, shutdown, get_config, set_config`.

There is **no** `add_url` RPC method — adding a URL must go through the legacy HTTP endpoint `POST /add` with body `{"source": ..., "filename": ..., "headers": ...}` (see `core/ipc_server.py` do_POST `/add` handler), not `/rpc`.

But `ipc_client.dart` currently calls:
- `addUrl()` → `_callMethod('add_url', {'url': url})` — wrong endpoint AND wrong method name AND wrong arg key (`url` instead of `source`). Will always return "unknown method".
- `pauseTask()` → `_callMethod('pause_task', {'id': id})` — should be method `pause`, arg key `task_id`.
- `resumeTask()` → `_callMethod('resume_task', {'id': id})` — should be method `resume`, arg key `task_id`.
- `cancelTask()` → `_callMethod('cancel_task', {'id': id})` — should be method `cancel`, arg key `task_id`.

**Fix:**
1. Add a helper that POSTs JSON directly to `http://127.0.0.1:47821/add` (same token header) for `addUrl()`, sending `{"source": url}`.
2. Change `pauseTask`/`resumeTask`/`cancelTask` to call RPC methods `pause`/`resume`/`cancel` with arg key `task_id` (not `id`).
3. Grep the rest of `flutter_ui/lib` for any other `_callMethod(...)` calls with method names not in the list above (e.g. future `set_priority`, `retry` calls) and correct them the same way — arg key must be `task_id`, and `set_priority`'s `priority` arg must be an int (0=LOW,1=NORMAL,2=HIGH) since that's what the daemon expects (see BUG 4).

**Verify:** with the daemon running, tapping Pause/Resume/Cancel/Add-URL in the Flutter app should now actually change task state instead of throwing "RPC call returned error: unknown method".

---

## BUG 2 (HIGH) — Duplicate `retry()` method definition silently breaks retry for completed/failed downloads
**File:** `core/manager.py`, lines ~305-312 and ~344-358

`DownloadManager` defines `retry()` **twice**. Python keeps only the second definition; the first is dead code that is never reachable.

- First definition (dead): allows retrying tasks with status `FAILED` or `COMPLETED`.
- Second definition (the one actually used): only allows retrying tasks with status `ERROR`.

Two problems:
1. `DownloadStatus.FAILED` referenced in the dead code **does not exist** in `core/models.py` (only `QUEUED, CONNECTING, DOWNLOADING, PAUSED, COMPLETED, ERROR, CANCELED`) — if that dead code were ever reached it would throw `AttributeError`.
2. Because only the second definition survives, there is currently **no way to re-download a COMPLETED task** via `retry()` — which the first definition's docstring/logic implies was intended functionality.

**Fix:**
- Delete the first (dead) definition entirely.
- Decide the intended behavior for the surviving one: if re-downloading a COMPLETED task should be supported, extend its status check to `(DownloadStatus.ERROR, DownloadStatus.COMPLETED)` and reset `downloaded_bytes`/`total_bytes`/`completed_at` appropriately before requeueing. If it should NOT be supported, leave the ERROR-only check but remove the misleading references to `FAILED`/`COMPLETED` everywhere (including the docstring).
- Also note the surviving `retry()` acquires `self._lock` correctly; the deleted one did not (`task = self._tasks.get(task_id)` outside the lock then mutated) — make sure whichever version remains follows the locking pattern of the surviving one.

---

## BUG 3 (HIGH) — Pausing a video (yt-dlp) download marks it ERROR instead of PAUSED, and Resume becomes permanently broken
**File:** `core/video_downloader.py`

`pause()` (line ~43) and `cancel()` (line ~62) both set the **same** `self._cancel_event`. `_progress_hook` (line ~71) raises `Exception("Cancelled")` whenever `_cancel_event` is set, regardless of whether the caller wanted a pause or a real cancel. That exception propagates out of `yt_dlp.YoutubeDL.download()`.

In `_run()`'s except block (line ~116):
```python
except Exception as e:
    if str(e) == "Cancelled":
        pass
    else:
        self.task.status = DownloadStatus.ERROR
        ...
```
yt-dlp does not guarantee the exception it re-raises after a progress-hook exception has `str(e) == "Cancelled"` — yt-dlp typically wraps hook exceptions in its own `DownloadError` with additional text (e.g. prefixed with `"ERROR: "` or including yt-dlp's own formatting). When the string doesn't match exactly, this code incorrectly sets `task.status = DownloadStatus.ERROR` and overwrites the `PAUSED` status that `pause()` had just set — immediately after the user pressed Pause.

Then `resume()` (line ~51) guards with `if self.task.status != DownloadStatus.PAUSED: return`, so once the status has been flipped to ERROR, **Resume silently does nothing** — the task is stuck.

**Fix:**
1. Give pause and cancel separate flags (e.g. `self._pause_requested` and keep `_cancel_event` only for real cancellation), OR keep one event but add a boolean `self._is_pausing` that `_run()` checks *before* falling back to the string-match on the exception, so a pause never reaches the ERROR branch.
2. Do not rely on matching the exact exception string from yt-dlp. Check `self._cancel_event.is_set()` (or the new pause flag) directly in the except block to decide PAUSED vs ERROR vs real cancel, the same way `core/http_downloader.py`'s `_run()` does it (`if self._cancel_event.is_set(): return` before ever touching status).
3. Add/extend a test (see `tests/` for existing patterns) that starts a video task, pauses it, and asserts status becomes `PAUSED` (not `ERROR`), then resumes and asserts it proceeds.

---

## BUG 4 (MEDIUM) — `set_priority` RPC accepts a raw int/string and can corrupt `DownloadTask.priority`, breaking state serialization
**Files:** `core/ipc_server.py` (`set_priority` handler, line ~203) and `core/manager.py` (`DownloadManager.set_priority`, line ~360)

`ipc_server.py` passes `args["priority"]` straight through from the JSON request body:
```python
manager.set_priority(args["task_id"], args["priority"])
```
`DownloadManager.set_priority` then does `task.priority = priority` directly. If the caller sends a plain JSON int (which is what any RPC client will naturally send — Dart/JS have no `Priority` enum), `task.priority` becomes a raw `int`, not a `Priority` enum member, even though comparisons like `priority == Priority.HIGH` happen to still work today (IntEnum compares equal to plain ints).

The real break is in `DownloadTask.to_dict()` (`core/models.py`):
```python
d["priority"] = self.priority.value
```
A plain `int` has no `.value` attribute → this raises `AttributeError` the next time `_save_state()`/`to_dict()` runs on that task (e.g. right after the RPC call, since `set_priority` calls `self._save_state()` itself), which will crash state persistence for that task (and, depending on where it's called from, potentially the RPC response with a 500).

**Fix:** In `ipc_server.py`'s `set_priority` handler, convert the incoming value explicitly before calling the manager: `priority = Priority(int(args["priority"]))` (import `Priority` from `core.models`), and pass that. Add a try/except around the conversion that returns a 400 with a clear error on invalid values instead of a 500.

---

## BUG 5 (MEDIUM) — Silent infinite retry when an HTTP server truncates a ranged response without erroring
**File:** `core/http_downloader.py`, `_download_segment()`, the `for...else` block around line ~481

When `resp.iter_content()` finishes iterating (stream closed normally) but `seg.done` is still `False` — i.e., the server advertised/accepted a Range but sent fewer bytes than promised and simply closed the connection without an HTTP error — the `for/else` branch only updates `total_bytes` for the *non-ranged* case (`not self.task.supports_ranges`). For the ranged case, nothing happens: no exception is raised, so `consecutive_failures` is never incremented and no backoff occurs. The outer `while not seg.done and not self._cancel_event.is_set()` loop immediately re-requests the same range and can spin as fast as the network round-trip allows, forever, if the host keeps truncating the same way — silently, since no error is ever surfaced to `task.error_message` or the UI.

This is the same class of bug as the already-fixed "infinite silent retry loop on persistently failing hosts" (see project history), but that fix only covers the exception path (`except requests.RequestException`), not this truncated-stream-without-exception path.

**Fix:** In the ranged branch of the `for/else`, if the loop completes without `seg.done` being true, treat it the same as a transient failure: increment `consecutive_failures`, set a short backoff (`time.sleep(1.5)`), and apply the same `MAX_CONSECUTIVE_SEGMENT_FAILURES * len(sources)` give-up threshold that the exception path uses, so a host that keeps truncating eventually surfaces `DownloadStatus.ERROR` with a clear message instead of spinning forever.

---

## BUG 6 (LOW / VERIFY) — Torrent partfile flag comment doesn't match the flag actually being set
**File:** `core/torrent_engine.py`, `_build_add_params()`, line ~183-185

```python
# Keep partial files as .parts rather than sparse full-size files
# so a half-downloaded task doesn't look deceptively large on disk.
params.flags |= lt.torrent_flags.duplicate_is_error
```
`duplicate_is_error` is libtorrent's flag for rejecting adding a torrent that's already active with the same info-hash — it has nothing to do with partfile behavior. Whatever flag was intended for "use .parts instead of sparse allocation" (check current libtorrent docs for the correct flag name/option, since `python-libtorrent`'s add_torrent_params flags have changed across versions) is not actually being set.

**Fix:** Confirm against the installed libtorrent version's docs what flag/setting controls partfile vs. sparse-file allocation, set it correctly, and either keep `duplicate_is_error` as a separate explicit `|=` (if it's genuinely also wanted) or remove it if it was a copy-paste mistake. Update the comment to match whichever flags end up set.

---

## BUG 7 (HIGH) — "Resume" button on a failed (ERROR) task silently does nothing; should call retry
**File:** `flutter_ui/lib/widgets/task_card.dart`, line ~104

```dart
else if (task.status == 'PAUSED' || task.status == 'ERROR')
  IconButton(
    icon: const Icon(Icons.play_arrow, color: Colors.greenAccent),
    onPressed: onResume,
  ),
```
The play button is shown for both `PAUSED` and `ERROR` tasks, but always wired to `onResume` (→ RPC `resume`). Every engine's `resume()` method (`HttpDownload.resume()`, `TorrentDownload.resume()`, `VideoDownload.resume()`) starts with `if self.task.status != DownloadStatus.PAUSED: return` — so calling resume on an `ERROR` task is a guaranteed no-op. The user taps play on a failed download and nothing happens, with no feedback.

**Fix:** In `task_card.dart`, pass a separate `onRetry` callback and use it for the `ERROR` branch instead of `onResume`; in `main.dart`, wire `onRetry: () => _ipcClient.retryTask(task.id)` calling RPC method `retry` (arg `task_id`) as covered in BUG 1. Keep `onResume`/RPC `resume` only for the `PAUSED` case.

---

## BUG 8 (MEDIUM) — Sidebar category filter doesn't match any backend category values
**File:** `flutter_ui/lib/main.dart`, line ~44-46 vs. `core/manager.py` category assignment (`add()`, lines ~177-210)

The Flutter sidebar's category list is:
```dart
final List<String> _categories = [
  'All', 'Downloading', 'Completed', 'Compressed', 'Documents', 'Media', 'Other'
];
```
But `DownloadManager.add()` assigns one of: `"Programs", "Video", "Music", "Documents", "Compressed", "Photos", "Other"` (never `"Media"`). Consequences:
- Selecting **"Media"** in the sidebar always shows an empty list — no task ever has that category.
- Tasks categorized as **"Video"**, **"Music"**, **"Photos"**, or **"Programs"** are only visible under "All" — there's no sidebar entry that filters to them specifically.

**Fix:** Either (a) change the backend's category strings for video/music/photo/program files to match a shared taxonomy the sidebar uses, or (b) update the sidebar list to the real backend category set: `['All', 'Downloading', 'Completed', 'Programs', 'Video', 'Music', 'Documents', 'Compressed', 'Photos', 'Other']`. Pick whichever direction matches the intended IDM-style category grouping, and keep both sides in sync (consider defining the category list once, e.g. as constants in a shared file/comment, so this can't drift again).

---

## BUG 9 (LOW, hygiene) — Machine-specific generated file committed to git with a stale, personal path
**File:** `native_host/native_host_manifest.json`

This file is meant to be generated per-machine by `register_native_host.py` (which writes absolute paths and the local extension ID), but a generated copy is checked into the repo:
```json
"path": "C:\\Users\\mitan\\Downloads\\download_manager_1\\download_manager\\native_host\\run_host.bat",
```
This hardcodes a specific Windows username and a `download_manager_1` numbered folder (a side effect of the zip-extraction-into-numbered-folders workflow) that won't exist on a fresh clone or a different machine, and will silently go stale every time the project is re-extracted into a new numbered folder.

**Fix:** Remove `native_host/native_host_manifest.json` from version control, add it to `.gitignore`, and note in the README that `register_native_host.py` must be run locally after cloning/installing to (re)generate it. Do the same check for `native_host/run_host.bat` if it's also checked in as a generated artifact.

---

## BUG 10 (LOW, lint/type-check) — `Any` used in a type annotation without being imported
**File:** `core/manager.py`, line 115

```python
self._engines: dict[str, HttpDownload | TorrentDownload | Any] = {}
```
`Any` is never imported (`from typing import Any` is missing). This doesn't crash today only because `from __future__ import annotations` (line 9) makes all annotations lazy strings that Python never evaluates at runtime. It will still: (a) be flagged as an undefined name by mypy/pyright/any linter, and (b) raise `NameError` if anything ever calls `typing.get_type_hints()` on `DownloadManager`, or if the `__future__` import is ever removed.

**Fix:** Add `from typing import Any` to the imports in `core/manager.py`.

---

## BUG 11 (LOW) — Add-URL dialog accepts whitespace-only input
**File:** `flutter_ui/lib/widgets/add_url_dialog.dart`, line ~45

```dart
onPressed: () {
  if (_controller.text.isNotEmpty) {
    widget.onAdd(_controller.text);
```
`isNotEmpty` doesn't catch a string of only spaces (e.g. pasted accidentally), which would be sent straight to the backend as `source` and fail with a confusing server-side error instead of just not submitting.

**Fix:** Use `_controller.text.trim().isNotEmpty` in the guard and pass `_controller.text.trim()` to `widget.onAdd(...)`.

---

## Priority order for Gemini to work through
1. BUG 1 (Flutter app is otherwise non-functional for core actions)
2. BUG 3 (video pause/resume is broken)
3. BUG 7 (failed downloads can never be retried from the UI)
4. BUG 2 (retry contract broken/dead code)
5. BUG 4 (latent crash on state save)
6. BUG 5 (silent stuck download edge case)
7. BUG 8 (category filter mismatch)
8. BUG 6 (verify against libtorrent docs, low impact)
9. BUG 9 (stop committing machine-specific manifest)
10. BUG 10 (missing `Any` import)
11. BUG 11 (trim whitespace in add-URL dialog)

After fixing, run the existing suite in `tests/` (especially `tests/test_ipc_server.py`, `tests/resume_test.py`, `tests/retry_test.py`, `tests/rate_limit_test.py`) plus any new tests added for BUGS 3, 5, and 7, and confirm nothing regresses.
