"""bracket — the desktop app's entry point.

Double-clicking the app runs this: it starts the drafting server on this machine and opens bracket in its own window
(macOS: the system WebKit view; Windows: Microsoft Edge WebView2). Closing the window stops everything, including the
local model. Opening the app again while it runs brings its window forward. Where no native window is available
(Linux, or a Windows PC without WebView2) it opens in the default browser, with a small control window to quit.

From a terminal (the packaged app or ``uv run python launcher.py``):

    --headless        no window and no browser: serve until interrupted (servers, scripts, tests)
    --port N          listen on port N (default 8765, or the next free port)
    --no-browser      do not open a window or the browser
    --browser         use the default browser instead of the app's own window
    --window-check N  open the window, check the page loaded and its bridge works, close after N seconds (CI)
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
from pathlib import Path


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
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--window-check", type=float, default=0)
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
            _bring_forward(url)
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

    if not args.browser and not args.no_browser:
        shown = _app_window(url, server, thread, server_app, args.window_check)
        if shown is not None:
            thread.join(10)
            return shown
    if args.window_check:
        print("WINDOW CHECK FAILED: no native window on this platform", flush=True)
        server.should_exit = True
        thread.join(10)
        return 1
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


def _bring_forward(url: str) -> None:
    """A second launch: ask the running app to show its window; if it has none (browser mode), open the browser."""
    import httpx

    try:
        r = httpx.post(f"{url}/api/focus", headers={"X-Bracket": "1"}, timeout=3)
        if r.status_code == 200 and r.json().get("window"):
            return
    except Exception:  # noqa: BLE001
        pass
    webbrowser.open(url)


class _Bridge:
    """Called from the page through window.pywebview.api (only inside the app's own window)."""

    def __init__(self):
        self._window = None   # private: pywebview walks every public attribute of the bridge, and on Windows the
        # native form behind a window refers to itself without end (Point.Empty.Empty...), which never finishes

    def set_theme(self, dark):
        """The page changed between light and dark: the window's own chrome follows."""
        _style_window(self._window, bool(dark))
        return True

    def toggle_fullscreen(self):
        self._window.toggle_fullscreen()
        return True

    def save_files(self, files):
        """[{name, text} or {name, b64}] → saved in the Downloads folder (a browser download does not exist in a
        native window). Returns the paths written. Only the app's own export types, plain names and modest sizes:
        whatever runs in the page can never use this to drop a script or an app into the folder."""
        try:
            from platformdirs import user_downloads_dir

            folder = Path(user_downloads_dir())
        except Exception:  # noqa: BLE001
            folder = Path.home() / "Downloads"
        return _save_exports(folder, files)


SAVE_TYPES = {".docx", ".md", ".json", ".txt", ".csv"}
SAVE_MAX_BYTES = 50 * 1024 * 1024


def _safe_export_name(raw) -> str | None:
    """A plain file name with one of the export suffixes, or None. No folders, no hidden files, no other types."""
    name = "".join(c for c in str(raw) if c.isascii() and (c.isalnum() or c in "-_. ")).strip(" .")[:120]
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem or f".{ext.lower()}" not in SAVE_TYPES:
        return None
    return name


def _save_exports(folder: Path, files) -> list[str]:
    import base64

    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in list(files or [])[:10]:
        if not isinstance(f, dict):
            continue
        name = _safe_export_name(f.get("name", ""))
        if not name:
            continue
        data = base64.b64decode(f["b64"]) if f.get("b64") is not None else str(f.get("text", "")).encode("utf-8")
        if len(data) > SAVE_MAX_BYTES:
            continue
        path = folder / name
        stem, n = path.stem, 1
        while path.exists():
            n += 1
            path = folder / f"{stem}-{n}{path.suffix}"
        path.write_bytes(data)
        saved.append(str(path))
    return saved


DARK_BG, LIGHT_BG = "#0a0a0b", "#ffffff"


def _style_window(window, dark: bool) -> None:
    """Make the title bar part of the page: on macOS a transparent title bar over the page's own colour, the traffic
    lights kept and the title hidden; on Windows 10/11 a dark or light caption in the same colour. Best effort: the
    plain system title bar is what remains if any of this is unavailable."""
    if window is None:
        return
    hexbg = DARK_BG if dark else LIGHT_BG
    rgb = tuple(int(hexbg[i:i + 2], 16) for i in (1, 3, 5))
    if sys.platform == "darwin":
        try:
            import AppKit
            from PyObjCTools import AppHelper
        except ImportError:
            return

        def apply():
            w = window.native
            if w is None:
                return
            try:
                color = AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(*(c / 255 for c in rgb), 1.0)
                w.setTitlebarAppearsTransparent_(True)
                w.setTitleVisibility_(1)                 # NSWindowTitleHidden
                w.setBackgroundColor_(color)
                try:                                     # pywebview paints the title bar grey; paint it the page's colour
                    w.contentView().superview().subviews().lastObject().setBackgroundColor_(color)
                except Exception:  # noqa: BLE001
                    pass
                name = AppKit.NSAppearanceNameDarkAqua if dark else AppKit.NSAppearanceNameAqua
                w.setAppearance_(AppKit.NSAppearance.appearanceNamed_(name))
                print(f"bracket: window styled ({'dark' if dark else 'light'})", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"bracket: window styling skipped ({e})", flush=True)

        AppHelper.callAfter(apply)
    elif sys.platform == "win32":
        try:
            import ctypes

            hwnd = None
            try:
                hwnd = int(window.native.Handle.ToInt64())
            except Exception:  # noqa: BLE001
                hwnd = ctypes.windll.user32.FindWindowW(None, window.title)
            if not hwnd:
                return
            dwm = ctypes.windll.dwmapi
            on = ctypes.c_int(1 if dark else 0)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))        # immersive dark mode
            colorref = ctypes.c_int(rgb[0] | (rgb[1] << 8) | (rgb[2] << 16))
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))  # caption (Windows 11)
            print(f"bracket: window styled ({'dark' if dark else 'light'})", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"bracket: window styling skipped ({e})", flush=True)


