import serial
import serial.tools.list_ports
import time


def detect_keithley_devices(baudrate: int | None = 9600, timeout=0.5, verbose=False):
    """
    Scans all available serial ports and attempts to identify Keithley 6514 instruments.

    If baudrate is None, tries a list of common baudrates for each port.

    Returns:
        list: A list of dictionaries containing port info, IDN strings, and baudrate used.
    """
    found_devices = []
    ports = serial.tools.list_ports.comports()

    common_baudrates = [9600, 19200, 38400, 57600, 115200]

    for port in ports:
        baudrate_list = [baudrate] if baudrate is not None else common_baudrates
        for br in baudrate_list:
            try:
                with serial.Serial(port.device, baudrate=br, timeout=timeout) as ser:
                    ser.write(b"*IDN?\n")
                    time.sleep(0.1)
                    response = ser.readline().decode(errors="ignore").strip()

                    if response:
                        found_devices.append(
                            {
                                "port": port.device,
                                "description": port.description,
                                "idn": response,
                                "baudrate": br,
                                "is_keithley": "KEITHLEY" in response.upper(),
                                "status": "response",
                            }
                        )
                        break
                    else:
                        found_devices.append(
                            {
                                "port": port.device,
                                "description": port.description,
                                "idn": "No response to *IDN?",
                                "baudrate": br,
                                "is_keithley": False,
                                "status": "no_idn",
                            }
                        )
                        break
            except Exception:  # Broad catch to handle any serial exceptions (port busy, permission issues, etc.)
                found_devices.append(
                    {
                        "port": port.device,
                        "description": port.description,
                        "idn": "Port busy or cannot open",
                        "baudrate": br,
                        "is_keithley": False,
                        "status": "busy",
                    }
                )
                break

    if verbose:
        print_keithley_devices(found_devices)
    return found_devices


def print_keithley_devices(devices):
    """Formats and prints the detected serial devices to the console."""
    if not devices:
        print("*** No serial devices detected on available serial ports ***")
        print("Please check your connections and try again.\n")
        return

    print("=" * 100)
    print(f"{'Port':<12} | {'Baudrate':<8} | {'Status':<10} | {'Identification (IDN)'}")
    print("-" * 100)
    for dev in devices:
        if dev["status"] == "response":
            status = "[✓] KEITHLEY" if dev["is_keithley"] else "[?] Response"
        elif dev["status"] == "no_idn":
            status = "[ ] No IDN"
        elif dev["status"] == "busy":
            status = "[!] Busy"
        elif dev["status"] == "decode_error":
            status = "[!] DecodeErr"
        else:
            status = "[?] Unknown"
        baudrate = dev.get("baudrate", "?")
        print(f"{dev['port']:<12} | {baudrate:<8} | {status:<10} | {dev['idn']}")
    print("=" * 100, "\n")


def scpi_query(cmd, dev, verbose=False):
    """Sends a SCPI command to the specified device and returns the response."""
    try:
        with serial.Serial(dev["port"], baudrate=dev["baudrate"], timeout=0.5) as ser:
            if verbose:
                print(f"[COMMAND]: {cmd}")
            ser.write(f"{cmd}\n".encode())
            time.sleep(0.1)
            response = ser.readline().decode(errors="ignore").strip()
            if response is None or response == "":
                response = f"No response to {cmd}"
            if verbose:
                print(f"[RESPONSE]: {response}")
            return response
    except serial.SerialException as e:
        if verbose:
            print(f"Error communicating with device on {dev['port']}: {e}")
        return None


if __name__ == "__main__":
    devs = detect_keithley_devices(baudrate=None, verbose=True)

    for dev in devs:
        if dev["is_keithley"]:
            scpi_query(":CONF?", dev, verbose=True)
            read_res = scpi_query(":READ?", dev, verbose=True)
            print("Measurement:", read_res)

            scpi_query(":SENS:CURR:RANG?", dev, verbose=True)
            scpi_query(":READ?", dev, verbose=True)
