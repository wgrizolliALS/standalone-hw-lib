# %%

import time

import keithley_utils as kthu
import serial


# %%
def read_waveform(dev, num_points=100, total_time=1.0, curr_range=2e-7):
    pass


# %%
if __name__ == "__main__":
    # %%

    print("\n### Scan for Keithleys ###")
    try:
        devs = kthu.detect_keithley_devices(baudrate=None, verbose=True)
        print("# Scan ENDED #\n")

    except Exception as e:
        print(f"Error during Keithley detection: {e}")
    # %%

    dev = devs[0] if devs else None
    # %%

    foo = read_waveform(dev, num_points=10, total_time=1.0, curr_range=2e-7)
# %%
