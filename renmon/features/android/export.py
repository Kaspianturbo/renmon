"""Export CSV using Android's document picker, without storage permissions."""

import threading


class CsvExport:
    def __init__(self):
        self._request_code = 5841
        self._error = None
        self._done = threading.Event()
        self._uri = None
        from android import activity

        activity.bind(on_activity_result=self._result)

    def _result(self, request, result, intent):
        if request == self._request_code:
            self._uri = intent.getData() if result == -1 and intent else None
            self._done.set()

    def save(self, content):
        from android.activity import _activity
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        self._request_code = 5841 + (self._request_code - 5840) % 50000
        request_code = self._request_code
        self._error = None
        self._done.clear()
        self._uri = None

        @run_on_ui_thread
        def choose():
            try:
                Intent = autoclass("android.content.Intent")
                intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
                intent.addCategory(Intent.CATEGORY_OPENABLE)
                intent.setType("text/csv")
                intent.putExtra(Intent.EXTRA_TITLE, "Renmon.csv")
                _activity.startActivityForResult(intent, request_code)
            except Exception as exc:
                self._error = str(exc)
                self._done.set()

        choose()
        if not self._done.wait(300):
            raise ValueError("Час вибору файлу вичерпано")
        if self._error:
            raise OSError("Не вдалося відкрити вибір файлу CSV")
        if self._uri is None:
            return False
        stream = None
        try:
            stream = _activity.getContentResolver().openOutputStream(self._uri, "wt")
            if stream is None:
                raise OSError("Не вдалося відкрити файл CSV")
            stream.write(bytearray(content.encode("utf-8-sig")))
            stream.flush()
        except Exception as exc:
            raise OSError("Не вдалося зберегти CSV") from exc
        finally:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
        return True
