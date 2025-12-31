from __future__ import annotations

import os
import time


def _acquire_lock(lock_path: str, timeout_s: float = 5.0) -> None:
    start = time.time()
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.close(fd)
            return
        except FileExistsError:
            if (time.time() - start) > timeout_s:
                raise TimeoutError(f"Timeout acquiring lock: {lock_path}")
            time.sleep(0.05)


def _release_lock(lock_path: str) -> None:
    try:
        os.remove(lock_path)
    except Exception:
        pass


def append_jsonl_line(path: str, line: str) -> None:
    if not line.endswith("\n"):
        line = line + "\n"

    lock_path = path + ".lock"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    _acquire_lock(lock_path, timeout_s=5.0)
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line)
            f.flush()
    finally:
        _release_lock(lock_path)

