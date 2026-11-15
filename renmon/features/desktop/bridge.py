"""The sole JS entry point. No raw commands, paths, transport or Python objects."""

import json
import threading

from ..history.export import export_csv


class DesktopAPI:
    def __init__(self, session, save_csv):
        self._session = session
        self._save_csv = save_csv
        self._export_lock = threading.Lock()

    def call(self, action, data=None):
        try:
            if not isinstance(action, str) or (
                data is not None and not isinstance(data, dict)
            ):
                raise ValueError("Некоректний запит")
            if len(json.dumps(data, allow_nan=False).encode()) > 8192:
                raise ValueError("Запит завеликий")
            self._session.ensure_open()
            monitor = self._session.monitor
            config = data or {}
            if action == "state":
                self._session.heartbeat()
                result = monitor.snapshot()
            elif action == "catalog":
                result = {
                    **monitor.catalog_snapshot(),
                    "ports": monitor.port_provider(),
                }
            elif action == "ports":
                result = {"ports": monitor.port_provider()}
            elif action == "export":
                if not self._export_lock.acquire(blocking=False):
                    raise ValueError("Діалог збереження вже відкритий")
                try:
                    result = {"saved": self._save_csv(export_csv(monitor.snapshot()))}
                finally:
                    self._export_lock.release()
            else:
                actions = {
                    "start": monitor.start,
                    "stop": lambda _: monitor.stop(),
                    "profile": monitor.change_profile,
                    "detect": monitor.detect,
                    "signals": monitor.update_codes,
                    "cadence": monitor.update_divisor,
                    "adapter": monitor.select_adapter,
                }
                if action not in actions:
                    raise ValueError("Невідома дія")
                actions[action](config)
                result = {"ok": True}
            return {"ok": True, "result": result}
        except (ValueError, KeyError, TypeError, OSError) as exc:
            return {"ok": False, "error": str(exc)}
