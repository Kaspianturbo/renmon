import Foundation
import IOBluetooth

// Only reconnect an already paired device whose name matches the selected port.
// No inquiry, pairing, PIN storage, disconnection, or ECU communication.
func finish(_ state: String, _ detail: String = "") -> Never {
    let data = try! JSONSerialization.data(withJSONObject: ["state":state, "detail":detail])
    print(String(data:data,encoding:.utf8)!)
    exit(0)
}
guard CommandLine.arguments.count == 2 else { finish("error", "Port required") }
let port = CommandLine.arguments[1]
guard port.hasPrefix("/dev/cu.") else { finish("not_bluetooth") }
let name = String(port.dropFirst("/dev/cu.".count))
let paired = IOBluetoothDevice.pairedDevices() as? [IOBluetoothDevice] ?? []
let matches = paired.filter { $0.name == name }
guard matches.count == 1 else { finish("not_bluetooth", "No unique paired device matching port name") }
let device = matches[0]
if device.isConnected() { finish("connected") }
// Bluetooth page timeout uses 0.625 ms slots: 1600 = 1 second.
let result = device.openConnection(nil, withPageTimeout: 1600, authenticationRequired: false)
if device.isConnected() { finish("connected") }
finish("waiting", "macOS Bluetooth openConnection: \(result)")
