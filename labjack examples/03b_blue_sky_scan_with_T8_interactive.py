"""
Bluesky Scan with LabJack T8 Multi-Channel Detector
This module demonstrates how to use the LabJackMultiChannelDetector with Bluesky to
perform a scan while recording data from multiple channels of the LabJack T8 device.
The workflow includes:
1. Initializing a RunEngine with the BestEffortCallback for real-time data visualization
2. Creating a LabJackMultiChannelDetector instance configured for channels 0, 1, and 2
3. Subscribing the detector's internal CSV saver to the RunEngine for automatic data logging
4. Executing a scan plan that moves a simulated motor from -5 to 5 in 11 steps while
    collecting detector data at each position
5. Properly closing the detector connection in a finally block to ensure resource cleanup
Key Features:
- Multi-channel data acquisition from LabJack T8 hardware
- Automatic CSV data export during scan execution
- Integration with Bluesky's scan plan infrastructure
- Ensures proper hardware resource management
Dependencies:
- bluesky: Experimental control framework
- ophyd: Control layer for hardware devices
- ophyd_local_labjack: Custom LabJack integration module
"""

# %%
import matplotlib
import numpy as np

# print(matplotlib.backends.backend_registry.list_builtin())
matplotlib.use("qtagg")
# matplotlib.use("ipympl")  # For Jupyter notebooks, use the interactive backend
import matplotlib.pyplot as plt  # noqa: E402
# show current backend


# %%
from bluesky import RunEngine  # type: ignore
from bluesky.plans import scan, count  # type: ignore  # noqa: F401
from bluesky.callbacks.best_effort import BestEffortCallback
from ophyd.sim import motor  # type: ignore
# from standalone_hw.labjack import LabJackT8

from ophyd_labjack_t8 import LabJackT8
from databroker import Broker


# %% Change plot style and parameters

print("Current Matplotlib backend:", matplotlib.get_backend())  # type: ignore
plt.style.use("default")

params = {
    "font.size": 10,
    "legend.fontsize": "small",
    "font.family": "serif",
    "figure.facecolor": "white",
    "axes.grid": True,
    "figure.autolayout": True,
    "axes.grid.axis": "both",
    "mathtext.fontset": "stix",
    "figure.dpi": 100,
    "savefig.dpi": 300,
    "figure.figsize": (6, 5),
    "image.origin": "lower",
    "image.interpolation": "none",
    "image.cmap": "magma",
    "lines.marker": "o",
    "lines.linestyle": "-",
}

plt.rcParams.update(params)

print("[Hi THERE 1]")
# %%
# Initialize Bluesky
print("[Hi THERE 2]")
RE = RunEngine({})
RE.subscribe(BestEffortCallback())
print("[Hi THERE 3]")

# %% Initialize Hardware

print("[Hi THERE 4]")

t8 = LabJackT8(name="t8", channels=[0, 1, 2, 4], act_time=2.0, sample_rate=10, verbose=True)


print("[Hi THERE 5]")

# %%
# Link the internal saver
RE.subscribe(t8.csv_saver)


# %%
# Initialize databroker (make sure you have configured a named broker, e.g. 'temp')
db = Broker.named("temp")
RE.subscribe(db.insert)

# %%
plt.ion()
plt.close("all")
# %% SCAN EXECUTION
try:
    # run a scan and capture uid
    uid = RE(scan([t8], motor, -5, 5, 5))  # type: ignore # blocks until complete

    print("Scan finished. uid:", uid)
    plt.show(block=False)
except Exception as e:
    print("## Error during scan execution!!! ###")
    print(f"Error during scan execution: {e}")

# %% Post Processing
# # Read back from databroker
run = db[uid][0]  # or db[-1]


# %%
df = run.table()

df = df.set_index("time")
df["seconds"] = df.index.astype("int64") / 1_000_000_000.0  # convert from nanoseconds to seconds
# %%
# events = list(run.events())
# # times = [ev['time'] for ev in events]
# # build DataFrame excluding t8_raw_block
# rows = []
# for ev in events:
#     d = ev['data'].copy()
#     d.pop('t8_raw_block', None)   # drop the field
#     d['time'] = ev['time']
#     rows.append(d)

# df2 = pd.DataFrame(rows)   # contains t8_ain0, motor, motor_setpoint, time

df.plot(x="seconds", y=["t8_ain0", "t8_ain1", "t8_ain2", "t8_ain4"], marker="o")
plt.xlabel("Time (s)")
plt.show()


# %%
_data2plot = np.asarray(df["t8_raw_block"].iloc[0])
_data2plot[:, 0] -= _data2plot[0, 0]
# normalize time to start at zero. Note that here is in seconds, not nanoseconds

# %%
plt.figure()

for i in range(1, _data2plot.shape[1]):
    print(
        f"Column {i} - min: {_data2plot[:, i].min():.4f}, max: {_data2plot[:, i].max():.4f}, mean: {_data2plot[:, i].mean():.4f}"
    )
    plt.plot(
        _data2plot[:, 0], _data2plot[:, i] - np.mean(_data2plot[:, i]), ".-", label=f"Column {i}"
    )  # plot time vs each channel, subtract mean for better visualization

plt.xlabel("Time (s)")
plt.ylabel("Voltage (V)")
plt.title("Raw T8 Block Data")
plt.legend()
plt.show()

# %%


if False:
    t8.close()
# %%
