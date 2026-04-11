# %%
"""
%load_ext autoreload
%autoreload 2
"""

import time

import pandas as pd

import keithley_utils as kthu  # your serial helper module;

POWER_LINE_FREQ = 60.0  # set to 50.0 if on 50 Hz mains
POWER_LINE_PERIOD = 1 / POWER_LINE_FREQ

DEBUG = False


# %%
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
    kthu.print_verbose("[INFO] Resetting instrument...", color="purple", verbose=verbose)
    _start_t = time.time()
    cmds = [
        "*RST",  # Reset to known state
        ":SYST:REM",  # Remote mode for faster serial response; comment out if you want to use front panel after this
        ":FORM:ELEM READ,TIME",  # Set Format.
    ]  # Reset to known state, then remote mode for faster serial response
    _send_batched(cmds, port, verbose=verbose, debug=DEBUG)
    kthu.print_verbose(
        f"[INFO] Reset complete. Time elapsed: {time.time() - _start_t:.2f} s", color="purple", verbose=verbose
    )

    return True


def is_autorange_ON(port, verbose=True, debug=True) -> bool:
    """Query autorange status."""

    kthu.print_verbose(
        "[INFO] Checking autorange status...",
        verbose=verbose,
        timestamp=True,
        color="purple",
    )

    _resp = _query_and_check(":SENS:CURR:RANG:AUTO?", port, verbose=verbose, debug=True)
    autorange_status = _resp.strip() if _resp is not None else None

    if autorange_status is not None and autorange_status == "0":
        kthu.print_verbose("[INFO] Autorange status: OFF", color="purple", verbose=verbose)
        return False
    else:
        kthu.print_verbose("[INFO] Autorange status: ON", color="purple", verbose=verbose)
        return True


def set_autorange(port, enable=True, verbose=True, debug=True):
    """Enable or disable autorange."""
    if enable:
        kthu.print_verbose("[INFO] Enabling autorange...", color="purple", verbose=verbose)
        _send_batched([":SENS:CURR:RANG:AUTO ON"], port, verbose=verbose, debug=DEBUG)
    else:
        kthu.print_verbose("[INFO] Disabling autorange...", color="purple", verbose=verbose)
        _send_batched([":SENS:CURR:RANG:AUTO OFF"], port, verbose=verbose, debug=DEBUG)

    return is_autorange_ON(port, verbose=verbose, debug=debug)


def get_curr_range(port, verbose=True, debug=True) -> float:
    """Query current range."""
    if is_autorange_ON(port, verbose=verbose, debug=debug):
        return -9999.00  # sentinel value to indicate autorange is ON and numeric range is not fixed
    else:
        kthu.print_verbose("[INFO] Autorange is OFF, querying current range...", color="purple", verbose=verbose)
        _resp = _query_and_check(":SENS:CURR:RANG?", port, verbose=verbose, debug=DEBUG)
        if _resp is None:
            kthu.print_verbose(
                "[WARNING] Received empty response when querying current range. Returning None.",
                color="red",
                verbose=verbose,
            )
            raise RuntimeError("Failed to query current range; received empty response.")
        curr_range = float(_resp.strip())
        kthu.print_verbose(f"[INFO] Current range: {curr_range}", color="purple", verbose=verbose)
        return curr_range


def get_curr_NPLC(port, verbose=True, debug=True) -> float:
    """Query current NPLC."""
    kthu.print_verbose("[INFO] Querying current NPLC...", color="purple", verbose=verbose)
    _resp = _query_and_check(":SENS:CURR:NPLC?", port, verbose=verbose, debug=DEBUG)
    if _resp is None:
        kthu.print_verbose(
            "[WARNING] Received empty response when querying current NPLC. Returning None.",
            color="red",
            verbose=verbose,
        )
        raise RuntimeError("Failed to query current NPLC; received empty response.")
    curr_nplc = float(_resp.strip())
    kthu.print_verbose(f"[INFO] Current NPLC: {curr_nplc}", color="purple", verbose=verbose)
    return curr_nplc


