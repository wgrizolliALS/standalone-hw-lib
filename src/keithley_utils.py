import serial
import serial.tools.list_ports
import time
from datetime import datetime

DEBUG = False


def _colorStr(s, color=None, bold=False):
    """Return the string wrapped in ANSI color/bold escape codes.

    Args:
        s: The input string to colorize.
        color: Optional color name (red, green, blue, purple, cyan).
        bold: If True, make the text bold.

    Returns:
        The ANSI-escaped string for terminal display.
    """

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


def print_verbose(msg, verbose=True, timestamp=False, color=None, bold=False):
    """Print `msg` to stdout when `verbose` is True, with optional color and timestamp.

    Args:
        msg: Message to print.
        verbose: If False, suppress printing.
        timestamp: If True, prepend a timestamp to the message.
        color: Optional color name for terminal output.
        bold: If True, print in bold.
    """

    if verbose:
        if timestamp:
            msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] : {msg}"
        if color is not None or bold:
            msg = _colorStr(msg, color=color, bold=bold)
        print(msg)


def serial_query(
    cmd: str,
    port: str,
    baudrate: int = 9600,
    wait_serial=False,
    verbose: bool = False,
    debug: bool = DEBUG,
    wait_before_read: float = 0.1,
) -> str | None:
    """Send a command string to a serial device and read a single-line response.

    This opens the serial port, writes `cmd`, optionally waits for data to become
    available, then reads one line and returns it (or `None` on empty response
    or error). Exceptions are caught and logged via `print_verbose`.

    Args:
        cmd: Command string to send (a newline is appended).
        port: Serial device path (e.g. COM3 or /dev/ttyUSB0).
        baudrate: Serial baud rate.
        wait_serial: If True, poll until data is available or a timeout occurs.
        verbose: Enable informational printing.
        debug: Enable debug printing.
        wait_before_read: Sleep interval between polls when `wait_serial` is True.

    Returns:
        The decoded response string, or `None` on empty response or error.
    """
    print_verbose(f"[DEBUG] : Attempting to open serial port {port} at baudrate {baudrate}", debug)

    try:
        with serial.Serial(port, baudrate=baudrate, timeout=0.5) as ser:
            print_verbose(f"[COMMAND] = {cmd}", verbose, timestamp=True, color="cyan", bold=True)
            ser.write(f"{cmd}\n".encode())

            _time_init = time.time()
            while wait_serial and ser.in_waiting == 0:
                time.sleep(wait_before_read)
                print_verbose(f"[DEBUG] : Waiting for response from {cmd}...", debug, timestamp=True)

                if time.time() - _time_init >= 5 * ser.timeout:  # type: ignore
                    raise TimeoutError(f"Timeout waiting for response to {cmd} on {port}")

            response = ser.readline().decode(errors="ignore").strip()

        if response == "":
            print_verbose(
                "[RESPONSE] = [EMPTY PORT]",
                verbose,
                timestamp=True,
                color="cyan",
                bold=False,
            )
            response = None
        else:
            print_verbose(
                f"[RESPONSE] = {response}",
                verbose,
                timestamp=True,
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
            color="red",
            bold=True,
        )
        return None
    except TimeoutError as e:
        print_verbose(f"[ERROR] : {e}", verbose, timestamp=True, color="red", bold=True)
        return None
    except Exception as e:
        print_verbose(
            f"[ERROR] : Unexpected error on {port}: {e}",
            verbose,
            timestamp=True,
            color="red",
            bold=True,
        )
        return None


