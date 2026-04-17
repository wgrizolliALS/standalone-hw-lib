"""
Utility library for LabJack T8 devices.
Provides helper functions for device discovery, resolution configuration,
and high-speed data acquisition.
"""

# %%
from labjack import ljm

import traceback
import time

import numpy as np


# %%
def detect_labjacks(verbose: bool = False):
    """
    Scans for connected LabJack devices and returns a list of dictionaries
    containing device information.
    """

    devices = []
    try:
        if verbose:
            print("[INFO] detect_labjacks() : Searching for connected Devices...")

        res = ljm.listAllS("ANY", "ANY")
        num_devices = res[0]
        print(f"[INFO] detect_labjacks() : Devices found: {num_devices}")

        for i in range(num_devices):
            device_info = {
                "type": res[1][i],
                "connection": res[2][i],
                "serial": res[3][i],
                "ip": ljm.numberToIP(res[4][i]),
                "port": None,
                "usb_address": None,
            }
            try:
                handle = ljm.openS("ANY", "ANY", device_info["serial"])
                info = ljm.getHandleInfo(handle)
                if len(info) > 4:
                    device_info["port"] = info[4]
                if device_info["connection"] == 1:
                    try:
                        device_info["usb_address"] = ljm.eReadName(handle, "DEVICE_PATH_USB")
                    except Exception as e:
                        # Some devices or connections might not support DEVICE_PATH_USB
                        print(f"[WARN] Could not read USB path for serial {device_info['serial']}: {e}")
                        pass

                ljm.close(handle)

            except ljm.LJMError:
                # Device might be in use or disconnected
                device_info["port"] = "Busy/Error"
            devices.append(device_info)
    except ljm.LJMError as e:
        print(f"[ERROR] Error listing LabJacks: {e}")

    if verbose:
        print_devices(devices)
    return devices


def print_devices(devices):
    """
    Prints a formatted list of detected LabJack devices.
    """

    if not devices:
        print("[INFO]: No LabJack devices found.")
        return
    connection_map = {1: "USB", 2: "ETH", 3: "Wireless"}
    for idx, dev in enumerate(devices):
        conn_name = connection_map.get(dev["connection"], f"Unknown({dev['connection']})")
        port_info = f", Port: {dev['port']}" if dev.get("port") else ""
        usb_info = f", USB Address: {dev['usb_address']}" if dev.get("usb_address") else ""
        print(
            f"[{idx}] Device type: {dev['type']}, Connection: {conn_name}, Serial: {dev['serial']}, IP: {dev['ip']}{port_info}{usb_info}"
        )


def set_DAC_voltage(handle, channel, voltage):
    """
    Sets the voltage for a specified DAC channel.

    Parameters:
    -----------
    handle : int
        Device handle from ljm.openS()
    channel : int
        DAC channel number (e.g., 0 for DAC0)
    voltage : float
        Desired voltage to set (within the device's DAC range)

    Returns:
    --------
    success : bool
        True if the voltage was set successfully, False otherwise.
    """

    try:
        ljm.eWriteName(handle, f"DAC{channel}", voltage)
        print(f"[INFO] Set DAC{channel} to {voltage} V")
        actual_voltage = ljm.eReadName(handle, f"DAC{channel}")
        print(f"[INFO] Actual DAC{channel} voltage: {actual_voltage} V")
        print(
            f"[INFO] Delta DAC{channel} voltage: {actual_voltage - voltage} V = {(actual_voltage / voltage - 1) * 100:.2f} %"
        )
        return actual_voltage

    except ljm.LJMError as e:
        print(f"Error setting DAC{channel} voltage: {e}")


