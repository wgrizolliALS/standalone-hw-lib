# %%

import time

import keithley_utils as kthu
import pandas as pd
import matplotlib

matplotlib.use("qtagg")
import matplotlib.pyplot as plt


# %%


def setup_waveform_acquisition(sport, num_points=60, nplc=1.0, curr_range=2e-7, verbose=True, debug=True):
    setup_recipe = [
        "*RST",
        ":FORM:ELEM READ,TIME",
        f":SYST:ZCH OFF; :CURR:NPLC {nplc}; :TRAC:POIN {num_points}; :TRIG:COUN {num_points}; :SYST:TIME:RES; :TRAC:FEED:CONT NEXT",
    ]
    for cmd in setup_recipe:
        _ = kthu.serial_query(cmd, sport, verbose=verbose, debug=debug)
        time.sleep(0.1)


def acq_waveform(sport, raw=False, verbose=True, debug=True):

    print("[INFO] Querying data...")

    _time_init = time.time()
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

    setup_waveform_acquisition(SERIALPORT, num_points=60, nplc=1.0, curr_range=2e-7, verbose=True, debug=True)

    # %%
    _waveform = acq_waveform(SERIALPORT, verbose=False, debug=False)
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
