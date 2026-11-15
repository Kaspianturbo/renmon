"""Portable pywebview shell. No diagnostic commands are exposed to JavaScript."""

from __future__ import annotations

import ctypes
import logging
import sys
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

WEBVIEW2_URL = (
    "https://developer.microsoft.com/microsoft-edge/webview2/#download-section"
)
WEBVIEW2_KEY = (
    r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
)


def has_webview2():
    """Detect Evergreen Runtime in both per-user and machine registry views."""
    import winreg

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(
                    hive, WEBVIEW2_KEY, 0, winreg.KEY_READ | view
                ) as key:
                    value, _ = winreg.QueryValueEx(key, "pv")
                version = tuple(int(part) for part in value.split("."))
                if len(version) == 4 and version > (0, 0, 0, 0):
                    return True
            except (OSError, ValueError, AttributeError):
                continue
    return False


def windows_message(title, message, flags=0x10):
    # Native Win32 dialog works even if WebView2 or Python.NET cannot load.
    message_box = ctypes.windll.user32.MessageBoxW
    message_box.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
    ]
    message_box.restype = ctypes.c_int
    return message_box(None, message, title, flags)


def check_runtime():
    if sys.platform != "win32" or has_webview2():
        return True
    message = (
        "Microsoft Edge WebView2 Runtime не встановлено.\n\n"
        "Для запуску Renmon встановіть Evergreen Runtime із сайту Microsoft:\n"
        f"{WEBVIEW2_URL}\n\n"
        "Після встановлення запустіть Renmon знову.\n"
        "Відкрити сторінку завантаження?"
    )
    if windows_message("Renmon — потрібен WebView2", message, 0x34) == 6:  # Yes/No
        webbrowser.open(WEBVIEW2_URL)
    return False


def portable_root():
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent
    executable = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for parent in executable.parents:
            if parent.suffix == ".app":
                return parent.parent
    return executable.parent


def show_error(message):
    logging.error("%s", message)
    if sys.platform == "win32":
        windows_message("Renmon — помилка запуску", message)
    elif sys.platform == "darwin":
        from AppKit import NSAlert, NSApplication

        NSApplication.sharedApplication()
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Renmon — помилка запуску")
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("OK")
        alert.runModal()


def main():
    backend = None
    try:
        if not check_runtime():
            return 1
        import webview

        root = portable_root()
        profile = root / "profiles" / "11075.json"
        if not profile.is_file():
            raise FileNotFoundError(
                f"Не знайдено {profile}.\nЗбережіть папку profiles поруч із Renmon."
            )
        logs = root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            handlers=[
                RotatingFileHandler(
                    logs / "desktop.log",
                    maxBytes=2_000_000,
                    backupCount=3,
                    encoding="utf-8",
                )
            ],
            level=logging.INFO,
            force=True,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        from .features.desktop.assets import document
        from .features.desktop.bridge import DesktopAPI
        from .features.desktop.dialogs import save_csv
        from .features.desktop.lifecycle import DesktopSession
        from .features.ecu.profile import Profile
        from .features.monitoring.service import Monitor

        backend = DesktopSession(Monitor(Profile.load(profile), logs, profile.parent))

        api = DesktopAPI(backend, lambda content: save_csv(window, content))
        webview.settings["ALLOW_DOWNLOADS"] = False
        webview.settings["ALLOW_FILE_URLS"] = False
        window = webview.create_window(
            "Renmon",
            html=document(),
            js_api=api,
            width=1280,
            height=850,
            min_size=(800, 600),
            background_color="#101410",
        )
        window.events.closed += backend.close
        # Force the modern engine: never silently fall back to Internet Explorer.
        webview.start(
            gui="edgechromium" if sys.platform == "win32" else "cocoa",
            private_mode=False,
            http_server=False,
        )
        return 0
    except Exception as exc:
        logging.exception("Desktop startup failed")
        show_error(f"Не вдалося запустити Renmon.\n\n{exc}")
        return 1
    finally:
        if backend is not None:
            backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
