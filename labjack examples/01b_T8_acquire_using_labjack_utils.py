"""
Example of using the LabJack LJM library to acquire data from a LabJack device using a labjack_utils library.

This example demonstrates how to:
1. List connected LabJack devices.
2. Open a connection to the first available device.
3. Configure and start a streaming acquisition from specified analog input channels using a labjack_utils function.
4. Collect and store the acquired data in a NumPy array.



"""

# %%
import time

from labjack import ljm
import plotly.graph_objects as go

import labjackT8_utils as t8u

from datetime import datetime


def datenow_str():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


print("\n[INFO] ### labjack python library version: " + ljm.__version__ + " ###")


# %%
if __name__ == "__main__":
    # %%
    start_t = time.time()

    # List devices and open connection
    print("[INFO] ### Searching for connected Devices...")
    try:
        # Open a connection to the first available LabJack device
        _devices = t8u.detect_labjacks(verbose=True)
        if not _devices:
            raise Exception("No LabJack devices found.")
        else:
            num_devices = len(_devices)
            print(f"[INFO] Devices found: {num_devices}")

    except Exception as e:
        print("[ERROR] No LabJack devices found.")
        print(f"Error: {e}")
        print("CONTINUE.")

    # %%
    # main try block for acquisition and processing
    try:
        # %% Open connection to the device
        _dev_idx = 0

        print(f"[INFO] Connecting to device index: {_dev_idx} with Serial: {_devices[_dev_idx]['serial']}")

        handle = ljm.openS("ANY", "ANY", _devices[_dev_idx]["serial"])
        info = ljm.getHandleInfo(handle)
        print(
            "[INFO] CONNECTED to Device:"
            + f"Device type: {info[0]}, Connection: {info[1]}, Serial: {info[2]}, IP: {info[3]}, Port: {info[4]}"
        )

        # %% Set channels resolution

        t8u.set_channels_resolution(handle, res_idx=11)

        # %%

        _foo = t8u.get_channel_resolution(handle)

        # %%

        t8u.set_channels_ranges(handle, num_channels=[1, 4], ranges=[1.0, 5.0], check_ranges=True)

        # %%
        ranges_actual = t8u.get_channels_ranges(handle)

        # %% Get devices Info and setup acquisition parameters
        print("[INFO] GET Channels Resolution:")

        resol_channels = t8u.get_channel_resolution(handle)
        print("[INFO] get_channels_res() :")
        print("[INFO] : ", resol_channels)

        # %% Acquire data
        print("\n[INFO] Acquisition STARTED.")
        data, data_info = t8u.acquire_dataT8(handle, num_samples=1000, sample_rate=1000, channels=["AIN0", "AIN1"])

        print("\n[INFO] Acquisition ENDED.")
        print("[INFO] Acquisition Info:")
        for key, value in data_info.items():
            print(f"\t- {key}: {value}")
    # %%
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # %% Close connection
        if handle:
            ljm.close(handle)
            print("[INFO] Closed connection with labjack.")
    # %%
    # Post processing and visualization
    if data is not None:
        print("\n[POSTPROCESSING] Post Processing STARTED")
        print(f"[POSTPROCESSING] Acquired {data.shape[0]} samples in {data.shape[1] - 1} Channels.")
        print("[POSTPROCESSING] Print the first 10 samples for verification")
        print(data[:10], "\n")  # Print the first 10 samples for verification

        # Plot data with plotly

        print("\n[POSTPROCESSING] Plotting data with Plotly...")
        fig = go.Figure()
        times = data[:, 0]
        for i in range(1, data.shape[1]):
            fig.add_trace(go.Scatter(x=times, y=data[:, i], mode="lines", name=f"Channel {i - 1}"))

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

    print(f"[INFO] Total scripts execution time: {time.time() - start_t:.2f} seconds\n")

# %%
