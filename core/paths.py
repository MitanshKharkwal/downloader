"""Shared destination naming and conservative file cleanup."""

import os
import re
import shutil


def safe_filename(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("Filename must be text")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not name:
        name = "download"
    base, ext = os.path.splitext(name)
    if base.upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)],
    }:
        base = "_" + base
    ext = ext[:20]
    return base[: 150 - len(ext)] + ext


def unique_path(directory: str, name: str, reserved=()) -> str:
    name = safe_filename(name)
    base, ext = os.path.splitext(name)
    occupied = {os.path.normcase(os.path.abspath(p)) for p in reserved}
    candidate = os.path.join(directory, name)
    counter = 1
    while os.path.normcase(os.path.abspath(candidate)) in occupied or any(
        os.path.exists(candidate + suffix)
        for suffix in ("", ".part", ".dmpart", ".dmpart.json", ".ytdl")
    ):
        candidate = os.path.join(directory, f"{base} ({counter}){ext}")
        counter += 1
    return candidate


def cleanup_task_files(task) -> None:
    if task.type.value == "torrent":
        # Legacy torrents use a shared save directory. Never recursively delete it.
        if (
            task.owns_dest_dir
            and os.path.basename(os.path.abspath(task.dest_path)) == task.id
        ):
            shutil.rmtree(task.dest_path, ignore_errors=True)
        return
    for suffix in ("", ".part", ".dmpart.json", ".dmpart.json.tmp", ".ytdl"):
        path = task.dest_path + suffix
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
