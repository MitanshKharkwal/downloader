"""Minimal demo: add sources on the command line, watch progress in the
terminal. Not a real UI -- just proof the core engine works standalone
before the Windows/Android front-ends exist.

Usage:
    python example_cli.py <url_or_magnet> [<url_or_magnet> ...]
"""

from __future__ import annotations

import sys
import time

from core import DownloadManager, DownloadStatus


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:,.1f}{unit}"
        n /= 1024
    return f"{n:,.1f}TB"


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    manager = DownloadManager(download_dir="./downloads", max_concurrent_downloads=3)
    tasks = [manager.add(src) for src in sys.argv[1:]]

    def on_progress(task):
        pass  # printed in the poll loop below to avoid a wall of output

    manager.events.on("progress", on_progress)

    try:
        while True:
            all_done = True
            lines = []
            for task in tasks:
                t = manager.get(task.id)
                if t.status not in (DownloadStatus.COMPLETED, DownloadStatus.ERROR, DownloadStatus.CANCELED):
                    all_done = False
                pct = t.progress() * 100
                extra = f"peers={t.num_peers}" if t.type.value == "torrent" else f"conns={t.num_connections}"
                lines.append(
                    f"[{t.status.value:>11}] {pct:5.1f}%  "
                    f"{human_bytes(t.downloaded_bytes)}/{human_bytes(t.total_bytes)}  "
                    f"{human_bytes(t.speed_bps)}/s  {extra}  {t.name or t.source[:40]}"
                )
            print("\033c", end="")  # clear terminal each tick
            print("\n".join(lines))
            if all_done:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        manager.shutdown()


if __name__ == "__main__":
    main()