def serial_batched(
    cmds: list,
    port: str,
    verbose: bool = True,
    debug: bool = DEBUG,
    send_ind: bool = False,
    wait_between_cmds: float = 0.1,
    check_errors: bool = True,
) -> str | None:
    """Send a list of serial commands either batched or individually.

    If any command contains a question mark `?` (a query) or `send_ind` is
    True, commands are sent one-by-one with a small delay between them. When
    safe, the list can be joined with `;` and sent as a single batched write
    which may be faster for write-only sequences.

    Args:
        cmds: List of command strings to send.
        port: Serial device path.
        verbose: Enable informational printing.
        debug: Enable debug printing.
        send_ind: Force sending commands individually.
        wait_between_cmds: Seconds to sleep between commands.
        check_errors: If True, query the instrument error queue after sends.

    Returns:
        The last received response (or `None`).
    """

    if any("?" in _str for _str in cmds) or send_ind:
        for cmd in cmds:
            res = serial_query(cmd, port, verbose=verbose, debug=debug)
            if check_errors:
                time.sleep(wait_between_cmds)
                check_inst_errors(port, verbose=verbose, debug=debug)
            time.sleep(wait_between_cmds)
    else:
        batch_cmd = ";".join(cmds)
        res = serial_query(batch_cmd, port, verbose=verbose, debug=debug)
        if check_errors:
            time.sleep(wait_between_cmds)
            check_inst_errors(port, verbose=verbose, debug=debug)
        time.sleep(wait_between_cmds)
    return res


def query_and_check(
    cmd: str,
    port: str,
    verbose: bool = True,
    debug: bool = DEBUG,
    wait_between_cmds: float = 0.1,
    check_errors: bool = True,
) -> str | None:
    """Send a single query command then optionally check the instrument error queue.

    This is a thin wrapper around `serial_query` that performs an optional
    error-checking step (`:SYST:ERR?`) after the query to surface instrument
    errors to the user.

    Args:
        cmd: Query string to send.
        port: Serial device path.
        verbose: Enable informational printing.
        debug: Enable debug printing.
        wait_between_cmds: Seconds to sleep before/after error checking.
        check_errors: If True, call `check_inst_errors` after the query.

    Returns:
        The response string from the device, or `None` on error.
    """

    _res = serial_query(cmd, port, verbose=verbose, debug=debug)
    if check_errors:
        time.sleep(wait_between_cmds)
        check_inst_errors(port, verbose=verbose, debug=debug)
        time.sleep(wait_between_cmds)
    return _res


def close_serial_connection(port, verbose=True):
    """Attempt to close a serial connection on `port` if open.

    Args:
        port: Serial device path.
        verbose: Enable informational printing about the close operation.
    """
    try:
        ser = serial.Serial(port)
        if ser.is_open:
            ser.close()
            print_verbose(f"[INFO] Serial connection on {port} closed.", verbose=verbose, color="blue", bold=True)
        else:
            print_verbose(f"[INFO] Serial connection on {port} was already closed.", verbose=verbose, color="yellow")
    except Exception as e:
        print_verbose(
            f"[ERROR] Failed to close serial connection on {port}: {e}",
            verbose=verbose,
            color="red",
            bold=True,
        )


def check_inst_errors(port, verbose=True, debug=DEBUG):
    """Poll the instrument error queue and print any non-zero errors.

    Repeatedly queries `:SYST:ERR?` until the instrument reports `0,` (no error).

    Args:
        port: Serial device path.
        verbose: Enable informational printing.
        debug: Enable debug printing.
    """
    while True:
        err = serial_query(":SYST:ERR?", port, verbose=verbose, debug=debug)
        if err is None or err.startswith("0,"):
            break
        print_verbose(f"[INSTR ERROR] {err}", verbose=verbose, timestamp=True, color="red", bold=True)


