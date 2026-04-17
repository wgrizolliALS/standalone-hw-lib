"""
This is a standalone example of acquiring data from a LabJack T8 device using the
LJM library in Python. It demonstrates how to:
1. List connected LabJack devices.
2. Open a connection to the first available device.
3. Configure and start a streaming acquisition from specified analog input channels.
4. Collect and store the acquired data in a NumPy array.

**Note 1**: Adjust the acquisition parameters (channels, sample rate, etc.) as needed
for your specific use case and device capabilities.

**Note 2**: This is uses only the LJM library, which is the recommended way to
interface with LabJack devices in Python. There is also a lower-level library called
LJME that can be used for more direct control, but LJM provides a more user-friendly
API and is generally sufficient for most applications.

**Note 3**: No use of ophyd or bluesky in this example, as it focuses on direct
interaction with the LabJack device using the LJM library. For integration with
ophyd/bluesky, see other examples in this project.

"""

# %% Import libraries

from labjack import ljm
import numpy as np
import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go


def datenow_str():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def check_out_of_range(flat_data: list, actual_range: list, verbose: bool = True):
    """
    Checks for out-of-range values in the acquired data and prints warnings if any are found.

    Parameters
    ----------
    flat_data : list
        A flat list of acquired data values, as provided by ljm.eStreamRead(handle), that are ordered by channel (e.g., [ch1_scan1, ch2_scan1, ch3_scan1, ch1_scan2, ch2_scan2, ...]).
    actual_range : list
        A list of actual voltage ranges for each channel (e.g., [±11, ±9.6, ±4.8, ...]).

    See also
    --------
    Ranges and actual ranges are listed at https://support.labjack.com/docs/a-3-3-3-t8-signal-range-t-series-datasheet

    """

    _ncurves = len(actual_range)

    _out_of_range = []

    for _i in range(_ncurves):
        _ch_data = flat_data[_i::_ncurves]  # extract data for this channel
        _max_abs = max(abs(np.array(_ch_data)))
        if _max_abs > actual_range[_i]:
            if verbose:
                print(
                    f"[WARNING] OUT-OF-RANGE: {channels[_i]} max absolute value {_max_abs:.3f} V is higher than actual channel range of ±{actual_range[_i]:.3f} V."
                )
            _out_of_range.append(True)

        else:
            if verbose:
                print(f"[INFO] {channels[_i]} is within the expected range of ±{actual_range[_i]:.3f} V.")
            _out_of_range.append(False)

    return _out_of_range


start_t = time.time()

print("\n[INFO] ### labjack python library version: " + ljm.__version__ + " ###")

# %% List devices
print("\n[INFO] ### Searching for connected Devices...")
res = ljm.listAllS("ANY", "ANY")
print(f"[INFO] Devices found: {res[0]}")
for i in range(res[0]):
    print(f"\t- Device {i}: {res[1][i]}, Connection: {res[2][i]}, Serial: {res[3][i]}, IP: {res[4][i]},")

if False:  # set to True to stop here and inspect the device list before proceeding
    print("\n[INFO] Raw results from ljm.listAllS('ANY', 'ANY'):")
    print(res)

# %% Opening connection to device with Serial number

_serial_to_connection = res[3][0]  # open by serial number
print(f"\n[INFO] Opening connection to device with Serial: {_serial_to_connection}.")
handle = ljm.openS("ANY", "ANY", _serial_to_connection)  # open by serial number
print("[INFO] Opened connection.")

info = ljm.getHandleInfo(handle)
print("[INFO] Device info from handle:")
print(f"[INFO] Device type: {info[0]}, Connection: {info[1]}, Serial: {info[2]}, IP: {info[3]}, Port: {info[4]}")

# %% Acquisition parameters
num_samples = 40_000  # total scans you want
sample_rate = 40_000  # Hz, The T8 has a maximum scan rate of 40 ksamples/second. Unlike other T-series devices, the scan rate does not depend on how many addresses are sampled per scan since all analog inputs are sampled simultaneously.
channels = ["AIN0", "AIN1", "AIN2", "AIN4", "AIN5"]
# ranges_per_channel = [10.0] * len(channels)  # set all channels to ±10V range
ranges_per_channel = [10.0, 10.0, 3.0, 1.0, 0.010]  # set each channel to a specific range
# channels = ["AIN0"]  # use names to avoid ambiguity
scans_per_read = 256  # chunk size per eStreamRead (reasonable default)
timeout_sec = 5.0  # safety timeout for acquisition
# ----------------------------------

# %% Set the range for each channel. This is important to ensure you get the best resolution for your expected signal levels.
actual_range = []
for i, ch in enumerate(channels):
    print(f"[INFO] Setting range for channel {ch} to ±{ranges_per_channel[i]} V")
    ljm.eWriteName(handle, f"{ch}_RANGE", ranges_per_channel[i])

    actual_range.append(ljm.eReadName(handle, f"{ch}_RANGE"))
    print(f"[INFO] Actual range set for {ch}: ±{actual_range[-1]:.6f} V")

# AIN range options for T8 (from LabJack documentation):
# Ranges are: ±11 V, ±9.6 V, ±4.8 V, ±2.4 V, ±1.2 V,
#             ±0.6 V, ±0.3 V, ±0.15 V,
#             ±0.075 V, ±0.036 V, ±0.018 V

