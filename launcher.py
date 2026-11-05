"""bracket — the desktop app's entry point.

Double-clicking the app runs this: it starts the drafting server on this machine, opens it in the default browser,
and shows a small window with the address and a Quit button. Closing that window stops everything, including the
local model. Opening the app again while it runs just opens the browser again.

From a terminal (the packaged app or ``uv run python launcher.py``):

    --headless        no window and no browser: serve until interrupted (servers, scripts, tests)
    --port N          listen on port N (default 8765, or the next free port)
    --no-browser      do not open the browser
    --data DIR        keep settings, models and logs in DIR instead of the per-user data folder
    --doctor          check the setup with real calls and exit
    --version         print the version and exit
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser


def _quiet_streams() -> None:
    """A windowed app on Windows has no console: stdout and stderr are None, and anything that prints would fail."""
    if sys.stdout is None or sys.stderr is None:
        from pathlib import Path

        from platformdirs import user_data_dir

        logs = Path(os.environ.get("BRACKET_DATA") or user_data_dir("bracket", appauthor=False)) / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        f = open(logs / "bracket.log", "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


def _is_bracket(url: str) -> bool:
    import httpx

    try:
        r = httpx.get(f"{url}/api/status", timeout=1.5)
        return r.status_code == 200 and "session" in r.json()
    except Exception:  # noqa: BLE001
        return False


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(argv: list[str] | None = None) -> int:
    import multiprocessing

    multiprocessing.freeze_support()   # a frozen app must not re-run itself if a library starts a child process
    ap = argparse.ArgumentParser(prog="bracket", description="A drafting table for rooms that have to agree.")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--data")
    ap.add_argument("--doctor", action="store_true")
    ap.add_argument("--version", action="store_true")
    # macOS passes -psn_… to apps opened from the Finder on some versions; ignore anything unknown
    args, _unknown = ap.parse_known_args(argv)
    if args.data:
        os.environ["BRACKET_DATA"] = os.path.abspath(os.path.expanduser(args.data))
    _quiet_streams()
    if os.environ.get("BRACKET_TRACE_HANG"):   # diagnostics: dump every thread's stack if start-up hangs
        import faulthandler

        faulthandler.dump_traceback_later(int(os.environ["BRACKET_TRACE_HANG"]), exit=False, file=sys.stderr)

    if args.version:
        from backend import config

        print(f"bracket {config.VERSION}")
        return 0
    if args.doctor:
        import asyncio

        from backend import doctor

        return asyncio.run(doctor.main())

    url = f"http://127.0.0.1:{args.port}"
    if _is_bracket(url):   # already running: bring it forward instead of starting a second server
        if not args.headless and not args.no_browser:
            webbrowser.open(url)
        print(f"bracket is already running at {url}")
        return 0
    port = args.port if _port_free(args.port) else _free_port()
    url = f"http://127.0.0.1:{port}"

    print("bracket: loading the language tools...", flush=True)
    import uvicorn

    from backend import app as server_app

    server = uvicorn.Server(uvicorn.Config(server_app.app, host="127.0.0.1", port=port, log_level="warning"))
    server_app._shutdown_hook = lambda: setattr(server, "should_exit", True)
    thread = threading.Thread(target=server.run, name="bracket-server", daemon=True)
    thread.start()
    t0 = time.monotonic()
    while not server.started and thread.is_alive() and time.monotonic() - t0 < 120:
        time.sleep(0.1)
    if not server.started:
        print("bracket could not start its server; see the log in the data folder.", file=sys.stderr)
        return 1
    print(f"bracket {server_app.config.VERSION} is running at {url}  (data: {server_app.config.DATA_DIR})", flush=True)
    if os.environ.get("BRACKET_TRACE_HANG"):
        import faulthandler

        faulthandler.cancel_dump_traceback_later()

    if args.headless:
        try:
            while thread.is_alive():
                thread.join(0.5)
        except KeyboardInterrupt:
            server.should_exit = True
            thread.join(10)
        return 0

    if not args.no_browser:
        webbrowser.open(url)
    if not _window(url, server, thread, server_app.config):
        try:   # no windowing toolkit (a minimal Linux install): serve until interrupted
            while thread.is_alive():
                thread.join(0.5)
        except KeyboardInterrupt:
            server.should_exit = True
    thread.join(10)
    return 0


def _window(url: str, server, thread: threading.Thread, config) -> bool:
    """A small control window: where bracket is, Open, Quit. Returns False if no window can be shown."""
    try:
        import tkinter as tk
    except ImportError:
        return False
    try:
        root = tk.Tk()
    except tk.TclError:
        return False

    def quit_app(*_):
        server.should_exit = True
        root.after(150, root.destroy)

    root.title("bracket")
    root.configure(bg="#0a0a0b", padx=28, pady=22)
    root.resizable(False, False)
    fg, dim = "#ffffff", "#8a8a8a"
    tk.Label(root, text="[bracket]", font=("Georgia", 20), fg=fg, bg="#0a0a0b").pack(anchor="w")
    tk.Label(root, text=f"Running at {url}", fg=dim, bg="#0a0a0b").pack(anchor="w", pady=(6, 2))
    tk.Label(root, text="Everything stays on this computer unless you turn on Claude.", fg=dim, bg="#0a0a0b").pack(anchor="w")
    row = tk.Frame(root, bg="#0a0a0b")
    row.pack(anchor="w", pady=(16, 0))
    tk.Button(row, text="Open bracket", command=lambda: webbrowser.open(url), highlightbackground="#0a0a0b").pack(side="left")
    tk.Button(row, text="Quit", command=quit_app, highlightbackground="#0a0a0b").pack(side="left", padx=(10, 0))
    tk.Label(root, text=f"Data: {config.DATA_DIR}", fg="#5a5a5a", bg="#0a0a0b", font=("TkDefaultFont", 9)).pack(anchor="w", pady=(16, 0))
    root.protocol("WM_DELETE_WINDOW", quit_app)
    try:
        root.createcommand("tk::mac::Quit", quit_app)          # Cmd-Q and Quit in the Dock menu
        root.createcommand("tk::mac::ReopenApplication", lambda: webbrowser.open(url))   # clicking the Dock icon
    except tk.TclError:
        pass

    def watch():   # Quit pressed in the page closes the window too
        if server.should_exit or not thread.is_alive():
            root.destroy()
        else:
            root.after(400, watch)

    root.after(400, watch)
    root.mainloop()
    server.should_exit = True
    return True


if __name__ == "__main__":
    sys.exit(main())