def detect_keithley_devices(baudrate: int | None = 9600, timeout=0.5, verbose=False, debug=DEBUG) -> list[dict] | None:
    """Scan available serial ports to identify Keithley instruments.

    For each detected port the function attempts to send `*IDN?` at the
    requested `baudrate`, or over a set of common baud rates if `baudrate` is
    None. Results are returned as a list of dictionaries describing each port
    and whether a valid IDN response was received.

    Args:
        baudrate: If provided, try only this baudrate; otherwise test common rates.
        timeout: Serial timeout used for low-level operations (seconds).
        verbose: Enable informational printing.
        debug: Enable debug printing.

    Returns:
        A list of device dictionaries when ports were found, otherwise `None`.
    """
    found_devices = []
    ports = serial.tools.list_ports.comports()
    print_verbose(f"[INFO] Detected {len(ports)} serial ports to scan.", verbose, timestamp=True)
    print_verbose(f"[DEBUG] : {ports = }", debug, timestamp=True)

    common_baudrates = [9600, 19200, 38400, 57600, 115200]

    print_verbose("[INFO] : Loop ports and baudrates", verbose)
    for port in ports:
        baudrate_list = [baudrate] if baudrate is not None else common_baudrates

        print_verbose(f"[INFO] : Checking {port.device = }", verbose)
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


def reset_instrument(port, verbose=True, debug=DEBUG):
    """Reset instrument to a known state."""
    print_verbose("[INFO] Resetting instrument...", color="purple", verbose=verbose)
    _start_t = time.time()
    cmds = [
        "*RST",  # Reset to known state
        ":SYST:REM",  # Remote mode for faster serial response; comment out if you want to use front panel after this
        ":FORM:ELEM READ,TIME",  # Set Format.
    ]  # Reset to known state, then remote mode for faster serial response
    serial_batched(cmds, port, verbose=verbose, debug=debug)
    print_verbose(
        f"[INFO] Reset complete. Time elapsed: {time.time() - _start_t:.2f} s", color="purple", verbose=verbose
    )

    return True


def is_autorange_ON(port, verbose=True, debug=DEBUG) -> bool:
    """Query autorange status."""

    print_verbose(
        "[INFO] Checking autorange status...",
        verbose=verbose,
        timestamp=True,
        color="purple",
    )

    _resp = query_and_check(":SENS:CURR:RANG:AUTO?", port, verbose=verbose, debug=debug)
    autorange_status = _resp.strip() if _resp is not None else None

    if autorange_status is not None and autorange_status == "0":
        print_verbose("[INFO] Autorange status: OFF", color="purple", verbose=verbose)
        return False
    else:
        print_verbose("[INFO] Autorange status: ON", color="purple", verbose=verbose)
        return True


def set_autorange(port, enable=True, verbose=True, debug=DEBUG):
    """Enable or disable autorange."""
    if enable:
        print_verbose("[INFO] Enabling autorange...", color="purple", verbose=verbose)
        serial_batched([":SENS:CURR:RANG:AUTO ON"], port, verbose=verbose, debug=debug)
    else:
        print_verbose("[INFO] Disabling autorange...", color="purple", verbose=verbose)
        serial_batched([":SENS:CURR:RANG:AUTO OFF"], port, verbose=verbose, debug=debug)

    return is_autorange_ON(port, verbose=verbose, debug=debug)


def get_curr_range(port, verbose=True, debug=DEBUG) -> float:
    """Query current range."""
    if is_autorange_ON(port, verbose=verbose, debug=debug):
        return -9999.00  # sentinel value to indicate autorange is ON and numeric range is not fixed
    else:
        print_verbose("[INFO] Autorange is OFF, querying current range...", color="purple", verbose=verbose)
        _resp = query_and_check(":SENS:CURR:RANG?", port, verbose=verbose, debug=debug)
        if _resp is None:
            print_verbose(
                "[WARNING] Received empty response when querying current range. Returning None.",
                color="red",
                verbose=verbose,
            )
            raise RuntimeError("Failed to query current range; received empty response.")
        curr_range = float(_resp.strip())
        print_verbose(f"[INFO] Current range: {curr_range}", color="purple", verbose=verbose)
        return curr_range


