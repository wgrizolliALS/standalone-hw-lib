# %%

import time

import keithley_utils as kthu
import pandas as pd
import matplotlib

matplotlib.use("qtagg")
import matplotlib.pyplot as plt

import numpy as np

# %%


def set_curr_range(port, verbose=True, debug=True):
    """Use autorange to find best scale, then turn off autorange to lock it in for the next acquisition."""
    kthu.serial_query(":SENS:CURR:RANG:AUTO ON", port, verbose=verbose, debug=debug)
    time.sleep(0.5)  # Wait for autorange to settle
    sens_curr_range = kthu.serial_query(":SENS:CURR:RANG?", port, verbose=verbose, debug=debug)

    kthu.serial_query(":SENS:CURR:RANG:AUTO OFF", port, verbose=verbose, debug=debug)
    return sens_curr_range


def setup_waveform_acquisition(sport, num_points=60, nplc=1.0, curr_range=2e-7, verbose=True, debug=True):
    setup_recipe = [
        "*RST",  # Reset the instrument to a known state
        ":SYST:AZERO 0; :SYST:ZCH OFF",  # Turn off auto-zero and zero check for faster measurements (but more noise)
        ":FORM:ELEM READ,TIME",  # Configure the data format to return both the reading and the timestamp for each point
        f":SENS:CURR:RANG {curr_range}",  # Set the current range
        f":SYST:ZCH OFF; :CURR:NPLC {nplc}; :TRAC:POIN {num_points}; :TRIG:COUN {num_points}; :SYST:TIME:RES; :TRAC:FEED:CONT NEXT",  # Configure the acquisition parameters: turn off zero check, set NPLC, number of points, trigger count, and prepare the trace buffer for the next acquisition
    ]
    for cmd in setup_recipe:
        _ = kthu.serial_query(cmd, sport, verbose=verbose, debug=debug)
        time.sleep(0.1)


def acq_waveform(sport, raw=False, reset_timer=False, verbose=True, debug=True):

    print("[INFO] Querying data...")

    _time_init = time.time()

    if reset_timer:
        kthu.serial_query(":SYST:TIME:RES", sport, verbose=verbose, debug=debug)
        print("[INFO] Timer reset with :SYST:TIME:RES command.")

    read_res = kthu.serial_query("INIT", sport, verbose=verbose, debug=debug)

    while True:
        read_res = kthu.serial_query("*OPC?", sport, wait_serial=True, verbose=verbose, debug=debug)
        if read_res == "1":
            print("[INFO] Acquisition complete.")
            break
        else:
            print(
                "[INFO] Waiting for acquisition to complete... {:.3f} seconds elapsed".format(time.time() - _time_init)
            )
            time.sleep(0.5)

    print("[INFO] Acquisition COMPLETED. ")
    print("[INFO] DOWLOADING DATA from device...")
    read_res = kthu.serial_query(":TRAC:DATA?", sport, verbose=verbose, debug=debug)

    print("[INFO] Querying COMPLETED. Data received.")
    kthu.print_verbose(read_res, verbose=debug)
    print(f"[INFO] Raw data length: {read_res.count(',') + 1} data points")  # type: ignore
    if raw:
        return read_res
    else:
        # 1. Split and convert to a flat list of floats
        full_list = [float(x) for x in read_res.split(",")]  # type: ignore

        # 2. Use list slicing to separate the pairs
        # [start:stop:step]
        currents = full_list[0::2]  # Start at 0, take every 2nd element
        times = full_list[1::2]  # Start at 1, take every 2nd element

        # 3. Create the DataFrame directly from a dictionary
        df = pd.DataFrame({"Current_A": currents, "Time_S": times})
        return df


# %%
if __name__ == "__main__":
    # %%

    print("\n### Scan for Keithleys ###")
    try:
        devs = kthu.detect_keithley_devices(baudrate=None, verbose=True)
        print("# Scan for hardware ENDED #\n")

    except Exception as e:
        print(f"Error during Keithley detection: {e}")
    # %%

    dev = devs[0] if devs else None

    SERIALPORT = dev["port"] if dev else None  # type: ignore

    # %%
    _time_Stats = []
    for NPLC in [10.0, 1.0, 0.1, 0.01]:
        setup_waveform_acquisition(SERIALPORT, num_points=10, nplc=NPLC, curr_range=2e-7, verbose=True, debug=True)

        _waveform = acq_waveform(SERIALPORT, verbose=False, debug=False)

        _time_diffs = np.diff(_waveform["Time_S"])
        _time_Stats.append([NPLC, _time_diffs.mean(), _time_diffs.max(), _time_diffs.min()])

    # %%

    _mess2print = ""

    for NPLC, mean_diff, max_diff, min_diff in _time_Stats:
        _mess2print += f"{NPLC:^10.2f}|"
        _mess2print += f"{f'{(NPLC * 1000 / 60.0):.3f} ms':^25}|"
        _mess2print += f"{f'{(mean_diff * 1e3):.3f} ms':^25}|"
        _mess2print += f"{f'{((mean_diff - NPLC * 1 / 60.0) * 1e3):.3f} ms':^15}|"
        _mess2print += f"{f'{((max_diff - NPLC * 1 / 60.0) * 1e3):.3f} ms':^15}|"
        _mess2print += f"{f'{((min_diff - NPLC * 1 / 60.0) * 1e3):.3f} ms':^15}|"
        _mess2print += "\n"

    print("=" * 95)
    print(
        f"{'NPLC':^10}|{'Int. Time from NPLC':^25}|{'Mean Time Between Points':^25}|{'Mean Dead Time':^15}|{'Max Dead Time':^15}|{'Min Dead Time':^15}|"
    )
    print("-" * 95)
    print(_mess2print)
    print("=" * 95)

    # %%
    print(f"\n[INFO] Mean time differences between measurements: {_time_diffs.mean():.4f} seconds")
    # %%

    _waveform.plot(
        x="Time_S",
        y="Current_A",
        title="Keithley 6514 Burst Acquisition",
        xlabel="Time (s)",
        ylabel="Current (A)",
        grid=True,
        marker=".",
    )
    plt.show()

    # %%
    _time_diffs = np.unique(np.diff(_waveform["Time_S"]))

    plt.figure()
    plt.hist(_time_diffs, bins=101, edgecolor="darkgray")
    plt.title("Histogram of Time Differences Between Measurements")
    plt.xlabel("Time Difference (s)")
    plt.ylabel("Frequency")
    plt.grid(True)
    plt.show()
# %%
