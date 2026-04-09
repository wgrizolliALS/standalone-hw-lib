import serial
import serial.tools.list_ports
import time
from datetime import datetime


def _colorStr(s, color=None, bold=False):
    color_codes = {
        "red": "91",
        "green": "92",
        "blue": "94",
        "purple": "95",
        "cyan": "96",
    }

    color_code = color_codes.get(color, "")  # type: ignore
    bold_code = "1;" if bold else ""
    return f"\033[{bold_code}{color_code}m{s}\033[0m"


def print_verbose(msg, verbose=True, timestamp=False, color_messages=False, color=None, bold=False):
    if verbose:
        if timestamp:
            msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] : {msg}"
        if color_messages:
            msg = _colorStr(msg, color=color, bold=bold)
        print(msg)


def serial_query(
    cmd: str,
    port: str,
    baudrate: int = 9600,
    wait_serial=False,
    color_messages=True,
    verbose: bool = False,
    debug: bool = False,
) -> str | None:
    """Sends a string to serial port and returns the response."""
    print_verbose(f"[DEBUG] : Attempting to open serial port {port} at baudrate {baudrate}", debug)

    try:
        with serial.Serial(port, baudrate=baudrate, timeout=0.5) as ser:
            print_verbose(
                f"[COMMAND] = {cmd}", verbose, timestamp=True, color_messages=color_messages, color="cyan", bold=True
            )
            ser.write(f"{cmd}\n".encode())

            _time_init = time.time()
            while wait_serial and ser.in_waiting == 0:
                time.sleep(0.25)
                print_verbose(f"[DEBUG] : Waiting for response from {cmd}...", debug, timestamp=True)

                if time.time() - _time_init >= 5 * ser.timeout:  # type: ignore
                    raise TimeoutError(f"Timeout waiting for response to {cmd} on {port}")

            response = ser.readline().decode(errors="ignore").strip()

        if response == "":
            print_verbose(
                "[RESPONSE] = [EMPTY PORT]",
                verbose,
                timestamp=True,
                color_messages=color_messages,
                color="red",
                bold=True,
            )
            response = None
        else:
            print_verbose(
                f"[RESPONSE] = {response}",
                verbose,
                timestamp=True,
                color_messages=color_messages,
                color="green",
                bold=True,
            )

        print_verbose(f"[DEBUG] : {type(response) = }", debug, timestamp=True)

        return response

    except serial.SerialException as e:
        print_verbose(
            f"[ERROR] : Error communicating with device on {port}: {e}",
            verbose,
            timestamp=True,
            color_messages=color_messages,
            color="red",
            bold=True,
        )
        return None
    except TimeoutError as e:
        print_verbose(f"[ERROR] : {e}", verbose, timestamp=True, color_messages=color_messages, color="red", bold=True)
        return None
    except Exception as e:
        print_verbose(
            f"[ERROR] : Unexpected error on {port}: {e}",
            verbose,
            timestamp=True,
            color_messages=color_messages,
            color="red",
            bold=True,
        )
        return None


def detect_keithley_devices(baudrate: int | None = 9600, timeout=0.5, verbose=False, debug=False) -> list[dict] | None:
    """
    Scans all available serial ports and attempts to identify Keithley 6514 instruments.

    If baudrate is None, tries a list of common baudrates for each port.

    Returns:
        list: A list of dictionaries containing port info, IDN strings, and baudrate used.
    """
    found_devices = []
    ports = serial.tools.list_ports.comports()
    print_verbose(f"[INFO] Detected {len(ports)} serial ports to scan.", debug, timestamp=True)
    print_verbose(f"[DEBUG] : {ports = }", debug)

    common_baudrates = [9600, 19200, 38400, 57600, 115200]

    print_verbose("[DEBUG] : Loop ports and baudrates", debug)
    for port in ports:
        baudrate_list = [baudrate] if baudrate is not None else common_baudrates

        print_verbose(f"[DEBUG] : {port.device = }", debug)
        for br in baudrate_list:
            try:
                # with serial.Serial(port.device, baudrate=br, timeout=timeout) as ser:
                # ser.write(b"*IDN?\n")
                # time.sleep(0.1)
                # response = ser.readline().decode(errors="ignore").strip()
                response = serial_query("*IDN?", port.device, baudrate=br, verbose=verbose, debug=debug)

                if response:
                    _mnfctr, _model, _sn, _frmwr = response.split(",")
                    found_devices.append(
                        {
                            "port": port.device,
                            "description": port.description,
                            "idn": response,
                            "manufacturer": _mnfctr,
                            "model": _model,
                            "serial_number": _sn,
                            "firmware": _frmwr,
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
    return found_devices if found_devices else None


def print_keithley_devices(devices):
    """Formats and prints the detected serial devices to the console."""
    if not devices:
        print_verbose("[INFO] *** No serial devices detected on available serial ports ***", timestamp=True)
        print_verbose("[INFO] Please check your connections and try again.\n", timestamp=True)
        return

    print_verbose(f"[INFO] #### FOUND {len(devices)} SERIAL DEVICES ####", timestamp=True)
    _n_keithleys = sum(1 for d in devices if d["is_keithley"])
    print_verbose(f"[INFO] #### FOUND {_n_keithleys} KEITHLEY DEVICES ####\n", timestamp=True)
    print("=" * 100)
    print(
        f"{'Port':<8} | {'Baudrate':<8} | {'Status':<15} | {'Manufacturer':<15} | {'Model':<15} | {'Serial Number':<15}"
    )
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

        if dev["is_keithley"]:
            print(
                f"{dev['port']:<8} | {baudrate:<8} | {status:<15} | {dev['manufacturer'][0:14]:<15} | {dev['model']:<15} | {dev['serial_number']:<15}"
            )
        else:
            print(f"{dev['port']:<8} | {baudrate:<8} | {status:<15} | {'-':<15} | {'-':<15} | {'-':<15}")
    print("=" * 100, "\n")


def print_keithley_properties(dev):
    """Prints the properties of a detected device in a readable format."""

    print("-" * 100)
    print(f"Port: {dev['port']}")
    print(f"Baudrate: {dev.get('baudrate', 'N/A')}")
    print(f"Description: {dev['description']}")
    if dev.get("status") == "response":
        print(f"IDN: {dev.get('idn', 'N/A')}")
    else:
        print(f"IDN: {dev.get('idn', 'N/A')} (No valid response)")
    if dev.get("is_keithley"):
        print(f"Manufacturer: {dev.get('manufacturer', 'N/A')}")
        print(f"Model: {dev.get('model', 'N/A')}")
        print(f"Serial Number: {dev.get('serial_number', 'N/A')}")
        print(f"Firmware: {dev.get('firmware', 'N/A')}")
    print("-" * 100, "\n")


if __name__ == "__main__":
    devs = detect_keithley_devices(baudrate=None, verbose=True, debug=False)

    if devs is None:
        print_verbose("[ERROR] : No Keithley devices found. Exiting.", verbose=True, timestamp=True)
        exit(1)

    for dev in devs:
        if dev["is_keithley"]:
            print_keithley_properties(dev)
            serial_query(":CONF?", dev["port"], verbose=True, debug=False)
            read_res = serial_query(":READ?", dev["port"], verbose=True, debug=False)
            print(f"[RESULT] Raw data length: {read_res.count(',') + 1} data points")  # type: ignore