def get_curr_NPLC(port, verbose=True, debug=DEBUG) -> float:
    """Query current NPLC."""
    print_verbose("[INFO] Querying current NPLC...", color="purple", verbose=verbose)
    _resp = query_and_check(":SENS:CURR:NPLC?", port, verbose=verbose, debug=debug)
    if _resp is None:
        print_verbose(
            "[WARNING] Received empty response when querying current NPLC. Returning None.",
            color="red",
            verbose=verbose,
        )
        raise RuntimeError("Failed to query current NPLC; received empty response.")
    curr_nplc = float(_resp.strip())
    print_verbose(f"[INFO] Current NPLC: {curr_nplc}", color="purple", verbose=verbose)
    return curr_nplc


def set_range(port, set_curr_range=None, nplc=1.0, verbose=True, debug=DEBUG) -> tuple[float, float]:
    """
    Enable autorange briefly so the instrument selects a range, read one measurement,
    query the selected range, then lock it and return numeric range.

    AUTORRANGE IS ALWAYS OFF AFTER THIS FUNCTION.
    """
    print_verbose("[INFO] Starting autorange selection...", verbose=verbose, timestamp=True, color="purple")
    _start_t = time.time()

    cmds = [
        ":SYST:ZCH OFF",  # turn off zero check for faster readings
        ":SYST:AZERO OFF",  # turn off autozero for faster readings
        ":SENS:AVER:STAT 0",  # turn off averaging for faster readings
    ]
    serial_batched(cmds, port, verbose=verbose, debug=debug)

    if set_curr_range is None:
        print_verbose(
            "[INFO] Using AUTORANGE to select initial range based on zero reading...\n"
            + f"[INFO] AUTORRANGE ON, NPLC = {nplc}...",
            verbose=verbose,
            timestamp=True,
            color="purple",
        )
        cmds = [
            f":SENS:CURR:NPLC {nplc}",
            ":SENS:CURR:RANGE:AUTO ON",  # enable autorange to let instrument select appropriate range based on zero reading
        ]
    elif isinstance(set_curr_range, float):
        print_verbose(
            "[INFO] Using specified range. AUTORANGE is OFF...\n"
            + f"[INFO] AUTORRANGE OFF, NPLC = {nplc}, RANGE SET POINT = {set_curr_range}...",
            verbose=verbose,
            timestamp=True,
            color="purple",
        )
        cmds = [
            f":SENS:CURR:NPLC {nplc}",
            ":SENS:CURR:RANGE:AUTO OFF",  # disable autorange to lock the range
            f":SENS:CURR:RANG {set_curr_range}",
        ]
    else:
        raise ValueError(f"Invalid curr_range value: {set_curr_range}, type {type(set_curr_range)}")

    serial_batched(cmds, port, verbose=verbose, debug=debug)

    # Perform a single read to let instrument choose range
    _t_read_start = time.time()

    print_verbose(
        "[INFO] Performing initial read to let instrument choose range OR check overflow...",
        verbose=verbose,
        timestamp=True,
        color="purple",
    )

    while True:
        _ans = query_and_check(
            ":READ?",
            port,
            wait_between_cmds=1.0,  # wait longer after :READ? to give instrument time to process and update range if needed
            check_errors=False,
            verbose=verbose,
            debug=debug,
        )

        if _ans is not None:
            break

        print_verbose(
            "[INFO] Empty response to :READ?....",
            verbose=verbose,
            timestamp=True,
            color="purple",
        )

    if set_curr_range is None:
        # Lock the detected range and turn autorange off
        print_verbose(
            "[INFO] Locking range at detected value and turning autorange off...",
            verbose=verbose,
            timestamp=True,
            color="purple",
        )
        serial_batched([":SENS:CURR:RANGE:AUTO OFF"], port, verbose=verbose, debug=debug)

    # Query the selected numeric range
    print_verbose(
        "[INFO] Querying Range and NPLC selected by INSTRUMENT...", verbose=verbose, timestamp=True, color="purple"
    )

    rng_val = get_curr_range(port, verbose=verbose, debug=debug)

    if rng_val > 0.0:  # check if autorange is still ON based on sentinel value
        print_verbose(
            "[INFO] Autorange is OFF as expected.",
            verbose=True,
            timestamp=True,
            color="green",
        )
    else:
        print_verbose(
            "[WARNING] Autorange is ON, unexpected behavior.",
            verbose=verbose,
            timestamp=True,
            color="red",
        )
        raise RuntimeError("Autorange should be OFF after range selection, but query indicates it is still ON.")

    nplc_val = get_curr_NPLC(port, verbose=verbose, debug=debug)

    print_verbose(
        "[INFO] Autorange selection complete. Time elapsed: {:.2f} s".format(time.time() - _start_t),
        verbose=verbose,
        timestamp=True,
        color="purple",
    )

    return rng_val, nplc_val