def _app_window(url: str, server, thread: threading.Thread, server_app, check_after: float = 0) -> int | None:
    """bracket in its own window. Returns the exit code when the window closes, or None if no native window can be
    shown here (then the caller falls back to the browser)."""
    if sys.platform not in ("darwin", "win32"):
        return None
    try:
        import webview
    except ImportError:
        return None
    bridge = _Bridge()
    try:
        light = server_app.config.THEME == "light"   # open in the theme's colour: no dark flash before a light page
        window = webview.create_window("[bracket]", url, width=1440, height=920, min_size=(960, 640),
                                       background_color=LIGHT_BG if light else DARK_BG, text_select=True, js_api=bridge)
    except Exception as e:  # noqa: BLE001
        print(f"bracket: no app window ({e}); opening the browser", flush=True)
        return None
    bridge._window = window
    result = {"code": 0}

    def bring_forward():
        try:
            window.restore()
            window.show()
        except Exception:  # noqa: BLE001
            pass

    from backend import app as api_module

    api_module._focus_hook = bring_forward
    window.events.closed += lambda: setattr(server, "should_exit", True)
    window.events.shown += lambda: _style_window(window, not light)

    def watch():
        if check_after:
            result["code"] = _check_window(window, check_after)
            window.destroy()
            return
        while not server.should_exit and thread.is_alive():   # Quit in the page closes the window too
            time.sleep(0.4)
        try:
            window.destroy()
        except Exception:  # noqa: BLE001
            pass

    gui = "edgechromium" if sys.platform == "win32" else None   # never the old Internet Explorer engine
    try:
        webview.start(watch, gui=gui, private_mode=False, storage_path=str(server_app.config.DATA_DIR / "webview"))
    except Exception as e:  # noqa: BLE001 — e.g. WebView2 missing on an old Windows 10
        print(f"bracket: the app window could not start ({e}); opening the browser", flush=True)
        api_module._focus_hook = None
        if check_after:
            return 1
        return None
    server.should_exit = True
    return result["code"]


def _check_window(window, seconds: float) -> int:
    """For CI: the page loaded inside the window and the page→app bridge answers."""
    t0 = time.monotonic()
    last = None
    while time.monotonic() - t0 < max(seconds, 20):
        try:
            last = window.evaluate_js("[document.title, !!document.querySelector('#setup'), "
                                      "!!(window.pywebview && window.pywebview.api && window.pywebview.api.save_files)]")
            if last and last[1] and last[2]:
                print(f"WINDOW CHECK PASSED: {last}", flush=True)
                time.sleep(float(os.environ.get("BRACKET_WINDOW_HOLD", "0") or 0))   # CI: time to photograph it
                return 0
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(1)
    print(f"WINDOW CHECK FAILED: {last}", flush=True)
    return 1


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

    root.title("[bracket]")
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
