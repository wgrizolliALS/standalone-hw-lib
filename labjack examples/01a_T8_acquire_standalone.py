"""
Example of using the LabJack LJM library to acquire data from a LabJack device.

This example demonstrates how to:
- List connected LabJack devices
- Open a connection to the first available device
- Acquire streaming data from specified channels
- Handle exceptions and ensure proper cleanup
Make sure to have the LabJack LJM library installed and a compatible LabJack device connected to run this example.

**Note 1**: Adjust the acquisition parameters (channels, sample rate, etc.) as needed for your specific use case and device capabilities.

**Note 2**: This is uses only the LJM library, which is the recommended way to interface with LabJack devices in Python. There is also a lower-level library called LJME that can be used for more direct control, but LJM provides a more user-friendly API and is generally sufficient for most applications.

**Note 3**: No use of ophyd or bluesky in this example, as it focuses on direct interaction with the LabJack device using the LJM library. For integration with ophyd/bluesky, see other examples in this project.

"""


# %%
from labjack import ljm
import numpy as np
import time

print('\n### labjack python library version: ' + ljm.__version__ + ' ###\n')

# %% List devices

res = ljm.listAllS("ANY", "ANY")
print("Devices found:")
for i in range(res[0]):
    print(f"Device {i}: {res[1][i]}, Connection: {res[2][i]}, Serial: {res[3][i]}, IP: {res[4][i]},")

# %% Open first device

try:
    handle = ljm.openS("ANY", "ANY", "ANY")
    print("Opened connection.")
except Exception as e:
    print("Failed to open device:", e)
    raise SystemExit

try:
    info = ljm.getHandleInfo(handle)
    print("\nHandle info:")
    print(f"Device type: {info[0]}, Connection: {info[1]}, Serial: {info[2]}, IP: {info[3]}, Port: {info[4]}")
except Exception as e:
    print("Failed getHandleInfo:", e)
    ljm.close(handle)
    raise SystemExit

# %% Acquisition
# ----- Acquisition parameters -----
num_samples = 40_000        # total scans you want
sample_rate = 40_000        # Hz, ma
channels = ["AIN0", "AIN1", "AIN2", "AIN4", "AIN5"] 
# channels = ["AIN0"]  # use names to avoid ambiguity
scans_per_read = 256       # chunk size per eStreamRead (reasonable default)
timeout_sec = 5.0         # safety timeout for acquisition
# ----------------------------------

try:
    # map names to addresses
    aAddresses, aTypes = ljm.namesToAddresses(len(channels), channels)
    num_ch = len(aAddresses)
    print("Channels:", channels)
    print("aAddresses:", aAddresses)
    print("aTypes:", aTypes)

    # start stream
    actual_rate = ljm.eStreamStart(handle, scans_per_read, num_ch, aAddresses, sample_rate)
    print(f"eStreamStart returned actual_rate={actual_rate}")

    all_flat = []
    start_t = time.time()
    scan_interval = 1.0 / actual_rate  # time between scans in seconds
    
    while True:
        # Check completion conditions
        scans_collected = len(all_flat) // num_ch
        if scans_collected >= num_samples:
            break
        
        elapsed = time.time() - start_t
        if elapsed >= timeout_sec:
            print(f"Timeout reached ({elapsed:.2f}s)")
            break
        
        # Read and accumulate data
        ret = ljm.eStreamRead(handle)
        if ret and ret[0]:
            all_flat.extend(ret[0])
        else:
            time.sleep(0.001)

    # stop stream
    ljm.eStreamStop(handle)

    # convert to numpy, trim partial tail, reshape
    flat = np.asarray(all_flat, dtype=float)
    n_rows = flat.size // num_ch
    if n_rows == 0:
        raise RuntimeError("No complete scans received.")
    flat = flat[:n_rows * num_ch]
    data = flat.reshape(n_rows, num_ch)

    # If you asked for a specific total, trim/keep only the requested scans
    if data.shape[0] > num_samples:
        data = data[:num_samples, :]

    # Generate timestamps for each scan
    times = np.arange(data.shape[0]) * scan_interval
    
    # Combine times with data
    data = np.hstack([times.reshape(-1, 1), data])

    print(f"Collected {data.shape[0]} scans × {data.shape[1]-1} channels (+ time column)")
    print(f"Time range: {times[0]:.6f} to {times[-1]:.6f} seconds (session time)")
    print(data[:10])  # preview first 10 rows

except Exception as e:
    print("Acquisition error:", e)
    try:
        ljm.eStreamStop(handle)
    except Exception:
        pass
    raise


# %% Close connection
try:
      ljm.close(handle)
      print("Closed connection.")
except Exception as e:
      print("Close error:", e)

print("\n### Acquisition complete ###\n")
print(f"Aquired {data.shape[0]} samples with {data.shape[1]-1} channels in {times[-1]:.6f} seconds at {actual_rate:.2f} Hz.\n")

print(f"Total sctripts execution time: {time.time() - start_t:.2f} seconds\n")
