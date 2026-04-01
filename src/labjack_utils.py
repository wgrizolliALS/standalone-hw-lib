"""
Utility library for LabJack T8 and T7 devices.
Provides helper functions for device discovery, resolution configuration,
and high-speed data acquisition.
"""

from labjack import ljm

import traceback
import time

import numpy as np


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
                        print(f"Could not read USB path for serial {device_info['serial']}: {e}")
                        pass

                ljm.close(handle)

            except ljm.LJMError:
                # Device might be in use or disconnected
                device_info["port"] = "Busy/Error"
            devices.append(device_info)
    except ljm.LJMError as e:
        print(f"Error listing LabJacks: {e}")

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
    for idx, dev in enumerate(devices, 1):
        conn_name = connection_map.get(dev["connection"], f"Unknown({dev['connection']})")
        port_info = f", Port: {dev['port']}" if dev.get("port") else ""
        usb_info = f", USB Address: {dev['usb_address']}" if dev.get("usb_address") else ""
        print(
            f"[{idx}] Device type: {dev['type']}, Connection: {conn_name}, Serial: {dev['serial']}, IP: {dev['ip']}{port_info}{usb_info}"
        )


def set_channels_res(handle, num_channels=[0], res_idx=[0]):
    """
    Set the resolution index for AIN channels and returns a mapping.
    Note: Default (0) means the channel follows AIN_ALL_RESOLUTION_INDEX.

    handle : int
        Device handle from ljm.openS()
    num_channels : list of int
        List of AIN channel numbers to configure (e.g., [0, 1, 2])
    res_idx : int or list of int
        Resolution index to set. If a single int, it applies to all num_channels.

    res_idx are given by the `res_lookup` dictionary:     T8 (Model 8) uses different indices than T7 (Model 7).
    T8: {0: "Default", 1: "Sinc1", 2: "Sinc1x4", 3: "Sinc1x16", 4: "Sinc1x64", 5: "Sinc4"}
    T7: {0: "Default", 1: "16-bit", 2: "17-bit", ..., 9: "24-bit"}

    ***NOTE*** Not tested!

    """

    # 1. Set the Global (AIN_ALL) resolution setting
    try:
        ljm.eWriteName(handle, "AIN_ALL_RESOLUTION_INDEX", 0)
        print("GLOBAL (AIN_ALL) Resolution Index set to 0 (Default)")
    except ljm.LJMError as e:
        print(f"Error setting GLOBAL resolution: {e}")

    # 2. Set individual channel settings
    for idx in num_channels:
        try:
            # For this utility, we default to 0 to follow AIN_ALL
            ljm.eWriteName(handle, f"AIN{idx}_RESOLUTION_INDEX", 0)
            print(f"AIN{idx} Resolution Index set to 0")
        except ljm.LJMError as e:
            print(f"Error setting AIN{idx} resolution: {e}")


def get_channels_res(handle, num_channels=[0]):
    """
    Reads the resolution index for AIN channels and returns a mapping.
    Note: Default (0) means the channel follows AIN_ALL_RESOLUTION_INDEX.
    """

    # Determine device type to provide accurate descriptions
    device_type = ljm.getHandleInfo(handle)[0]

    # T8 (Model 8) uses different indices than T7 (Model 7)
    if device_type == 8:
        res_lookup = {
            0: "Default",
            1: "Sinc1",
            2: "Sinc1x4",
            3: "Sinc1x16",
            4: "Sinc1x64",
            5: "Sinc4",
        }
    else:
        res_lookup = {
            0: "Default",
            1: "16-bit",
            2: "17-bit",
            3: "18-bit",
            4: "19-bit",
            5: "20-bit",
            6: "21-bit",
            7: "22-bit",
            8: "23-bit",
            9: "24-bit",
        }

    # 1. Read the Global (AIN_ALL) resolution setting
    try:
        ain_all_val = int(ljm.eReadName(handle, "AIN_ALL_RESOLUTION_INDEX"))
        ain_all_desc = res_lookup.get(ain_all_val, f"Index {ain_all_val}")
        print(f"GLOBAL (AIN_ALL) Resolution Index: {ain_all_val} ({ain_all_desc})")
    except ljm.LJMError:
        ain_all_val = None
        ain_all_desc = "Unknown"

    resolutions = {"global": {"index": ain_all_val, "description": ain_all_desc}}

    # 2. Read individual channel settings
    for idx in num_channels:
        try:
            val = ljm.eReadName(handle, f"AIN{idx}_RESOLUTION_INDEX")
            val_int = int(val)
            res_str = res_lookup.get(val_int, f"Index {val_int}")

            # Determine the actual hardware setting being used
            if val_int == 0:
                display_str = f"Default (inheriting Global: {ain_all_desc})"
                effective_desc = ain_all_desc
            else:
                display_str = res_str
                effective_desc = res_str

            resolutions[idx] = {
                "index": val_int,
                "description": display_str,
                "effective_description": effective_desc,
            }
            print(f"AIN{idx} Resolution Index: {val_int}, {display_str}")
        except ljm.LJMError:
            # Skip channels that aren't available or don't support the register
            continue

    return resolutions


def acquire_dataT8(
    handle,
    num_samples=1000,
    sample_rate=1000,
    channels=None,
    timeout_sec=5.0,
    resolution_idx=0,
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
    """
    if channels is None:
        channels = ["AIN0"]

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
        return data

    except Exception as e:
        print("Error acquiring data:")
        print(e)
        traceback.print_exc()
        return None


if __name__ == "__main__":
    det = detect_labjacks(verbose=True)
