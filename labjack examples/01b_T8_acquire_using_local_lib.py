"""
Example of using the LabJack LJM library to acquire data from a LabJack device using a local utility library.

This example demonstrates how to:
- Use the `labjack_utils` (lju) helper module to simplify device interaction.
- Open a connection to a LabJack T8.
- Read channel resolutions.
- Acquire high-speed streaming data using a simplified wrapper function.
- Process and visualize the results using Plotly for interactive graphing.

The `acquire_dataT8` function handles the stream setup, data buffering, and cleanup
automatically, returning a structured numpy array with timestamps.

"""

from labjack import ljm
import plotly.graph_objects as go

import labjack_utils as lju


print("\n### labjack python library version: " + ljm.__version__ + " ###\n")

if __name__ == "__main__":
    try:
        # Open a connection to the first available LabJack device
        handle = ljm.openS("ANY", "ANY", "ANY")

    except Exception as e:
        print("No LabJack devices found.")
        print(f"Error: {e}")

    handle = None
    try:
        # List available devices
        print("### Searching for connected Devices...")
        res = ljm.listAllS("ANY", "ANY")
        num_devices = res[0]

        print(f"*** Devices found: {num_devices}")

        handle = ljm.openS("ANY", "ANY", "ANY")
        info = ljm.getHandleInfo(handle)
        print("\n*** Handle info:")
        print(
            f"Device type: {info[0]}, Connection: {info[1]}, Serial: {info[2]}, IP: {info[3]}, Port: {info[4]}"
        )

        print("\n*** Channels Resolution:")

        resol_channels = lju.get_channels_res(handle)

        print("\n###### START Acquisition ######")
        data = lju.acquire_dataT8(
            handle, num_samples=1000, sample_rate=1000, channels=["AIN0", "AIN1"]
        )
        print("\n###### END of Acquisition ######\n")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if handle:
            ljm.close(handle)
            print("***Closed connection with labjack.")

    if data is not None:
        print("\n###### Post Processing ######")
        print(f"*** Acquired {data.shape[0]} samples in {data.shape[1] - 1} Channels.")
        print("Print the first 10 samples for verification")
        print(data[:10])  # Print the first 10 samples for verification

        # Plot data with plotly
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
        #   fig.show() # this will open the figure in a web browser
        print(f"\n*** Plot saved to .\\{html_file}\n")
