# %%

import keithley_utils as kthu
import pandas as pd

# %%
import matplotlib

matplotlib.use("qtagg")
# print(matplotlib.backends.backend_registry.list_builtin())
# matplotlib.use("widget")
import matplotlib.pyplot as plt

import time
# %%

devs = kthu.detect_keithley_devices(baudrate=None, verbose=True)

if devs is None:
    print("[ERROR] : No Keithley devices found. Exiting.")
    exit(1)

# %%

dev = devs[0] if devs else None
print("[INFO] Using device:")
kthu.print_keithley_properties(dev)

SERIALPORT = dev["port"]  # type: ignore
# %%
_ = kthu.serial_query(":CONF?", SERIALPORT, verbose=True)

# %%

SETUP_RECIPE = [
    "*RST",
    ":FORM:ELEM READ,TIME",
    ":SYST:ZCH OFF; :CURR:NPLC 1.0; :TRAC:POIN 100; :TRIG:COUN 100; :SYST:TIME:RES; :TRAC:FEED:CONT NEXT",
]

for cmd in SETUP_RECIPE:
    _ = kthu.serial_query(cmd, SERIALPORT, verbose=True, debug=True)
    time.sleep(0.1)

# %%

print("[INFO] Querying data...")

_time_init = time.time()
CMD = "INIT"
read_res = kthu.serial_query(CMD, SERIALPORT, verbose=True, debug=True)

#
CMD = "*OPC?"
# CMD = "*OPC"

while True:
    read_res = kthu.serial_query(CMD, SERIALPORT, wait_serial=True, verbose=True, debug=True)
    if read_res == "1":
        print("[INFO] Acquisition complete.")
        break
    else:
        print("[INFO] Waiting for acquisition to complete... {:.3f} seconds elapsed".format(time.time() - _time_init))
        time.sleep(0.5)


print("[INFO] Acquisition COMPLETED. ")
print("[INFO] DOWLOADING DATA from device...")
CMD = ":TRAC:DATA?"
read_res = kthu.serial_query(CMD, SERIALPORT, verbose=True, debug=True)

print("[INFO] Querying COMPLETED. Data received:")
print("Measurement:", read_res)
print(f"Raw data length: {read_res.count(',') + 1} data points")  # type: ignore

# %% Retrieve data and parse into DataFrame
# 1. Split and convert to a flat list of floats
full_list = [float(x) for x in read_res.split(",")]  # type: ignore

# 2. Use list slicing to separate the pairs
# [start:stop:step]
currents = full_list[0::2]  # Start at 0, take every 2nd element
times = full_list[1::2]  # Start at 1, take every 2nd element

# 3. Create the DataFrame directly from a dictionary
df = pd.DataFrame({"Current_A": currents, "Time_S": times})

# %%

df.info()

# %%

df.plot(
    x="Time_S",
    y="Current_A",
    title="Keithley 6514 Burst Acquisition",
    xlabel="Time (s)",
    ylabel="Current (A)",
    grid=True,
    marker=".",
)
plt.show(block=True)