def zero_instrument(
    port,
    verbose=True,
    debug=DEBUG,
):
    """
    If curr_range is None, auto-select range first. Then take one zero reading
    """
    _start_t = time.time()
    print_verbose("[INFO] Starting zero measurement...", verbose=verbose, timestamp=True, color="purple")

    cmds = [  # From Manual pg 3-6
        # ":*RST",
        ":SYST:TIME:RESET",
        ":SYST:ZCH ON",
        ":INIT",
        ":SYST:ZCOR:STAT OFF",
        ":SYST:ZCOR:ACQ",
        ":SYST:ZCH OFF",
        ":SYST:ZCOR ON",
    ]

    serial_batched(cmds, port, verbose=verbose, debug=debug, check_errors=True)

    t_read = time.time()

    while True:
        resp = query_and_check(
            ":READ?",
            port,
            wait_between_cmds=1.0,  # wait longer after :READ? to give instrument time to process and update range if needed
            check_errors=False,
            verbose=verbose,
            debug=debug,
        )
        if resp is not None:
            break

        print_verbose(
            "[INFO] Empty response to :READ? Repeating...",
            verbose=verbose,
            timestamp=True,
            color="purple",
        )

    if resp is not None and "A" in resp:
        zero_val = resp.strip().replace("A", "")
    elif resp is not None and "," in resp:
        zero_val = resp.rsplit(",")[0].strip()
    else:
        zero_val = resp.strip()

    try:
        zero_val = float(zero_val)
    except ValueError:
        zero_val = None

    print_verbose(
        "[INFO] Zero measurement complete.\n" + f"[INFO] Zero value: {zero_val}.",
        verbose=verbose,
        timestamp=True,
        color="green",
    )
    print_verbose(
        f"[INFO] Zeroing instrument... ENDED. Time elapsed: {time.time() - _start_t:.2f} s",
        verbose=verbose,
        timestamp=True,
        color="purple",
    )

    return zero_val


def setup_read_acquisition(port, points_for_stat=1, verbose=True, debug=DEBUG):
    """
    Prepare instrument for single-point acquisition with timestamps.
    """
    print_verbose("[INFO] Setting up single-point acquisition...", color="purple", verbose=verbose)
    _start_t = time.time()

    # Note that, according to manual pg 12-2
    # when #CONF is executed, the 6487 is configured as follows:
    # ▪ All controls related to the selected function are defaulted to the *RST values.
    # ▪ The event control sources of the trigger model are set to immediate.
    # ▪ The arm and trigger count values of the trigger model are set to one.
    # ▪ The delay of the trigger model is set to zero.
    # ▪ The 6487 is placed in the idle state.
    # ▪ All math calculations are disabled.
    # ▪ Buffer operation is disabled. A storage operation presently in process will be aborted.
    # ▪ Autozero is enabled.

    serial_batched([":CONF:CURR;:CONF?"], port, verbose=verbose, debug=debug)

    print_verbose(
        f"[INFO] Single-point acquisition setup complete. Time elapsed: {time.time() - _start_t:.2f} s",
        color="purple",
        verbose=verbose,
    )
    return True


