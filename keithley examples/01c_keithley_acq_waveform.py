# keithley_6487_waveform.py
import time
import re

import keithley_utils as kthu  # your serial helper module; must provide serial_query(cmd, port, verbose, debug)

DEFAULT_MAINS_PERIOD = 1 / 60.0  # set to 1/50.0 if on 50 Hz mains


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


def reset_instrument(port, verbose=True, debug=True):
    """Reset instrument to a known state."""
    if verbose:
        print(_colorStr("[INFO] Resetting instrument...", color="purple"))
        _start_t = time.time()
    cmds = ["*RST", ":SYST:REM"]
    _send_batched(cmds, port, verbose=verbose, debug=debug)
    if verbose:
        print(_colorStr(f"[INFO] Reset complete. Time elapsed: {time.time() - _start_t:.2f} s", color="purple"))

    return True


def auto_select_range(port, nplc=1.0, mains_period=DEFAULT_MAINS_PERIOD, verbose=True, debug=True):
    """
    Enable autorange briefly so the instrument selects a range, read one measurement,
    query the selected range, then lock it and return numeric range.
    """
    if verbose:
        print(_colorStr("[INFO] Starting autorange selection...", color="purple"))
        _start_t = time.time()
    cmds = [
        ":FORM:ELEM READ",
        f":SENS:CURR:NPLC {nplc}",
        ":SYST:ZCH OFF",
        ":SYST:AZERO OFF",
        ":SENS:AVER:STAT 0",
        ":SENS:CURR:RANGE:AUTO ON",
    ]
    t0 = time.time()
    _send_batched(cmds, port, verbose=verbose, debug=debug)
    kthu.print_verbose(f"[DEBUG] autorange commands sent (t={time.time():.3f})", verbose=debug, timestamp=True)

    # Give one PLC for settling
    plc_wait = nplc * mains_period + 0.05
    kthu.print_verbose(f"[DEBUG] Waiting {plc_wait:.3f}s for PLC settling", verbose=debug, timestamp=True)
    time.sleep(plc_wait)
    kthu.print_verbose(f"[DEBUG] PLC wait done (elapsed {time.time() - t0:.3f}s)", verbose=debug, timestamp=True)

    # Perform a single read to let instrument choose range
    t_read_start = time.time()
    _ = kthu.serial_query(":READ?", port, verbose=verbose, debug=debug)
    kthu.print_verbose(f"[DEBUG] :READ? completed in {time.time() - t_read_start:.3f}s", verbose=debug, timestamp=True)

    # Query the selected numeric range
    rng_resp = kthu.serial_query(":SENS:CURR:RANG?", port, verbose=verbose, debug=debug)
    try:
        rng_val = float(re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", rng_resp).group(0))
    except Exception:
        rng_val = None

    # Lock the detected range and turn autorange off
    if rng_val is not None:
        _ = kthu.serial_query(f":SENS:CURR:RANG {rng_val}", port, verbose=verbose, debug=debug)
    _ = kthu.serial_query(":SENS:CURR:RANGE:AUTO OFF", port, verbose=verbose, debug=debug)

    if verbose:
        print(
            _colorStr(
                "[INFO] Autorange selection complete. Time elapsed: {:.2f} s".format(time.time() - _start_t),
                color="purple",
            )
        )
        print(_colorStr(f"[INFO] Selected range: {rng_val}", color="green"))

    return rng_val


def zero_instrument(port, curr_range=None, nplc=1.0, mains_period=DEFAULT_MAINS_PERIOD, verbose=True, debug=True):
    """
    If curr_range is None, auto-select range first. Then take one zero reading
    with autorange/autozero/zerocheck off. Returns (zero_val, locked_range).
    """

    if verbose:
        print(_colorStr("[INFO] Starting zero measurement...", color="purple"))
        _start_t = time.time()

    if verbose:
        print(_colorStr("[INFO] Zeroing instrument...", color="purple"))
        _start_t = time.time()
    if curr_range is None:
        kthu.print_verbose("[DEBUG] Starting autorange selection", verbose=debug, timestamp=True)
        t0 = time.time()
        curr_range = auto_select_range(port, nplc=nplc, mains_period=mains_period, verbose=verbose, debug=debug)
        kthu.print_verbose(
            f"[DEBUG] autorange selected {curr_range} in {time.time() - t0:.3f}s", verbose=debug, timestamp=True
        )

    # Configure fixed-range single-shot measurement
    cmds = [
        ":FORM:ELEM READ",
        f":SENS:CURR:RANG {curr_range}",
        f":SENS:CURR:NPLC {nplc}",
        ":SENS:CURR:RANGE:AUTO OFF",
        ":SYST:ZCH OFF",
        ":SYST:AZERO OFF",
        ":SENS:AVER:STAT 0",
        ":TRIG:SOUR IMM",
        ":TRIG:COUNT 1",
        ":TRAC:POIN 1",
        ":TRAC:POIN:ACT 0",
    ]
    _send_batched(cmds, port, verbose=verbose, debug=debug)

    _ = kthu.serial_query(":INIT", port, verbose=verbose, debug=debug)
    # Wait one PLC + margin for measurement completion
    plc_wait = nplc * mains_period + 0.05
    kthu.print_verbose(f"[DEBUG] Waiting {plc_wait:.3f}s for measurement completion", verbose=debug, timestamp=True)
    time.sleep(plc_wait)

    t_read = time.time()
    resp = kthu.serial_query(":READ?", port, verbose=verbose, debug=debug)
    kthu.print_verbose(f"[DEBUG] Final :READ? completed in {time.time() - t_read:.3f}s", verbose=debug, timestamp=True)
    try:
        zero_val = float(re.split(r"[,\s]+", resp.strip())[0])
    except Exception:
        zero_val = None

    if verbose:
        print(
            _colorStr(
                f"[INFO] Zeroing instrument... ENDED. Time elapsed: {time.time() - _start_t:.2f} s",
                color="purple",
            )
        )

        print(
            _colorStr(
                f"[INFO] Zero measurement complete. Zero value: {zero_val}, Locked range: {curr_range}", color="green"
            )
        )

    return zero_val, curr_range


def setup_waveform_acquisition(
    port, num_points=60, nplc=1.0, curr_range=2e-7, mains_period=DEFAULT_MAINS_PERIOD, verbose=True, debug=True
):
    """
    Prepare instrument for buffered waveform acquisition with timestamps.
    """

    if verbose:
        print(_colorStr("[INFO] Setting up waveform acquisition...", color="purple"))
        _start_t = time.time()

    setup_recipe = [
        ":FORM:ELEM READ,TIME",
        f":SENS:CURR:RANG {curr_range}",
        f":SENS:CURR:NPLC {nplc}",
        ":SENS:CURR:RANGE:AUTO OFF",
        ":SYST:ZCH OFF",
        ":SYST:AZERO OFF",
        ":SENS:AVER:STAT 0",
        f":TRAC:POIN {num_points}",
        ":TRAC:POIN:ACT 0",
        ":TRIG:SOUR IMM",
        f":TRIG:COUNT {num_points}",  # single-trigger sampling for even spacing
        ":TRAC:FEED:CONT NEXT",  # model-specific; include if supported
        ":SYST:TIME:RES ON",  # enable timestamps (model-specific)
    ]
    _send_batched(setup_recipe, port, verbose=verbose, debug=debug)
    if verbose:
        print(
            _colorStr(
                f"[INFO] Waveform acquisition setup complete. Time elapsed: {time.time() - _start_t:.2f} s",
                color="purple",
            )
        )

    return True


def acq_waveform(port, num_points=60, timeout_s=None, poll_interval=0.5, verbose=True, debug=True):
    """
    Wait for buffer to fill then read buffered data (readings + timestamps).
    Returns raw response string from :TRAC:DATA?; caller should parse into values/times.
    """

    if verbose:
        print(_colorStr("[INFO] Acquiring waveform...", color="purple"))
        _start_t = time.time()

    if timeout_s is None:
        timeout_s = max(5.0, num_points * 0.02 + 5.0)

    start = time.time()

    # Arm acquisition
    _ = kthu.serial_query(":INIT", port, verbose=verbose, debug=debug)

    while True:
        resp = kthu.serial_query(":TRAC:POIN:ACT?", port, verbose=False, debug=False)
        try:
            active = int(resp.strip())
        except Exception:
            active = 0
        if active >= num_points:
            break
        if (time.time() - start) > timeout_s:
            raise TimeoutError("Timeout waiting for buffer to fill")
        time.sleep(poll_interval)

    # Read all buffered readings and timestamps in one transfer
    raw = kthu.serial_query(":TRAC:DATA?", port, verbose=verbose, debug=debug)

    if verbose:
        print(
            _colorStr(
                f"[INFO] Waveform acquisition complete. Time elapsed: {time.time() - _start_t:.2f} s. Raw data length: {len(raw) if raw else 0}",
                color="purple",
            )
        )
    return raw


def _is_query(cmd: str) -> bool:
    """Return True if cmd expects a response from the instrument."""
    q_indicators = ("?", ":READ", "TRAC:DATA", "TRAC:POIN:ACT", "*IDN?")
    cu = cmd.upper()
    return any(ind in cu for ind in q_indicators)


def _send_batched(cmds: list, port: str, verbose: bool = True, debug: bool = False, delay: float = 0.05):
    """Send consecutive write-only commands batched with ';' where safe.

    Commands that are queries or contain read-like tokens are sent individually.
    """
    buf = []
    for cmd in cmds:
        if _is_query(cmd):
            # flush buffer first
            if buf:
                combined = ";".join(buf)
                # log each buffered command as sent for clearer per-command logging
                for b in buf:
                    kthu.print_verbose(
                        f"[COMMAND] = {b}", verbose, timestamp=True, color_messages=True, color="cyan", bold=True
                    )
                kthu.serial_query(combined, port, verbose=verbose, debug=debug)
                time.sleep(delay)
                buf = []
            kthu.serial_query(cmd, port, verbose=verbose, debug=debug)
            time.sleep(delay)
        else:
            buf.append(cmd)

    if buf:
        combined = ";".join(buf)
        for b in buf:
            kthu.print_verbose(
                f"[COMMAND] = {b}", verbose, timestamp=True, color_messages=True, color="cyan", bold=True
            )
        kthu.serial_query(combined, port, verbose=verbose, debug=debug)
        time.sleep(delay)


# Helper: parse TRAC:DATA? response formatted as READ,TIME into arrays
def parse_trac_data(raw):
    """
    Parse a comma-separated stream of READ,TIME,READ,TIME,... into lists.
    Returns (reads: list[float], times: list[float_or_str]).
    """
    parts = [p.strip() for p in raw.strip().split(",") if p.strip() != ""]
    reads, times = [], []
    for i in range(0, len(parts), 2):
        try:
            reads.append(float(parts[i]))
        except Exception:
            reads.append(None)
        if i + 1 < len(parts):
            times.append(parts[i + 1])
    return reads, times


# Example usage in a __main__ block
if __name__ == "__main__":
    print(_colorStr("[INFO] Starting Keithley waveform acquisition example...", color="purple"))

    try:
        devs = kthu.detect_keithley_devices(baudrate=None, verbose=True)
        print(_colorStr("# Scan for hardware ENDED #\n", color="purple"))

    except Exception as e:
        print(_colorStr(f"Error during Keithley detection: {e}", color="red"))

    dev = devs[0] if devs else None

    SERIALPORT = dev["port"] if dev else None  # type: ignore

    num_points = 10
    nplc = 0.1
    mains_period = DEFAULT_MAINS_PERIOD  # change to 1/50.0 if needed

    # Example flow

    reset_instrument(SERIALPORT, verbose=True, debug=False)

    zero_val, locked_range = None, None

    try:
        zero_val, locked_range = zero_instrument(
            SERIALPORT, curr_range=None, nplc=nplc, mains_period=mains_period, verbose=True, debug=False
        )

    except Exception as e:
        print(_colorStr(f"Zero measurement failed: {e}", color="red"))
    finally:
        locked_range = locked_range if locked_range is not None else 2e-7
        print(_colorStr(f"[WARNING] Autorrange ERROR! Proceeding with locked range: {locked_range}", color="red"))

    setup_waveform_acquisition(
        SERIALPORT,
        num_points=num_points,
        nplc=nplc,
        curr_range=locked_range,
        mains_period=mains_period,
        verbose=True,
        debug=False,
    )

    raw = acq_waveform(SERIALPORT, num_points=num_points, verbose=True, debug=False)
    reads, times = parse_trac_data(raw)

    print(_colorStr(f"[RESULTS] Acquired samples: {len(reads)}", color="green"))
    for r, t in zip(reads, times):
        print(r, t)