def set_channels_resolution(handle, res_idx=0):
    """

    Description
    -----------

    Set the resolution index for **ALL** Analog Input channels.

    **NOTE:** For the T8, writing to ***any*** of the resolution index registers will set the resolution for ***all*** channels. That is why we will not set them individually, but instead set the global AIN_ALL_RESOLUTION_INDEX register.

    Valid resolution indices are 0-16, where 0 means "Default (use best resolution for requested rate)".

    When the resolution index is set to zero, the device will select the best resolution for the requested sampling rate according to the following table in the documentation:
    https://support.labjack.com/docs/a-3-3-2-t8-noise-and-resolution-t-series-datasheet#ADC-Noise-and-Resolution

    The T8 offers user-selectable effective resolution through the resolution index parameter, which applies to all AIN channels. Increasing the resolution index value will improve the channel resolution, but increasing the resolution often requires the use of slower sampling rates.  See section 14.0 AIN for more information on the resolution index parameter and its use.

    Reference
    --------

    https://support.labjack.com/docs/a-3-3-2-t8-noise-and-resolution-t-series-datasheet#ADC-Noise-and-Resolution

    Parameters
    ----------

    handle : int
        Device handle from ljm.openS()

    """

    # Set the Global (AIN_ALL) resolution setting
    try:
        ljm.eWriteName(handle, "AIN_ALL_RESOLUTION_INDEX", res_idx)
        print(f"GLOBAL (AIN_ALL) Resolution Index set to {res_idx}")
    except ljm.LJMError as e:
        print(f"Error setting GLOBAL resolution: {e}")


def get_channel_resolution(handle) -> int | None:
    """
    Reads the resolution index for AIN channels and returns a mapping.
    Note: Default (0) means the channel follows AIN_ALL_RESOLUTION_INDEX.
    """

    # Determine device type to provide accurate descriptions
    device_type = ljm.getHandleInfo(handle)[0]

    if device_type != 8:
        print(f"Warning: Device type {device_type} may not support resolution index settings as expected for T8.")
        raise NotImplementedError(
            f"get_channel_resolution is designed for T8 devices. Detected device type: {device_type}"
        )

    # 1. Read the Global (AIN_ALL) resolution setting
    try:
        ain_all_val = int(ljm.eReadName(handle, "AIN_ALL_RESOLUTION_INDEX"))
        print(f"GLOBAL (AIN_ALL) Resolution Index: {ain_all_val} (AIN_ALL_RESOLUTION_INDEX)")
    except ljm.LJMError:
        ain_all_val = None

    return ain_all_val


def set_channels_ranges(handle, num_channels=None, ranges=None, check_ranges=False):
    """
    Set the voltage range for AIN channels.

    Note that, if you set to non-default value, the instrument will set the next higher range. For example, if you set AIN0 to 5V, the instrument will automatically switch to the next higher range (±9.6 V) for that measurement.

    Ranges are: ±11 V, ±9.6 V, ±4.8 V, ±2.4 V, ±1.2 V,
                ±0.6 V, ±0.3 V, ±0.15 V,
                ±0.075 V, ±0.036 V, ±0.018 V

    Reference: https://support.labjack.com/docs/14-3-2-analog-inputs-t8-t-series-datasheet#Feature-Highlights

    handle : int
        Device handle from ljm.openS()
    num_channels : list of int
        List of AIN channel numbers to configure (e.g., [0, 1, 2])
    ranges : dict or list
        If dict, keys are channel numbers and values are range values (e.g., {0: 10, 1: 3.44}).
        If list, it applies to channels in order (e.g., [10, 3.44] for channels [0, 1]).
    """

    if num_channels is None:
        num_channels = range(8)  # Default to AIN0-AIN7 for T8

    if ranges is None:
        ranges = {idx: 10 for idx in num_channels}  # Default to ±10 V

    for idx in num_channels:
        try:
            range_val = ranges[idx] if isinstance(ranges, dict) else ranges[num_channels.index(idx)]
            ljm.eWriteName(handle, f"AIN{idx}_RANGE", range_val)
            print(f"AIN{idx} Range set to ±{range_val} V")
            if check_ranges:
                _ = get_channels_ranges(handle, num_channels=[idx])
        except ljm.LJMError as e:
            print(f"Error setting AIN{idx} range: {e}")