def setup_waveform_acquisition(port, num_points=60, verbose=True, debug=DEBUG):
    """
    Prepare instrument for buffered waveform acquisition with timestamps.
    """

    print_verbose("[INFO] Setting up waveform acquisition...", color="purple", verbose=verbose)
    _start_t = time.time()

    setup_recipe = [  # following pg 6-8 from manual
        # ":FORM:ELEM READ,TIME",
        # ":SENS:CURR:RANGE:AUTO OFF",
        f":TRIG:COUNT {num_points}",  # single-trigger sampling for even spacing
        f":TRAC:POIN {num_points}",  # specify number of readings to store: 1 to 3000
        ":TRAC:FEED SENS",  # Store raw input readings (as opposed to calculated values like avg and max/min).
        ":TRAC:FEED:CONT NEXT",  # `NEXT` Enables the buffer. `NEVer disable it.
    ]
    serial_batched(setup_recipe, port, verbose=verbose, debug=debug)

    print_verbose(
        f"[INFO] Waveform acquisition setup complete. Time elapsed: {time.time() - _start_t:.2f} s",
        color="purple",
        verbose=verbose,
    )

    return True


def acq_read(port, verbose=True, debug=DEBUG):
    t_read = time.time()

    resp = query_and_check(":read?", port, verbose=verbose, debug=debug)

    if resp is None:
        print_verbose(
            "[WARNING] Received empty response to :READ? Returning None.",
            color="red",
            verbose=verbose,
        )
        return None

    return resp


def acq_waveform(port, poll_interval=0.5, verbose=True, debug=DEBUG):
    """
    Wait for buffer to fill then read buffered data (readings + timestamps).
    Returns raw response string from :TRAC:DATA?; caller should parse into values/times.
    """

    print_verbose(
        "\n[INFO] Acquiring waveform...",
        verbose=verbose,
        timestamp=True,
        color="purple",
    )

    _start_total_time = time.time()

    _start_acq_time = time.time()

    # Arm acquisition
    query_and_check(":INIT", port, verbose=verbose, debug=debug)

    while True:
        resp = query_and_check(":TRAC:POIN:ACT?", port, verbose=True)

        if resp is not None:
            break
        print_verbose(
            f"[INFO] Waiting for acquisition to complete... time elapsed: {time.time() - _start_acq_time:.2f}s",
            color="purple",
            verbose=verbose,
        )
        time.sleep(poll_interval)

    print_verbose(
        f"[INFO] Acquisition COMPLETED... time elapsed: {time.time() - _start_acq_time:.2f}s",
        color="purple",
        verbose=verbose,
    )

    print_verbose(
        "\n[INFO] Download data from instrument...",
        color="purple",
        verbose=verbose,
    )

    # Read all buffered readings and timestamps in one transfer
    raw = query_and_check(":TRAC:DATA?", port, verbose=verbose, debug=debug)

    print_verbose(
        f"[INFO] Waveform acquisition complete. Data Download COMPLETED. Time elapsed: {time.time() - _start_total_time:.2f} s.",
        color="purple",
        verbose=verbose,
    )

    return raw


if __name__ == "__main__":
    devs = detect_keithley_devices(baudrate=None, verbose=True, debug=DEBUG)

    if devs is None:
        print_verbose("[ERROR] : No Keithley devices found. Exiting.", verbose=True, timestamp=True)
        exit(1)

    for dev in devs:
        if dev["is_keithley"]:
            print_keithley_properties(dev)
            serial_query(":CONF?", dev["port"], verbose=True, debug=DEBUG)
            read_res = serial_query(":READ?", dev["port"], verbose=True, debug=DEBUG)
            print(f"[RESULT] Raw data length: {read_res.count(',') + 1} data points")  # type: ignore
