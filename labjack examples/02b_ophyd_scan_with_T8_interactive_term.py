"""
This script provides a standalone test for the LabJackMultiChannelDetector class using Ophyd.
It demonstrates:
1. How to define a custom Ophyd Device for the LabJack T8.
2. How to implement an asynchronous trigger using Python threading.
3. How to handle both real hardware connections via LJM and simulated data.
4. A manual execution loop that triggers the device and reads back the averaged results.

This is useful for verifying hardware communication and Ophyd signal logic before 
integrating the device into a full Bluesky RunEngine scan.


"""

# %%
import time
from labjack import ljm
from numpy import isin

# --- THE DETECTOR CLASS ---
from ophyd_labjack_t8 import LabJackT8

#%%

print("[MAIN SCRIPT INFO] Starting Standalone Detector Test...")
det = LabJackT8(name="test_lj", channels=[0, 1],
                act_time=1.0,
                sample_rate=100,
                verbose=True)

# %%

status = det.trigger()

# Wait for the trigger to finish
count = 0
while not status.done:
    time.sleep(0.5)
    count += 1
    if count > 10: # Safety timeout
        print("  Timeout: Status never marked as done!")
        break

# Check values
readings = det.read()
for key, val in readings.items():
    try:
        print(f"[Result] {key}: 10 first rows of array:\n{val['value'][:10]}")
    except:
        print(f"[Result] {key}: {val['value']}")

# %%

if det.handle:
    # ljm.close(det.handle)
    det.close()


# %% POST PROCESSING
import matplotlib.pyplot as plt
import numpy as np

_raw_wvf = readings['test_lj_raw_block']['value']
plt.figure()
plt.plot(_raw_wvf[:, 0]-_raw_wvf[0, 0],
         _raw_wvf[:, 1]-np.mean(_raw_wvf[:, 1]))
plt.plot(_raw_wvf[:, 0]-_raw_wvf[0, 0],
         _raw_wvf[:, 2]-np.mean(_raw_wvf[:, 2]))
plt.show(block=True)

# %%

print("\n[MAIN SCRIPT INFO] Test Complete.\n")

# %%
