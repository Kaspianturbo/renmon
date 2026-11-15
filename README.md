# Renmon

Portable desktop monitor for Renault Laguna III / X91 ECUs, using Python and PyWebView. The HTML/CSS/JS interface talks directly to Python through a restricted native bridge. **There is no HTTP server, localhost UI, or browser launch mode.**

## Run

Open `Renmon.app` on macOS or `Renmon.exe` on Windows. Keep the adjacent `profiles` directory and, on Windows, `_internal`. Extract into a writable folder. Ready builds contain Python; Windows also needs WebView2 Evergreen Runtime. A native dialog links to Microsoft's download page if it is absent.

From source:

```sh
python -m pip install -e '.[desktop]'
npm ci
npm run build
python -m renmon.desktop
```

`Start-Renmon.cmd` installs Python dependencies and builds the UI on first launch. Running from source requires Python and Node.js. Portable builds include the generated UI.

## Monitoring

Demo requires no adapter. For live reading, pair a Bluetooth Classic SPP ELM in OS settings, then select its outgoing COM port (Windows) or `/dev/cu.*` port (macOS). BLE-only devices without serial ports are unsupported.

Selecting a port alone does not connect. Autoconnect is opt-in: when checked, Renmon retries every 3 seconds and maintains the idle adapter link. Without it, Start or Detect profile opens the port once; Stop releases it. The macOS Bluetooth helper is used with autoconnect when it has been built.

Choose an ECU profile and select 1–10 parameters, then Start. Parameters can be added/removed during reading, including temporarily selecting none. Chart membership is independent: hiding a chart series does not stop reading the sensor. Tiles support ordering and fullscreen. State parameters use CLIP enumeration labels, not arbitrary booleans. Performance optionally groups up to three validated DIDs and falls back to individual reads on a rejected/malformed response.

Intervals are 0.1–10 seconds. Requests are serialized, without queued catch-up cycles. The UI displays measured read time and warns when it exceeds the cycle budget. Logs are SQLite files next to the application; CSV uses a native Save dialog.

## Closing and safety

Closing the native window stops monitoring and autoconnect, waits for pending I/O and releases the serial port. An independent watchdog does the same after more than 15 seconds without UI heartbeat, including when only autoconnect was running. A lost session cannot resume without restarting Renmon. Stop alone retains an idle link only when autoconnect is checked.

The transport allowlist permits explicit adapter setup, session/keepalive requests, exact `2180` identification and `22` reads. No ECU data writes, routine execution, fault clearing or address scanning are exposed. The desktop UI uses the default diagnostic state without requesting a session change. Live desktop reads verify the profile against the installed X91 catalog before polling.

## CLI and offline tools

```sh
renmon list profiles/11075.json -f pressure
renmon monitor profiles/11075.json -p /dev/cu.V-LINK -c PR064 PR383 --db readings.sqlite
renmon history PR383 --db readings.sqlite
renmon sessions --db readings.sqlite
renmon probe profiles/11075.json -p /dev/cu.V-LINK -c PR900 PR383
```

CLI monitor/probe are manual diagnostic tools with an explicitly chosen profile, not a second UI client. They retain the command allowlist but do not perform the desktop's automatic 2180 profile verification. Offline `renmon extract` and `tools/inventory_x91.py` read local CLIP files; the runtime needs only extracted profiles, not Pyren/DDT.

## Development and portable builds

```sh
python -m pip install -e '.[desktop,dev,build]'
npm ci
npm run build
python tools/check.py
python packaging/build_portable.py
```

Build on the target OS; `Build-Windows.cmd` prepares Windows dependencies. The macOS portable build compiles the Bluetooth helper from Swift using Xcode or the Command Line Tools. Source JS remains modular; esbuild produces a single local script, then the desktop embeds it with CSS into an HTML string. The quality check rejects stale bundles.

macOS builds target Apple Silicon and use ad-hoc signing, without Developer ID notarization. Windows hardware and real ECU behavior after changes still require physical verification. POSIX PTY tests run on macOS/Linux; Windows uses in-memory adapter tests.

Architecture and dependencies: [ARCHITECTURE.uk.md](docs/ARCHITECTURE.uk.md).

## Android preview

An experimental Android 8.0+ arm64 APK can be built with Buildozer. It shares the read-only monitoring core and responsive UI, adds paired Bluetooth Classic SPP devices, and stops communication when backgrounded. See [Android build and test instructions](docs/ANDROID.uk.md). The APK has not yet been run on a physical phone/ELM.
