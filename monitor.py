"""
monitor.py  —  Watches SESSIONS_FOLDER continuously.
- On startup: inserts ALL existing folders into the db
- While running: detects and inserts any NEW folders too
- Runs forever until Ctrl-C
"""

from __future__ import annotations
import os
import sys
import time
import signal
from datetime import datetime

import db
import credentials as cfg


# ─── Colours ─────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
WHITE  = "\033[97m"

def c(colour, text):
    return f"{colour}{text}{RESET}"


# ─── Logging ──────────────────────────────────────────────────────────────────

def log(level, msg):
    ts      = datetime.now().strftime("%H:%M:%S")
    colours = {"INFO": CYAN, "NEW": GREEN, "WARN": YELLOW, "ERROR": RED, "SKIP": DIM}
    colour  = colours.get(level, RESET)
    tag     = c(colour, f"[{level:<5}]")
    print(f"  {c(DIM, ts)}  {tag}  {msg}")


def print_banner():
    os.system("cls" if os.name == "nt" else "clear")
    w = 54
    print()
    print(c(CYAN,  "┌" + "─" * w + "┐"))
    print(c(CYAN,  "│") + c(BOLD + WHITE, "        SESSION FOLDER MONITOR".center(w)) + c(CYAN, "│"))
    print(c(CYAN,  "├" + "─" * w + "┤"))

    db_line  = (f"SQLite → {os.path.abspath(cfg.SQLITE_PATH)}")[:w-4]
    fol_line = cfg.SESSIONS_FOLDER[:w-4]

    for label, val in [("DB", db_line), ("Folder", fol_line),
                       ("Poll", f"every {cfg.POLL_INTERVAL}s"), ("Stop", "Ctrl-C")]:
        row = f"  {label:<8}: {val}"
        print(c(CYAN, "│") + c(WHITE, row.ljust(w)) + c(CYAN, "│"))

    print(c(CYAN, "└" + "─" * w + "┘"))
    print()


# ─── Core ─────────────────────────────────────────────────────────────────────

def scan_folders(watch_dir):
    """Return set of all immediate sub-folder names inside watch_dir."""
    try:
        return {e.name for e in os.scandir(watch_dir) if e.is_dir()}
    except PermissionError:
        log("ERROR", f"Permission denied: {watch_dir}")
        return set()
    except FileNotFoundError:
        log("WARN",  f"Folder not found: {watch_dir}  — will retry...")
        return set()


def save_folder(name):
    """
    Insert folder into DB.
    - If already in DB: skip silently
    - If new: insert and print a line
    Returns True if inserted, False if skipped.
    """
    if db.folder_exists(name):
        return False  # already recorded, skip
    try:
        entry = db.add_session(foldername=name)
        log("NEW", (
            f"{c(GREEN + BOLD, name)}"
            f"  {c(DIM, '→')}"
            f"  id={c(WHITE, str(entry.id))}"
            f"  date={c(WHITE, str(entry.date))}"
            f"  time={c(WHITE, str(entry.time))}"
            f"  isUpload={c(YELLOW, str(entry.isUpload))}"
        ))
        return True
    except Exception as exc:
        log("ERROR", f"Could not save '{name}': {exc}")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def run():

    # Ctrl-C handler
    def _exit(sig, frame):
        print()
        log("INFO", "Monitor stopped. Goodbye.")
        print()
        sys.exit(0)

    signal.signal(signal.SIGINT, _exit)

    print_banner()

    # Connect to DB
    try:
        db.init_db()
        log("INFO", "Database ready.")
    except Exception as exc:
        log("ERROR", f"Cannot connect to database: {exc}")
        log("ERROR", "Run setup.py first.")
        sys.exit(1)

    watch_dir = cfg.SESSIONS_FOLDER

    # Wait for the network share to become available
    if not os.path.exists(watch_dir):
        log("WARN", f"Share not reachable yet: {watch_dir}")
        log("INFO", "Waiting for share to become available...")
        while not os.path.exists(watch_dir):
            time.sleep(cfg.POLL_INTERVAL)
        log("INFO", "Share is now reachable.")

    # ── Startup: insert ALL existing folders ──────────────────
    print()
    log("INFO", "Scanning existing folders on startup...")
    existing = scan_folders(watch_dir)

    if existing:
        inserted = 0
        skipped  = 0
        for name in sorted(existing):
            if save_folder(name):
                inserted += 1
            else:
                skipped += 1
        log("INFO", (
            f"Startup scan done — "
            f"{c(GREEN, str(inserted))} new, "
            f"{c(DIM, str(skipped))} already in db"
        ))
    else:
        log("INFO", "No existing folders found — share is empty.")

    known = existing.copy()

    # ── Continuous watch loop ─────────────────────────────────
    print()
    log("INFO", f"Watching for new folders every {cfg.POLL_INTERVAL}s...")
    print(c(DIM, "  " + "─" * 52))

    while True:
        time.sleep(cfg.POLL_INTERVAL)

        current = scan_folders(watch_dir)

        if current is None:
            continue

        new_folders = current - known

        for name in sorted(new_folders):
            save_folder(name)

        if new_folders:
            known = current   # update snapshot


if __name__ == "__main__":
    run()