"""Mobile-specific metadata and permission entry, reusing the restricted bridge."""

from ..desktop.bridge import DesktopAPI


class AndroidAPI(DesktopAPI):
    def __init__(self, session, devices, save_csv):
        super().__init__(session, save_csv)
        self._devices = devices

    def call(self, action, data=None):
        with self._session.operation_lock:
            return self._call(action, data)

    def _call(self, action, data=None):
        if action == "ports":
            try:
                self._session.ensure_open()
                return {
                    "ok": True,
                    "result": {"ports": self._devices.ports(request=True)},
                }
            except (ValueError, OSError) as exc:
                return {"ok": False, "error": str(exc)}
        result = super().call(action, data)
        if action == "catalog" and result.get("ok"):
            result["result"]["platform"] = "android"
        return result
