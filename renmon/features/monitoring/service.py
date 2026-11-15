"""Monitoring use cases independent of the native desktop bridge.

State lock protects short in-memory transitions only. Serial I/O uses the
connection lock; no serial operation is performed while holding the state lock.
"""

import threading
import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path

from renmon.elm import ElmError

from ..connection.ports import ports
from ..connection.service import Connection
from ..ecu.catalog import Catalog
from ..history.store import Store
from .cadence import Cadence, divisor, divisors
from .performance import Performance
from .requests import MAX_SIGNALS, StartRequest, selected_codes, session_request
from .sources import DemoReader, LiveReader

ROOT = Path(__file__).resolve().parents[3]


class Monitor:
    def __init__(
        self,
        profile,
        log_dir=None,
        profile_dir=None,
        *,
        connection=None,
        port_provider=None,
    ):
        self.log_dir = Path(log_dir) if log_dir is not None else ROOT / "logs"
        self.catalog = Catalog(profile_dir or ROOT / "profiles")
        self.connection = connection if connection is not None else Connection()
        self.port_provider = port_provider if port_provider is not None else ports
        self.profile = profile
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.operation = None
        self.closed = False
        self.samples = deque(maxlen=3600)
        self.status = "idle"
        self.error = ""
        self.mode = "demo"
        self.codes = []
        self.divisors = {}
        self.started = None
        self.interval = 1.0
        self.performance = Performance(profile.did_lengths).snapshot()
        self.log_path = None
        self.heartbeat = time.monotonic()
        self.identification = "ECU ще не визначено"

    def _require_idle(self):
        if self.closed:
            raise ValueError("Застосунок закривається")
        if self.operation or (self.thread and self.thread.is_alive()):
            raise ValueError(
                "Спочатку зупиніть поточний сеанс або дочекайтеся завершення операції"
            )

    @contextmanager
    def _idle_operation(self, name):
        with self.lock:
            self._require_idle()
            self.operation = name
            if name == "detect":
                self.stop_event.clear()
        try:
            yield
        finally:
            with self.lock:
                self.operation = None

    def start(self, config):
        request = StartRequest.parse(config)
        if request.mode == "live" and request.port not in self.port_provider():
            raise ValueError("Оберіть доступний локальний serial-порт")
        with self.lock:
            self._require_idle()
            self.profile.by_code(list(request.codes))
            self.samples.clear()
            self.mode, self.codes = request.mode, list(request.codes)
            self.divisors = request.divisors
            self.interval = request.interval
            self.performance = Performance(
                self.profile.did_lengths, request.performance
            ).snapshot()
            self.started = time.time()
            self.status, self.error = "connecting", ""
            self.log_path = None
            self.heartbeat = time.monotonic()
            self.stop_event.clear()
            self.thread = threading.Thread(
                target=self._run,
                args=(request, self.profile),
                name="Renmon monitoring",
                daemon=True,
            )
            self.thread.start()

    def _run(self, request, profile):
        store = None
        try:
            if request.mode == "live":
                self.connection.begin(request.port)
            else:
                self.connection.select("")
            reader = (
                LiveReader(
                    self.connection,
                    profile,
                    self.catalog,
                    request.session,
                    request.performance,
                )
                if request.mode == "live"
                else DemoReader()
            )
            path = self.log_dir / f"{request.mode}-{time.time_ns()}.sqlite"
            store = Store(path)
            store.start_session(
                profile.ecu,
                profile.doc,
                f"{request.mode}; session={request.session or 'default'}; performance={request.performance}",
            )
            with self.lock:
                self.log_path = str(path)
            described = None
            failures = 0
            cadence = Cadence()
            generation = self.connection.generation
            while not self.stop_event.is_set():
                with self.lock:
                    if (
                        request.mode == "live"
                        and time.monotonic() - self.heartbeat > 15
                    ):
                        raise RuntimeError(
                            "Інтерфейс не відповідає понад 15 с. Опитування зупинено."
                        )
                    codes = tuple(self.codes)
                    modifiers = dict(self.divisors)
                signals = profile.by_code(list(codes))
                if codes != described:
                    store.describe(signals)
                    described = codes
                if generation != self.connection.generation:
                    cadence = Cadence()
                    generation = self.connection.generation
                signals = cadence.due(signals, modifiers)
                began = time.monotonic()
                reading = reader.cycle(signals, self.stop_event)
                if self.stop_event.is_set():
                    break
                if reading is None:
                    with self.lock:
                        self.status = "connecting"
                    self.stop_event.wait(0.1)
                    continue
                cadence.advance(signals)
                at = time.time()
                store.record(
                    (
                        (s.code, reading.values.get(s.code), reading.errors.get(s.code))
                        for s in signals
                    ),
                    at=at,
                )
                with self.lock:
                    self.status = "running"
                    if request.mode == "live":
                        self.performance = reader.performance.snapshot()
                    self.samples.append(
                        dict(
                            at=at,
                            values=reading.values,
                            errors=reading.errors,
                            elapsed=reading.elapsed,
                            requests=reading.requests,
                            dids=len({s.request for s in signals}),
                        )
                    )
                if signals:
                    failures = failures + 1 if not reading.values else 0
                if failures >= 3:
                    raise RuntimeError(
                        "Три цикли без даних. Опитування зупинено; перевірте адаптер, профіль і сесію."
                    )
                self.stop_event.wait(
                    max(0, request.interval - (time.monotonic() - began))
                )
        except Exception as exc:
            with self.lock:
                if not self.stop_event.is_set():
                    self.error = str(exc)
        finally:
            try:
                if store:
                    store.close()
            finally:
                self.connection.finish()
                with self.lock:
                    self.status = "error" if self.error else "stopped"

    def _set_profile(self, profile):
        # Caller owns the state lock and has reserved an idle operation.
        self.profile = profile
        self.codes = []
        self.divisors = {}
        self.samples.clear()
        self.log_path = None
        self.started = None
        self.error = ""
        self.status = "idle"
        self.performance = Performance(profile.did_lengths).snapshot()

    def change_profile(self, config):
        with self._idle_operation("profile"):
            profile = self.catalog.load(config.get("ecu"))
            with self.lock:
                self._set_profile(profile)
                self.identification = (
                    "Профіль обрано вручну; ECU буде перевірено перед читанням"
                )

    def detect(self, config):
        session = session_request(config.get("session", ""))
        with self._idle_operation("detect"):
            try:
                self.connection.begin(self.connection.target)
                with self.connection.lock:
                    if (
                        self.connection.status != "connected"
                        or self.connection.elm is None
                    ):
                        raise ValueError(
                            "Спочатку оберіть порт і дочекайтеся підключення ELM"
                        )
                    elm = self.connection.elm
                    elm.connect("7E0", "7E8", stop=self.stop_event)
                    if self.stop_event.is_set():
                        raise ValueError("Визначення ECU скасовано")
                    if session:
                        elm.start_session(session)
                    if self.stop_event.is_set():
                        raise ValueError("Визначення ECU скасовано")
                    entry = self.catalog.verify(elm)
                    profile = self.catalog.load(entry["ecu"])
                    self.connection.last_activity = time.monotonic()
                with self.lock:
                    if not self.stop_event.is_set():
                        self._set_profile(profile)
                        self.identification = f"Визначено ECU {entry['ecu']}"
            except (ValueError, ElmError, OSError) as exc:
                with self.lock:
                    self.identification = str(exc)
                raise ValueError(str(exc)) from exc
            finally:
                self.connection.finish()

    def update_codes(self, config):
        codes = selected_codes(config.get("codes"), allow_empty=True)
        with self.lock:
            if self.operation or self.closed:
                raise ValueError("Дочекайтеся завершення операції")
            self.profile.by_code(list(codes))
            modifiers = divisors(
                config.get("divisors", {c: self.divisors.get(c, 1) for c in codes}),
                codes,
            )
            self.codes = list(codes)
            self.divisors = modifiers

    def update_divisor(self, config):
        code, value = config.get("code"), divisor(config.get("divisor"))
        with self.lock:
            if self.operation or self.closed or code not in self.codes:
                raise ValueError("Параметр не відстежується")
            self.divisors[code] = value

    def select_adapter(self, config):
        target = config.get("port", "")
        auto_connect = config.get("auto_connect", False)
        if type(auto_connect) is not bool:
            raise ValueError("auto_connect має бути true або false")
        if not isinstance(target, str) or (
            target and target not in self.port_provider()
        ):
            raise ValueError("Недоступний serial-порт")
        with self.lock:
            if (
                self.thread
                and self.thread.is_alive()
                and target == self.connection.target
                and auto_connect == self.connection.auto_connect
            ):
                return
        with self._idle_operation("adapter"):
            self.connection.select(target, auto_connect)
            with self.lock:
                self.identification = "ECU ще не визначено"

    def stop(self):
        self.stop_event.set()
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.status = "stopping"

    def touch(self):
        with self.lock:
            self.heartbeat = time.monotonic()

    def catalog_snapshot(self):
        with self.lock:
            profile = self.profile
            return dict(
                ecu=profile.ecu,
                doc=profile.doc,
                tx=profile.tx_id,
                rx=profile.rx_id,
                profiles=self.catalog.entries,
                identification=self.identification,
                max_signals=MAX_SIGNALS,
                signals=[
                    dict(
                        code=s.code,
                        label=s.label,
                        label_uk=s.label_uk,
                        unit=s.unit,
                        kind=s.kind,
                        request=s.request,
                        interpretations=s.interpretations,
                    )
                    for s in profile.signals
                ],
            )

    def snapshot(self):
        with self.lock:
            performance = dict(self.performance)
            if self.mode == "demo":
                performance["status"] = "demo"
            return dict(
                status=self.status,
                error=self.error,
                mode=self.mode,
                codes=list(self.codes),
                divisors=dict(self.divisors),
                operation=self.operation,
                performance=performance,
                ecu=self.profile.ecu,
                identification=self.identification,
                started=self.started,
                interval=self.interval,
                log_path=self.log_path,
                samples=list(self.samples),
                connection=self.connection.snapshot(),
            )

    def close(self):
        with self.lock:
            self.closed = True
        self.connection.request_close()
        self.stop()
        if self.thread:
            self.thread.join()
        self.connection.close()
