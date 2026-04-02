"""
Example of using the LabJack LJM library to acquire data from a LabJack device using a labjack_utils library.

This example demonstrates how to:
1. List connected LabJack devices.
2. Open a connection to the first available device.
3. Configure and start a streaming acquisition from specified analog input channels using a labjack_utils function.
4. Collect and store the acquired data in a NumPy array.



"""

import time

from labjack import ljm
import plotly.graph_objects as go

import labjack_utils as lju


print("\n[INFO] ### labjack python library version: " + ljm.__version__ + " ###")

if __name__ == "__main__":
    start_t = time.time()

    # List devices and open connection
    try:
        # Open a connection to the first available LabJack device
        handle = ljm.openS("ANY", "ANY", "ANY")

    except Exception as e:
        print("[ERROR] No LabJack devices found.")
        print(f"Error: {e}")

    handle = None

    # main try block for acquisition and processing
    try:
        # List available devices
        print("[INFO] ### Searching for connected Devices...")
        res = ljm.listAllS("ANY", "ANY")
        num_devices = res[0]

        print(f"[INFO] Devices found: {num_devices}")

        handle = ljm.openS("ANY", "ANY", "ANY")
        info = ljm.getHandleInfo(handle)
        print("[INFO] Device info from handle:")
        print(
            f"[INFO] Device type: {info[0]}, Connection: {info[1]}, Serial: {info[2]}, IP: {info[3]}, Port: {info[4]}"
        )

        print("[INFO] GET Channels Resolution:")

        resol_channels = lju.get_channels_res(handle)
        print("[INFO] get_channels_res() :")
        print("[INFO] : ", resol_channels)

        print("\n[INFO] Acquisition STARTED.")
        data, data_info = lju.acquire_dataT8(
            handle, num_samples=1000, sample_rate=1000, channels=["AIN0", "AIN1"]
        )

        print("\n[INFO] Acquisition ENDED.")
        print("[INFO] Acquisition Info:")
        for key, value in data_info.items():
            print(f"\t- {key}: {value}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if handle:
            ljm.close(handle)
            print("[INFO] Closed connection with labjack.")

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
        html_file = "labjack_acquisition_plot.html"
        fig.write_html(html_file)
        fig.show()  # this will open the figure in a web browser
        print(f"[POSTPROCESSING] Plot saved to .\\{html_file}\n")

    print(f"[INFO] Total scripts execution time: {time.time() - start_t:.2f} seconds\n")
