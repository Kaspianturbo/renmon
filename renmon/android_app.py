"""Android entry point: local HTML + Python bridge; no HTTP listener."""

import logging
from pathlib import Path


def main():
    import webview
    from android.activity import _activity, register_activity_lifecycle_callbacks
    from android.runnable import run_on_ui_thread

    from .features.android.bluetooth import BluetoothDevices
    from .features.android.bridge import AndroidAPI
    from .features.android.export import CsvExport
    from .features.android.lifecycle import AndroidSession
    from .features.connection.service import Connection
    from .features.desktop.assets import document
    from .features.ecu.profile import Profile
    from .features.monitoring.service import Monitor

    root = Path(__file__).resolve().parent.parent
    logs = Path(str(_activity.getFilesDir().getAbsolutePath())) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=logs / "android.log", encoding="utf-8", level=logging.INFO
    )
    devices = BluetoothDevices()
    monitor = Monitor(
        Profile.load(root / "profiles/11075.json"),
        logs,
        root / "profiles",
        connection=Connection(transport_factory=devices.open),
        port_provider=devices.ports,
    )
    session = AndroidSession(monitor)
    exporter = CsvExport()
    api = AndroidAPI(session, devices, exporter.save)

    def destroy(*_args):
        # Android must not wait for adapter cleanup on its main thread.
        import threading

        threading.Thread(target=session.close, daemon=True).start()

    register_activity_lifecycle_callbacks(
        onActivityPaused=session.pause,
        onActivityResumed=session.resume,
        onActivityDestroyed=destroy,
    )
    webview.settings["ALLOW_DOWNLOADS"] = False
    webview.settings["ALLOW_FILE_URLS"] = False
    window = webview.create_window(
        "Renmon", html=document(), js_api=api, background_color="#101410"
    )

    @run_on_ui_thread
    def secure_view():
        settings = window.native.webview.getSettings()
        settings.setAllowFileAccess(False)
        settings.setAllowFileAccessFromFileURLs(False)
        settings.setAllowUniversalAccessFromFileURLs(False)
        settings.setUseWideViewPort(True)
        settings.setTextZoom(100)

    window.events.shown += secure_view
    try:
        webview.start(gui="android", http_server=False, private_mode=False)
    finally:
        session.close()


if __name__ == "__main__":
    main()
