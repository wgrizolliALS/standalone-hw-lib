""" """

# %%
import time

import matplotlib

# --- THE DETECTOR CLASS ---
from ophyd_labjack_t8 import LabJackT8

# %%

print("[INFO] Starting Detector Test with Ophyd...")
det = LabJackT8(name="test_lj", channels=[0, 1], act_time=1.0, sample_rate=100, verbose=True)
print("[INFO] ophyd LabJackT8 instance created with channels: ", det.active_channels)

# %%
print("[INFO] Triggering the detector...")
status = det.trigger()
print("[INFO] Detector triggered, waiting for acquisition to complete...")

# Wait for the trigger to finish
count = 0
while not status.done:
    time.sleep(0.5)
    count += 1
    if count > 10:  # Safety timeout
        print("[TIMEOUT] Status never marked as done!")
        break

# Check values
readings = det.read()
for key, val in readings.items():
    try:
        print(f"[Result] {key}: 10 first rows of array:\n{val['value'][:10]}")  # type: ignore
    except (TypeError, IndexError):
        print(f"[Result] {key}: {val['value']}")  # type: ignore

# %%

if det.handle:
    det.close()
    print("[INFO] Detector connection closed.")


# %% POST PROCESSING
print("\n[POSTPROCESSING] Post Processing STARTED")
import matplotlib.pyplot as plt  # type: ignore
import matplotlib

matplotlib.use("qtagg")

import numpy as np  # type: ignore
# %% PLOT RAW WAVEFORM

_raw_wvf = readings["test_lj_raw_block"]["value"]  # type: ignore

print("\n[POSTPROCESSING] Plotting raw waveform data with Matplotlib...")
plt.figure()
plt.plot(_raw_wvf[:, 0] - _raw_wvf[0, 0], _raw_wvf[:, 1] - np.mean(_raw_wvf[:, 1]))
plt.plot(_raw_wvf[:, 0] - _raw_wvf[0, 0], _raw_wvf[:, 2] - np.mean(_raw_wvf[:, 2]))
plt.show(block=True)

# %%

print("\n[INFO] Test Complete.\n")

# %%