print(f"\n[INFO] Requesting {num_samples} scans at {sample_rate} Hz from {num_ch} channels...")
# %% map names to addresses. Needed for streaming API. Also get types for reference.
aAddresses, aTypes = ljm.namesToAddresses(len(channels), channels)
num_ch = len(aAddresses)

print("\n[INFO] Channels info:")
print("\t- Channels:", channels)
print("\t- aAddresses:", aAddresses)
print("\t- aTypes:", aTypes)
# reference for aTypes:https://support.labjack.com/docs/ewriteaddresses-ljm-user-s-guide#aTypes-[in]
# Values according to LJM library constants:
# 0 = UINT16, 1 = UINT32, 2 = INT32, 3 = FLOAT32, 98 = STRING, 99 = BYTE


# %% start stream
print(f"\n[INFO] Requesting {num_samples} scans at {sample_rate} Hz from {num_ch} channels...\n")

start_t = time.time()
actual_rate = ljm.eStreamStart(handle, scans_per_read, num_ch, aAddresses, sample_rate)
print(f"[INFO] eStreamStart STARTED. Requested rate: {sample_rate} Hz, Actual rate: {actual_rate:.2f} Hz")

all_flat = []
scan_interval = 1.0 / actual_rate  # time between scans in seconds

while True:
    # Check completion conditions
    scans_collected = len(all_flat) // num_ch
    if scans_collected >= num_samples:
        break
        # note that in the streaming API, the actual acquisition continues until we stop it. Numbers are saved in the buffer and we can read them out in chunks. So we just keep reading until we have enough samples, then stop the stream. Also nte that we dont know the timestamp, only the actual_rate.

    elapsed = time.time() - start_t
    if elapsed >= timeout_sec:
        print(f"[WARNING] Timeout reached ({elapsed:.2f}s)")
        break

    # Read and accumulate data
    # print(
    #     f"[INFO] Reading stream data... Scans collected so far: {scans_collected}. Time elapsed: {elapsed * 1000:.3f} ms"
    # )

    ret = ljm.eStreamRead(handle)
    if ret and ret[0]:
        all_flat.extend(ret[0])

    time.sleep(0.0001)

elapsed = time.time() - start_t

print("\n[INFO] eStreamStart ENDED. ")
# stop stream
ljm.eStreamStop(handle)
print("[INFO] eStreamStart STOPPED. ")

print("\n[INFO] Checking for out-of-range values...")

if any(check_out_of_range(all_flat, actual_range)):
    print("[WARNING] Some values are out of range!")


print(f"\n[INFO] Total scans requested: {num_samples}, collected: {scans_collected}")

print(f"[INFO] Requested rate: {sample_rate} Hz, Actual rate: {actual_rate:.2f} Hz")
print(
    f"[INFO] Elapsed computer time: {elapsed:.3f} s. Acquisition time: {scans_collected * scan_interval:.3f} s (based on actual rate)."
)


# %% convert to numpy, trim partial tail, reshape

_arr_data = np.asarray(all_flat, dtype=float).reshape(scans_collected, num_ch)
# If you asked for a specific total, trim/keep only the requested scans
if _arr_data.shape[0] > num_samples:
    _arr_data = _arr_data[:num_samples, :]

# Generate timestamps for each scan
times = np.arange(_arr_data.shape[0]) * scan_interval

# Combine times with data
_arr_data = np.hstack([times.reshape(-1, 1), _arr_data])

print(f"[INFO] Collected {_arr_data.shape[0]} scans x {_arr_data.shape[1] - 1} channels (+ time column)")
print(f"[INFO] Time range: {times[0]:.6f} to {times[-1]:.6f} seconds (session time)")


df = pd.DataFrame(_arr_data, columns=["Time"] + channels)
# %%

df = pd.DataFrame(_arr_data, columns=["Time"] + channels)
_arr_data = None
df.head()


# %% Post processing and visualization
print("\n[POSTPROCESSING] Post Processing STARTED")


print("\n[POSTPROCESSING] Plotting data with Plotly...")
fig = go.Figure()
times = df["Time"]
for i in range(1, df.shape[1]):
    fig.add_trace(go.Scatter(x=times, y=df.iloc[:, i], mode="lines", name=f"{df.columns[i]}"))

fig.update_layout(
    title="LabJack Data Acquisition",
    xaxis_title="Time (s)",
    yaxis_title="Voltage (V)",
    hovermode="x unified",
    template="plotly",
)
# Save HTML and open in VS Code webview
html_file = f"Results\\{datenow_str()}_labjack_acquisition_plot.html"
fig.write_html(html_file)
fig.show()  # this will open the figure in a web browser
print(f"[POSTPROCESSING] Plot saved to .\\{html_file}\n")

# %% Close connection
try:
    ljm.close(handle)
    print("[INFO] Closed connection to hardware.")
except Exception as e:
    print("[ERROR] Close error:", e)

print("\n[INFO] ### Acquisition complete ###\n")

print(f"[INFO] Total scripts execution time: {time.time() - start_t:.2f} seconds\n")

# %%
