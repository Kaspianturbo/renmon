"""Paired Bluetooth Classic SPP devices only: no discovery, BLE or ECU commands."""

import re
import threading
import time

SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"
_ADDRESS = re.compile(r"[0-9A-F]{2}(?::[0-9A-F]{2}){5}")


def address_from_target(target):
    address = target.rsplit(" · ", 1)[-1]
    if not _ADDRESS.fullmatch(address):
        raise ValueError("Некоректна адреса Bluetooth")
    return address


class BluetoothDevices:
    def __init__(self):
        self._permission_pending = False

    def adapter(self, *, request=False):
        from android.permissions import check_permission, request_permissions
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        version = autoclass("android.os.Build$VERSION").SDK_INT
        permission = "android.permission.BLUETOOTH_CONNECT"
        if version >= 31 and not check_permission(permission):
            if request and not self._permission_pending:
                self._permission_pending = True

                def completed(_permissions, _grants):
                    self._permission_pending = False

                @run_on_ui_thread
                def ask():
                    request_permissions([permission], completed)

                ask()
            raise ValueError(
                "Надайте дозвіл «Пристрої поблизу» та відкрийте список ELM повторно."
            )
        adapter = autoclass("android.bluetooth.BluetoothAdapter").getDefaultAdapter()
        if adapter is None:
            raise ValueError("Телефон не підтримує Bluetooth")
        if not adapter.isEnabled():
            raise ValueError("Увімкніть Bluetooth у налаштуваннях телефону")
        return adapter

    def ports(self, *, request=False):
        try:
            devices = self.adapter(request=request).getBondedDevices().toArray()
            return sorted(
                f"{device.getName() or 'ELM'} · {device.getAddress()}"
                for device in devices
                if device.getType() != 2  # TYPE_LE; BLE is not a serial SPP link.
            )
        except ValueError:
            if request:
                raise
            return []
        except Exception as exc:
            if request:
                raise ValueError(
                    "Не вдалося прочитати спарені Bluetooth-пристрої"
                ) from exc
            return []

    def open(self, target, **_options):
        if target not in self.ports(request=True):
            raise ValueError("Спочатку спарте ELM у налаштуваннях Bluetooth телефону")
        from jnius import autoclass

        device = self.adapter().getRemoteDevice(address_from_target(target))
        uuid = autoclass("java.util.UUID").fromString(SPP_UUID)
        return BluetoothTransport(device.createRfcommSocketToServiceRecord(uuid))


class BluetoothTransport:
    def __init__(self, socket, connect_timeout=10.0, read_timeout=0.1):
        self.socket = socket
        self.closed = threading.Event()
        self.read_timeout = read_timeout
        timer = threading.Timer(connect_timeout, self.interrupt)
        timer.daemon = True
        timer.start()
        try:
            socket.connect()
            if self.closed.is_set():
                raise OSError("Bluetooth: час підключення вичерпано")
            self.input = socket.getInputStream()
            self.output = socket.getOutputStream()
        except Exception as exc:
            self.interrupt()
            raise OSError("Не вдалося підключитися до ELM через Bluetooth") from exc
        finally:
            timer.cancel()

    def write(self, data):
        if self.closed.is_set():
            raise OSError("Bluetooth від’єднано")
        # Bound writes too: closing BluetoothSocket interrupts blocked Java I/O.
        timer = threading.Timer(5.0, self.interrupt)
        timer.daemon = True
        timer.start()
        try:
            self.output.write(bytearray(data))
            self.output.flush()
        except Exception as exc:
            raise OSError("Bluetooth: помилка надсилання") from exc
        finally:
            timer.cancel()

    def read(self, size=1):
        deadline = time.monotonic() + self.read_timeout
        try:
            while not self.closed.is_set():
                available = self.input.available()
                if available:
                    data = bytearray()
                    for _ in range(min(size, available)):
                        value = self.input.read()
                        if value < 0:
                            raise OSError("Bluetooth від’єднано")
                        data.append(value)
                    return bytes(data)
                if time.monotonic() >= deadline:
                    return b""
                self.closed.wait(0.005)
            raise OSError("Bluetooth від’єднано")
        except Exception as exc:
            raise OSError("Bluetooth: помилка читання") from exc

    def reset_input(self):
        try:
            # Drain only what is already buffered; never loop on a noisy device.
            self.input.skip(min(self.input.available(), 65536))
        except Exception as exc:
            raise OSError("Bluetooth: помилка буфера") from exc

    def interrupt(self):
        if not self.closed.is_set():
            self.closed.set()
            try:
                self.socket.close()
            except Exception:
                pass

    close = interrupt