def select_range(port, set_curr_range=None, nplc=1.0, verbose=True, debug=True) -> tuple[float, float]:
    """
    Enable autorange briefly so the instrument selects a range, read one measurement,
    query the selected range, then lock it and return numeric range.

    AUTORRANGE IS ALWAYS OFF AFTER THIS FUNCTION.
    """
    kthu.print_verbose("[INFO] Starting autorange selection...", verbose=verbose, timestamp=True, color="purple")
    _start_t = time.time()

    cmds = [
        ":SYST:ZCH OFF",  # turn off zero check for faster readings
        ":SYST:AZERO OFF",  # turn off autozero for faster readings
        ":SENS:AVER:STAT 0",  # turn off averaging for faster readings
    ]
    _send_batched(cmds, port, verbose=verbose, debug=DEBUG)

    if set_curr_range is None:
        kthu.print_verbose(
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
        kthu.print_verbose(
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

    _send_batched(cmds, port, verbose=verbose, debug=DEBUG)

    # Perform a single read to let instrument choose range
    _t_read_start = time.time()

    kthu.print_verbose(
        "[INFO] Performing initial read to let instrument choose range OR check overflow...",
        verbose=verbose,
        timestamp=True,
        color="purple",
    )

    while True:
        _ans = _query_and_check(
            ":READ?",
            port,
            wait_between_cmds=1.0,  # wait longer after :READ? to give instrument time to process and update range if needed
            check_errors=False,
            verbose=verbose,
            debug=DEBUG,
        )

        if _ans is not None:
            break

        kthu.print_verbose(
            "[INFO] Empty response to :READ?....",
            verbose=verbose,
            timestamp=True,
            color="purple",
        )

    if set_curr_range is None:
        # Lock the detected range and turn autorange off
        kthu.print_verbose(
            "[INFO] Locking range at detected value and turning autorange off...",
            verbose=verbose,
            timestamp=True,
            color="purple",
        )
        _send_batched([":SENS:CURR:RANGE:AUTO OFF"], port, verbose=verbose, debug=DEBUG)

    # Query the selected numeric range
    kthu.print_verbose(
        "[INFO] Querying Range and NPLC selected by INSTRUMENT...", verbose=verbose, timestamp=True, color="purple"
    )

    rng_val = get_curr_range(port, verbose=verbose, debug=DEBUG)

    if rng_val > 0.0:  # check if autorange is still ON based on sentinel value
        kthu.print_verbose(
            "[INFO] Autorange is OFF as expected.",
            verbose=True,
            timestamp=True,
            color="green",
        )
    else:
        kthu.print_verbose(
            "[WARNING] Autorange is ON, unexpected behavior.",
            verbose=verbose,
            timestamp=True,
            color="red",
        )
        raise RuntimeError("Autorange should be OFF after range selection, but query indicates it is still ON.")

    nplc_val = get_curr_NPLC(port, verbose=verbose, debug=DEBUG)

    kthu.print_verbose(
        "[INFO] Autorange selection complete. Time elapsed: {:.2f} s".format(time.time() - _start_t),
        verbose=verbose,
        timestamp=True,
        color="purple",
    )

    return rng_val, nplc_val


def zero_instrument(
    port,
    verbose=True,
):
    """
    If curr_range is None, auto-select range first. Then take one zero reading
    """
    _start_t = time.time()
    kthu.print_verbose("[INFO] Starting zero measurement...", verbose=verbose, timestamp=True, color="purple")

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

    _send_batched(cmds, port, verbose=verbose, debug=DEBUG, check_errors=True)

    t_read = time.time()

    while True:
        resp = _query_and_check(
            ":READ?",
            port,
            wait_between_cmds=1.0,  # wait longer after :READ? to give instrument time to process and update range if needed
            check_errors=False,
            verbose=verbose,
            debug=DEBUG,
        )
        if resp is not None:
            break

        kthu.print_verbose(
            "[INFO] Empty response to :READ? Repeating...",
            verbose=verbose,
            timestamp=True,
            color="purple",
        )

    kthu.print_verbose(f"[DEBUG] Final :READ? completed in {time.time() - t_read:.3f}s", verbose=DEBUG, timestamp=True)

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

    kthu.print_verbose(
        "[INFO] Zero measurement complete.\n" + f"[INFO] Zero value: {zero_val}.",
        verbose=verbose,
        timestamp=True,
        color="green",
    )
    kthu.print_verbose(
        f"[INFO] Zeroing instrument... ENDED. Time elapsed: {time.time() - _start_t:.2f} s",
        verbose=verbose,
        timestamp=True,
        color="purple",
    )

    return zero_val


def setup_read_acquisition(port, points_for_stat=1, verbose=True, debug=True):
    """
    Prepare instrument for single-point acquisition with timestamps.
    """
    kthu.print_verbose("[INFO] Setting up single-point acquisition...", color="purple", verbose=verbose)
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

    _send_batched([":CONF:CURR;:CONF?"], port, verbose=verbose, debug=DEBUG)

    kthu.print_verbose(
        f"[INFO] Single-point acquisition setup complete. Time elapsed: {time.time() - _start_t:.2f} s",
        color="purple",
        verbose=verbose,
    )
    return True


def setup_waveform_acquisition(port, num_points=60, verbose=True, debug=True):
    """
    Prepare instrument for buffered waveform acquisition with timestamps.
    """

    kthu.print_verbose("[INFO] Setting up waveform acquisition...", color="purple", verbose=verbose)
    _start_t = time.time()

    setup_recipe = [  # following pg 6-8 from manual
        # ":FORM:ELEM READ,TIME",
        # ":SENS:CURR:RANGE:AUTO OFF",
        f":TRIG:COUNT {num_points}",  # single-trigger sampling for even spacing
        f":TRAC:POIN {num_points}",  # specify number of readings to store: 1 to 3000
        ":TRAC:FEED SENS",  # Store raw input readings (as opposed to calculated values like avg and max/min).
        ":TRAC:FEED:CONT NEXT",  # `NEXT` Enables the buffer. `NEVer disable it.
    ]
    _send_batched(setup_recipe, port, verbose=verbose, debug=DEBUG)

    kthu.print_verbose(
        f"[INFO] Waveform acquisition setup complete. Time elapsed: {time.time() - _start_t:.2f} s",
        color="purple",
        verbose=verbose,
    )

    return True


def acq_read(port, verbose=True, debug=True):
    t_read = time.time()

    resp = _query_and_check(":READ?", port, verbose=verbose, debug=DEBUG)
    kthu.print_verbose(f"[DEBUG] Final :READ? completed in {time.time() - t_read:.3f}s", verbose=debug, timestamp=True)

    if resp is None:
        kthu.print_verbose(
            "[WARNING] Received empty response to :READ? Returning None.",
            color="red",
            verbose=verbose,
        )
        return None

    return resp


def acq_waveform(port, poll_interval=0.5, verbose=True, debug=True):
    """
    Wait for buffer to fill then read buffered data (readings + timestamps).
    Returns raw response string from :TRAC:DATA?; caller should parse into values/times.
    """

    kthu.print_verbose(
        "[INFO] Acquiring waveform...",
        verbose=verbose,
        timestamp=True,
        color="purple",
    )

    _start_total_time = time.time()

    _start_acq_time = time.time()

    # Arm acquisition
    _query_and_check(":INIT", port, verbose=verbose, debug=DEBUG)

    while True:
        resp = _query_and_check(":TRAC:POIN:ACT?", port, verbose=True)

        if resp is not None:
            break
        kthu.print_verbose(
            f"[INFO] Waiting for acquisition to complete... time elapsed: {time.time() - _start_acq_time:.2f}s",
            color="purple",
            verbose=verbose,
        )
        time.sleep(poll_interval)

    kthu.print_verbose(
        f"[INFO] Acquisition COMPLETED... time elapsed: {time.time() - _start_acq_time:.2f}s",
        color="purple",
        verbose=verbose,
    )

    kthu.print_verbose(
        "[INFO] Download data from instrument...",
        color="purple",
        verbose=verbose,
    )

    # Read all buffered readings and timestamps in one transfer
    raw = _query_and_check(":TRAC:DATA?", port, verbose=verbose, debug=DEBUG)

    kthu.print_verbose(
        f"[INFO] Waveform acquisition complete. Data Download COMPLETED. Time elapsed: {time.time() - _start_total_time:.2f} s.",
        color="purple",
        verbose=verbose,
    )

    return raw


def _send_batched(
    cmds: list,
    port: str,
    verbose: bool = True,
    debug: bool = False,
    send_ind: bool = False,
    wait_between_cmds: float = 0.1,
    check_errors: bool = True,
) -> str | None:
    """Send consecutive write-only commands batched with ';' where safe.

    Commands that are queries or contain read-like tokens are sent individually.
    """

    if any("?" in _str for _str in cmds) or send_ind:
        for cmd in cmds:
            res = kthu.serial_query(cmd, port, verbose=verbose, debug=DEBUG)
            if check_errors:
                time.sleep(wait_between_cmds)
                check_inst_errors(port, verbose=verbose)
            time.sleep(wait_between_cmds)
    else:
        batch_cmd = ";".join(cmds)
        res = kthu.serial_query(batch_cmd, port, verbose=verbose, debug=DEBUG)
        if check_errors:
            time.sleep(wait_between_cmds)
            check_inst_errors(port, verbose=verbose)
        time.sleep(wait_between_cmds)
    return res


def _query_and_check(
    cmd: str,
    port: str,
    verbose: bool = True,
    debug: bool = False,
    wait_between_cmds: float = 0.1,
    check_errors: bool = True,
) -> str | None:
    """Send consecutive write-only commands batched with ';' where safe.

    Commands that are queries or contain read-like tokens are sent individually.
    """

    _res = kthu.serial_query(cmd, port, verbose=verbose, debug=DEBUG)
    if check_errors:
        time.sleep(wait_between_cmds)
        check_inst_errors(port, verbose=verbose)
        time.sleep(wait_between_cmds)
    return _res


def check_inst_errors(port, verbose=True):
    """Query instrument error queue and print any errors."""
    while True:
        err = kthu.serial_query(":SYST:ERR?", port, verbose=verbose, debug=DEBUG)
        if err is None or err.startswith("0,"):
            break
        kthu.print_verbose(f"[INSTR ERROR] {err}", verbose=verbose, timestamp=True, color="red", bold=True)


# Helper: parse TRAC:DATA? response formatted as READ,TIME into arrays
def parse_trac_data(raw):
    """
    Parse a comma-separated stream of READ,TIME,READ,TIME,... into lists.
    Returns (reads: list[float], times: list[float_or_str]).
    """
    parts = [p.strip() for p in raw.strip().split(",") if p.strip() != ""]
    reads, times = [], []
    for i in range(0, len(parts), 2):
        reads.append(float(parts[i]))

    for i in range(0, len(parts), 2):
        times.append(float(parts[i + 1]))

    df = pd.DataFrame({"Current_Amps": reads, "Time_Secs": times})

    return df


# %% Example usage in a __main__ block
if __name__ == "__main__":
    pass
    # %% Scan For Instruments and Select Device
    _total_t_start = time.time()
    kthu.print_verbose("[INFO] Starting Keithley waveform acquisition example...", color="purple", verbose=True)

    try:
        devs = kthu.detect_keithley_devices(baudrate=None, verbose=True)
        kthu.print_verbose("# Scan for hardware ENDED #\n", color="purple")

    except Exception as e:
        kthu.print_verbose(f"Error during Keithley detection: {e}", color="red")

    SERIALPORT = devs[0]["port"] if devs[0]["port"] else None  # type: ignore
    if SERIALPORT is None:
        kthu.print_verbose("[ERROR] No valid serial port found for device.", color="red", bold=True)
        raise SystemExit(1)

    # %% Reset Instrument and Check for Errors

    reset_instrument(SERIALPORT, verbose=True)

    # %% Zero Instrument and Check for Errors

    zero_val = zero_instrument(SERIALPORT, verbose=True)

    # %%
    # for _sel_range in [3.0e-11, 3.0e-10, 3.0e-9, 3.0e-8, 3.0e-7, 3.0e-6, 3.0e-5, 3.0e-4, 3.0e-3, 3.0e-2, 3.0e-1, 3.0e0]:
    #     final_range = _send_batched([f":SENS:CURR:RANG {_sel_range};:SENS:CURR:RANG?"], SERIALPORT, verbose=True)
    #     time.sleep(1)

    # Smaller scale is 2.100000E-09
    # Larger scale is 2.100000E-02

    # %% Setup Acquisition, Acquire Waveform, Parse Results
    # %% MAIN LOOP: Setup acquisition, acquire waveform, parse results
    num_points = 10
    # nplc = 1.0
    _df_list: list[pd.DataFrame] = []

    _start_t_main_loop = time.time()

    _sel_range_vals = [
        # 3.0e-10,
        # 3.0e-9,
        3.0e-8,
        # 3.0e-7,
        # 3.0e-6,
        # 3.0e-5,
        # 3.0e-4,
        # 3.0e-3,
    ]
    nplc_vals = [0.1, 1.0, 10.0]
    _step = 0

    for _sel_range in _sel_range_vals:
        for nplc in nplc_vals:
            select_range(SERIALPORT, set_curr_range=_sel_range, nplc=nplc, verbose=True)

            setup_waveform_acquisition(
                SERIALPORT,
                num_points=num_points,
                verbose=True,
                debug=False,
            )

            raw = acq_waveform(SERIALPORT, verbose=True)

            final_range = get_curr_range(SERIALPORT, verbose=True)

            _df = parse_trac_data(raw)
            _df["NPLC"] = nplc
            _df["Range"] = final_range
            _df_list.append(_df)

            _step += 1
            kthu.print_verbose(
                "\n########### [INFO] MAIN LOOP: Step "
                + f"{_step} of {len(_sel_range_vals) * len(nplc_vals)}."
                + f" Time elapsed: {time.time() - _start_t_main_loop:.2f} s\n",
                color="purple",
                timestamp=False,
            )

    # Ensure we actually collected any data before concatenating
    if not _df_list:
        raise RuntimeError("No data collected: _df_list is empty. Check instrument connectivity and acquisition loop.")

    df = pd.concat(_df_list, ignore_index=True)

    df["Time_msecs"] = df["Time_Secs"] * 1000
    # %%
    kthu.print_verbose(f"[RESULTS] Acquired samples: {len(df)}", color="green")

    kthu.print_verbose("[RESULTS] Samples DataFrame Head 10:", color="green", bold=True)
    print(df.head(10))
    kthu.print_verbose("[RESULTS] Samples DataFrame info:", color="green", bold=True)
    print(df.info())

    # %% Post Processing

    df_post = pd.DataFrame(
        {
            "Acq_Time_ms": [],
            "NPLC": [],
            "Range": [],
            "Time_Diffs_ms_Mean": [],
            "Time_Diffs_ms_Max": [],
            "Time_Diffs_ms_Min": [],
            "Mean_Dead_Time_ms": [],
            "Max_Dead_Time_ms": [],
            "Min_Dead_Time_ms": [],
            "Mean_Dead_Time_Percent": [],
            "Max_Dead_Time_Percent": [],
            "Min_Dead_Time_Percent": [],
        }
    )

    for nplc in df["NPLC"].unique():
        act_time_ms = nplc / POWER_LINE_FREQ * 1000
        kthu.print_verbose(
            f"[RESULTS] Expected acquisition time based on NPLC={nplc} and PL period: {act_time_ms:.4f} ms",
            color="blue",
        )
        for rng in df["Range"].unique():
            # time_diffs_ms = df[df["NPLC"] == nplc]["Time_msecs"].diff().dropna()
            time_diffs_ms = df.loc[(df["NPLC"] == nplc) & (df["Range"] == rng), "Time_msecs"].diff().dropna()  # type: ignore

            new_row = {
                "Acq_Time_ms": act_time_ms,
                "NPLC": nplc,
                "Range": rng,
                "Time_Diffs_ms_Mean": time_diffs_ms.mean(),
                "Time_Diffs_ms_Max": time_diffs_ms.max(),
                "Time_Diffs_ms_Min": time_diffs_ms.min(),
                "Mean_Dead_Time_ms": time_diffs_ms.mean() - act_time_ms,
                "Max_Dead_Time_ms": time_diffs_ms.max() - act_time_ms,
                "Min_Dead_Time_ms": time_diffs_ms.min() - act_time_ms,
                "Mean_Dead_Time_Percent": (time_diffs_ms.mean() / act_time_ms - 1) * 100,
                "Max_Dead_Time_Percent": (time_diffs_ms.max() / act_time_ms - 1) * 100,
                "Min_Dead_Time_Percent": (time_diffs_ms.min() / act_time_ms - 1) * 100,
            }

            # df_post.loc[len(df_post)] = new_row  #
            df_post.loc[len(df_post)] = pd.Series(new_row)  # append new row to summary DataFrame

    # %%
    kthu.print_verbose(f"[RESULTS] Post-Processing Conditions: {len(df)}", color="green")

    kthu.print_verbose("[RESULTS] Post-Processing DataFrame Head 10:", color="green", bold=True)
    print(df_post.head(10))
    kthu.print_verbose("[RESULTS] Post-Processing DataFrame info:", color="green", bold=True)
    print(df_post.info())

    # %%
    kthu.print_verbose("[RESULTS] Dead Time Only DataFrame:", color="green", bold=True)
    print(df_post.iloc[:, [1, 0, 2, 6]])

    # %%
    _total_t_end = time.time()
    kthu.print_verbose(
        f"[RESULTS] Total execution time: {_total_t_end - _total_t_start:.4f} s", color="green", bold=True
    )

# %%