def get_channels_ranges(handle, num_channels=None):
    """
    Reads the voltage range for AIN channels and returns a mapping.

    handle : int
        Device handle from ljm.openS()
    num_channels : list of int
        List of AIN channel numbers to read (e.g., [0, 1, 2])
    """

    if num_channels is None:
        num_channels = range(8)  # Default to AIN0-AIN7 for T8

    ranges = {}
    for idx in num_channels:
        try:
            range_val = ljm.eReadName(handle, f"AIN{idx}_RANGE")
            ranges[idx] = range_val
            print(f"AIN{idx} Range Instrument Setting: ±{range_val} V")
        except ljm.LJMError as e:
            print(f"Error reading AIN{idx} range: {e}")
    return ranges


def acquire_dataT8(
    handle,
    num_samples=1000,
    sample_rate=1000,
    channels=["AIN0"],
    timeout_sec=5.0,
):
    """Acquire streaming data from LabJack device with timestamps.

    Parameters:
    -----------
    handle : int
        Device handle from ljm.openS()
    num_samples : int
        Number of scans to acquire
    sample_rate : float
        Sample rate in Hz
    channels : list
        Channel names (e.g., ["AIN0", "AIN1"])
    timeout_sec : float
        Timeout for acquisition in seconds

    Returns:
    --------
    data : np.ndarray
        Array with shape (num_scans, num_channels+1) where first column is time
        and remaining columns are channel data. Returns None on error.
    info : dict
        Dictionary with acquisition metadata (actual_rate, scans_collected, elapsed_time_sec)
    """

    try:
        # Map names to addresses
        aAddresses, aTypes = ljm.namesToAddresses(len(channels), channels)
        num_ch = len(aAddresses)
        print("Channels:", channels)
        print("aAddresses:", aAddresses)
        print("aTypes:", aTypes)
        scans_per_read = 256  # chunk size per eStreamRead (reasonable default)

        print(
            f"**** Starting stream with num_samples={num_samples}, sample_rate={sample_rate}, channels={channels} ****"
        )

        # Start stream
        actual_rate = ljm.eStreamStart(handle, scans_per_read, num_ch, aAddresses, sample_rate)
        print(f"eStreamStart returned actual_rate = {actual_rate} Hz")

        # Read the stream data
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

        # Stop stream
        ljm.eStreamStop(handle)

        # Convert to numpy, trim partial tail, reshape
        flat = np.asarray(all_flat, dtype=float)
        n_rows = flat.size // num_ch
        if n_rows == 0:
            raise RuntimeError("No complete scans received.")
        flat = flat[: n_rows * num_ch]
        data = flat.reshape(n_rows, num_ch)

        # If you asked for a specific total, trim/keep only the requested scans
        if data.shape[0] > num_samples:
            data = data[:num_samples, :]

        # Generate timestamps for each scan
        times = np.arange(data.shape[0]) * scan_interval

        # Combine times with data (time as first column)
        data = np.hstack([times.reshape(-1, 1), data])

        print(f"Collected {data.shape[0]} scans × {data.shape[1] - 1} channels (+ time column)")
        print(f"Time range: {times[0]:.6f} to {times[-1]:.6f} seconds")
        return data, {
            "actual_rate": actual_rate,
            "scans_collected": scans_collected,
            "elapsed_time_sec": elapsed,
        }

    except Exception as e:
        print("Error acquiring data:")
        print(e)
        traceback.print_exc()
        return None, None


def close_all_labjacks(verbose=False):
    """
    Closes all open connections to LabJack devices. Useful for ensuring a clean slate before starting new work.
    """
    try:
        res = ljm.listAllS("ANY", "ANY")
        if verbose:
            print('ljm.listAllS("ANY", "ANY") OUTPUT:')
            print(res)
        ljm.closeAll()
        if verbose:
            print("[INFO] All LabJack connections closed successfully.")

    except Exception as e:
        print(f"[ERROR] Failed to close all LabJack connections: {e}")


if __name__ == "__main__":
    det = detect_labjacks(verbose=True)
    close_all_labjacks(verbose=True)

# %%
