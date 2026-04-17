import csv
import time
import threading
import numpy as np
from datetime import datetime
from ophyd import Device, Signal
from labjack import ljm


class LabJackT8(Device):
    """
    A self-contained Ophyd device for the LabJack T8.

    Features:
    1. Hardware Connection (LJM)
    2. Asynchronous Triggering (Threading)
    3. Data Processing (Averaging for Bluesky)
    4. Data Logging (Self-contained CSV saving for Raw Data, optional)
    5. Optional per-channel waveform signal recording

    Parameters
    ----------
    name : str
        The name of the device for Ophyd/Bluesky.
    channels : list[int] | int | None, optional
        List of AIN channel indices to read (e.g., [0, 1] for AIN0 and AIN1).
    handle : str | None, optional
        An existing LJM handle. If None, a new connection is opened.
    act_time : float, optional
        The duration of the stream acquisition in seconds. Default is 0.5s.
    sample_rate : float, optional
        The sampling frequency in Hz. Default is 20.0 Hz.
    connectionType : str, optional
        LJM connection type (e.g., "USB", "ETHERNET", "ANY").
    identifier : str, optional
        LJM identifier (e.g., "ANY", or a specific serial number).
    save_raw_to_csv : bool, optional
        If True, saves raw waveform data to CSV during scans. Default is True.
    enable_waveforms : bool, optional
        If True, exposes per-channel waveform signals and time vector. Default is False.
    csv_fname : str | None, optional
        Optional filename for the raw data CSV export.
    verbose : bool, optional
        Print connection and status info.
    verbose_stream : bool, optional
        Print acquisition info.
    ranges : dict | None, optional
        Backwards-compatible per-channel range settings. Keys may be channel
        integers (e.g. `0`) or channel name strings (e.g. `'AIN0'` or
        `'AIN0_RANGE'`). Values are numeric and will be written to the
        corresponding `AIN#_RANGE` register on device initialization.
        Values for T8 model are: ±11 V, ±9.6 V, ±4.8 V, ±2.4 V, ±1.2 V,
        ±0.6 V, ±0.3 V, ±0.15 V, ±0.075 V, ±0.036 V, ±0.018 V . See T8 documentaion
        at https://support.labjack.com/docs/14-3-2-analog-inputs-t8-t-series-datasheet
    writes : dict | None, optional
        Generic register writes to apply at initialization. Keys are the
        LJM register names (strings) and values are numeric. Useful for
        setting arbitrary device registers (including `AIN#_RANGE`).
    writes_raise : bool, optional
        If True, any failure performing the `writes`/`ranges` will raise a
        RuntimeError and abort initialization. If False (default), write
        failures are logged as warnings and initialization continues.
    Examples
    --------
    - Set per-channel ranges (legacy style):

        LabJackT8('t8', channels=[0,1], ranges={0: 10, 'AIN1': 2.44})

    - Generic register writes (recommended for arbitrary registers):

        LabJackT8('t8', writes={'AIN0_RANGE': 10, 'DIO0_EF_CLOCK0_ENABLE': 1})
    """

    def __init__(
        self,
        name,
        channels: list[int] | int | None = None,
        handle: str | None = None,
        act_time: float = 0.5,
        sample_rate: float = 20.0,
        connectionType: str = "ANY",
        identifier: str = "ANY",
        save_raw_to_csv: bool = True,
        csv_fname: str | None = None,
        verbose: bool = False,
        verbose_stream: bool = False,
        enable_waveforms: bool = False,
        ranges: dict | None = None,
        writes: dict | None = None,
        writes_raise: bool = False,
        **kwargs,
    ):

        super().__init__(name=name, **kwargs)
        if isinstance(channels, (int, float)):
            channels = [int(channels)]

        self.handle_info = None
        self._ljm_ready = False
        self.active_channels = channels if channels is not None else [0]
        self.channel_names = [f"AIN{c}" for c in self.active_channels]
        self.save_raw_to_csv = save_raw_to_csv
        self._scan_results = []
        self._raw_block_for_csv = None  # Only for CSV saving, not exposed as a Signal
        # Add per-channel waveform signals
        self._waveform_signals = {}
        self._waveform_time_signal = None
        self._record_waveform_signals = enable_waveforms
        self._ch_map = {}
        self._hint_fields = []
        self._csv_file = None
        self._csv_writer = None
        self.csv_fname = csv_fname

        self.verbose = verbose
        self.verbose_stream = verbose_stream

        # Backwards-compatible ranges dict and generic writes dict
        self.ranges = ranges or {}
        self.writes = writes or {}
        self.writes_raise = bool(writes_raise)

        self.act_time = act_time
        self.sample_rate = sample_rate
        self.last_scan_actual_rate = None

        for ch in self.channel_names:
            # Scalar signal (mean)
            full_name = f"{name}_{ch.lower()}"
            sig = Signal(name=full_name, kind="hinted")  # type: ignore
            setattr(self, ch, sig)
            self._ch_map[ch] = sig
            self._hint_fields.append(full_name)
            # Waveform signal (optional)
            if self._record_waveform_signals:
                wf_name = f"{name}_{ch.lower()}_waveform"
                wf_sig = Signal(name=wf_name, kind="normal")  # type: ignore
                setattr(self, f"{ch}_waveform", wf_sig)
                self._waveform_signals[ch] = wf_sig
        # Only one time vector for all channels
        if self._record_waveform_signals:
            wf_time_name = f"{name}_waveform_time"
            wf_time_sig = Signal(name=wf_time_name, kind="normal")  # type: ignore
            setattr(self, "waveform_time", wf_time_sig)
            self._waveform_time_signal = wf_time_sig

        from labjack import ljm

        try:
            print("[INFO] Connecting to LabJack T8...")
            self.handle = handle or ljm.openS("T8", connectionType, identifier)
            print("[INFO] Connected!")
            self.ljm_module = ljm
            self._ljm_ready = True
            if self.verbose:
                print("[STATUS] Successfully Connected to LabJack T8")
                info = ljm.getHandleInfo(self.handle)
                self.handle_info = info
                print(
                    f"[INFO] Connected Device: {info[0]}, Connection: {info[1]}, Serial: {info[2]}, IP: {info[3]}, Port: {info[4]}\n"
                )
            # Apply `ranges` and `writes` using the wrapper helpers so error handling
            # and verification are centralized. `set_range` will perform optional
            # readback verification; here we skip verification to keep init fast,
            # but respect `writes_raise` for raising on failure.
            # Apply configured ranges and writes. Let helper methods manage errors
            # (they accept flags to raise or log failures).
            for k, v in (self.ranges or {}).items():
                if isinstance(k, int):
                    ch = k
                else:
                    ch = str(k)
                self.set_range(ch, float(v), verify=False, raise_on_mismatch=self.writes_raise)
                if self.verbose:
                    print(f"[INFO] Set AIN range {ch} = {v}")

            for name, val in (self.writes or {}).items():
                self.eWriteName(str(name), float(val), raise_on_fail=self.writes_raise)
                if self.verbose:
                    print(f"[INFO] Wrote {name} = {val}")
        except Exception as e:
            self.close()
            raise RuntimeError(f"[ERROR] LJM Connection FAILED: {e}")

    @property
    def hints(self):
        return {"fields": self._hint_fields}

    def trigger(self):
        """
        Start an asynchronous acquisition from the LabJack T8.
        Acquires a block of data, computes per-channel means, and (optionally) stores waveforms and time vector.
        The raw block is stored for CSV export if enabled.
        """
        samples = []
        scan_rate = self.sample_rate
        scans_per_read = int(scan_rate * self.act_time)

        def _worker():
            if self.verbose_stream:
                print(f"[INFO] {datetime.now()}: Acquisition STARTED.")
            try:
                aAddresses = self.ljm_module.namesToAddresses(len(self.channel_names), self.channel_names)[0]
                actual_rate = self.ljm_module.eStreamStart(
                    self.handle, scans_per_read, len(aAddresses), aAddresses, scan_rate
                )
                self.last_scan_actual_rate = actual_rate
                ret = self.ljm_module.eStreamRead(self.handle)
                raw_data = ret[0]
                self.ljm_module.eStreamStop(self.handle)

                num_channels = len(self.channel_names)
                reshaped = np.array(raw_data).reshape(-1, num_channels)
                t0 = time.time() - self.act_time
                for i, row in enumerate(reshaped):
                    ts = t0 + (i / actual_rate)
                    samples.append([ts] + row.tolist())

                # Scalar (mean) and waveform per channel
                for i, ch in enumerate(self.channel_names):
                    avg = np.mean(reshaped[:, i])
                    self._ch_map[ch].put(avg)
                    # Store waveform as 1D array (fixed shape) if enabled
                    if self._record_waveform_signals and ch in self._waveform_signals:
                        waveform = np.asarray(reshaped[:, i], dtype=float)
                        self._waveform_signals[ch].put(waveform)
                # Store time vector ONCE for all channels
                if self._record_waveform_signals and self._waveform_time_signal is not None:
                    time_vector = np.array([t0 + (j / actual_rate) for j in range(reshaped.shape[0])], dtype=float)
                    self._waveform_time_signal.put(time_vector)

                try:
                    arr = np.array(samples, dtype=float)
                except Exception:
                    print("[WARNING] Could not convert samples to float array, storing as object array instead.")
                    arr = np.array(samples, dtype=object)
                self._raw_block_for_csv = arr  # Store for CSV saver only

                if self.verbose_stream:
                    print(f"[INFO] {datetime.now()}: Acquisition FINISHED.")
                    print(
                        f"[INFO] Acquired {len(reshaped)} samples from {num_channels} channels at {actual_rate:} Hz.\n"
                    )

            except Exception as e:
                print(f"[STREAM ERROR] : {e}")
                try:
                    self.ljm_module.eStreamStop(self.handle)
                except Exception as stop_e:
                    print(f"[STREAM ERROR] Failed to stop stream: {stop_e}")

        from ophyd.status import DeviceStatus

        status = DeviceStatus(self)
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        def _check_done():
            thread.join()
            status.set_finished()

        threading.Thread(target=_check_done, daemon=True).start()
        return status

    def read(self):
        """
        Read the current values from all signals.
        Returns a dictionary with per-channel means and, if enabled, waveform and time signals.
        """
        res = super().read()
        for sig in self._ch_map.values():
            res.update(sig.read())
        # Add per-channel waveform signals if enabled
        if self._record_waveform_signals:
            for wf_sig in self._waveform_signals.values():
                res.update(wf_sig.read())
            if self._waveform_time_signal is not None:
                res.update(self._waveform_time_signal.read())  # type: ignore
        # Expose temporary raw block for convenience (matches older behaviour
        # used by some examples). This is not persisted to the event stream;
        # it's a transient view of the last acquired block.
        if self._raw_block_for_csv is not None:
            key = f"{self.name}_raw_block"
            # Provide a minimal read dict with a `value` entry to match legacy
            # code that indexes `readings["..._raw_block"]["value"]`.
            res[key] = {"value": self._raw_block_for_csv}
        return res

    def describe(self):
        """
        Describe the structure of the signals produced by this device.
        Includes per-channel means and, if enabled, waveform and time signals.
        """
        res = super().describe()
        scans_per_read = int(self.sample_rate * self.act_time)
        for sig in self._ch_map.values():
            res.update(sig.describe())
        # Add per-channel waveform signal descriptions if enabled
        if self._record_waveform_signals:
            for i, ch in enumerate(self.channel_names):
                wf_key = f"{self.name}_{ch.lower()}_waveform"
                res[wf_key] = {  # type: ignore
                    "source": f"LabJackT8 {ch} waveform",
                    "dtype": "number",
                    "shape": (scans_per_read,),
                }
            # Only one time vector for all channels
            wf_time_key = f"{self.name}_waveform_time"
            res[wf_time_key] = {  # type: ignore
                "source": "LabJackT8 waveform time",
                "dtype": "number",
                "shape": (scans_per_read,),
            }
        return res

    def csv_saver(self, name, doc):
        """
        Bluesky callback to save raw waveform data to CSV during a scan.
        Only saves if save_raw_to_csv is True.
        If save_raw_to_csv is False, this callback is a no-op and nothing will be saved (safe to subscribe regardless of flag).
        Uses the temporary _raw_block_for_csv attribute for performance, not stored in event stream.
        Columns: Time, motor, [channels...]
        """
        if not self.save_raw_to_csv:
            return

        if name == "start":
            self._scan_results.clear()
            self.csv_fname = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            try:
                self._csv_file = open(self.csv_fname, "w", newline="", encoding="utf-8")
            except Exception as e:
                print(f"[CSV ERROR] Could not open file {self.csv_fname}: {e}")
                self._csv_file = None
                self._csv_writer = None
                return
            fieldnames = ["Time", "motor"] + self.channel_names
            self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=fieldnames)
            self._csv_writer.writeheader()

        elif name == "event":
            m_pos = doc.get("data", {}).get("motor", 0.0)
            raw_data = self._raw_block_for_csv if self._raw_block_for_csv is not None else []
            for sample in raw_data:
                row = {
                    "Time": datetime.fromtimestamp(sample[0]).strftime("%Y-%m-%d %H:%M:%S.%f"),
                    "motor": m_pos,
                }
                for i, ch_name in enumerate(self.channel_names):
                    row[ch_name] = sample[i + 1]
                self._scan_results.append(row)
                if self._csv_writer:
                    try:
                        self._csv_writer.writerow(row)
                    except Exception as e:
                        print(f"[CSV ERROR] Could not write row: {e}")
            if self._csv_file:
                try:
                    self._csv_file.flush()
                except Exception as e:
                    print(f"[CSV ERROR] Could not flush file: {e}")
            self._raw_block_for_csv = None  # Clear after use

        elif name == "stop":
            if self._csv_file:
                try:
                    self._csv_file.close()
                except Exception as e:
                    print(f"[CSV ERROR] Could not close file: {e}")
                print(f"\n[CSV] Saved {len(self._scan_results)} rows to {self.csv_fname}")
                self._csv_file = None

    def close(self):
        """
        Close the connection to the LabJack device.
        """
        if hasattr(self, "handle") and self.handle:
            self.ljm_module.close(self.handle)
            print("[INFO] LabJack connection closed.")

    def eWriteName(self, name, value, raise_on_fail: bool = False):
        """
        Safe wrapper around the LabJack LJM `eWriteName` call.

        Parameters
        - name: str - register name to write (e.g., 'AIN0_RANGE' or 'DIO0_EF_CLOCK0_ENABLE')
        - value: numeric - value to write to the register
        - raise_on_fail: bool - if True, exceptions from the underlying LJM call
            will be propagated. If False, exceptions are caught and logged.

        Note: This function does not return a value. Success is indicated by the
        absence of an exception when `raise_on_fail` is True, or by no error
        message being printed when `raise_on_fail` is False.
        """
        # If caller wants exceptions propagated, let them bubble up.
        if raise_on_fail:
            # Will raise if the underlying call fails.
            self.ljm_module.eWriteName(self.handle, str(name), float(value))
            if self.verbose:
                print(f"[INFO] eWriteName: Wrote {name} = {value}")

        # Otherwise, catch errors and return False on failure.
        try:
            self.ljm_module.eWriteName(self.handle, str(name), float(value))
            if self.verbose:
                print(f"[INFO] eWriteName: Wrote {name} = {value}")
        except Exception as e:
            print(f"[ERROR] eWriteName failed for {name} -> {value}: {e}")

    def eReadName(self, name, raise_on_fail: bool = False) -> float | None:
        """
        Wrapper around LJM `eReadName` to read a single register.

        Returns the numeric value on success, or None on failure (unless
        `raise_on_fail` is True, in which case a RuntimeError is raised).
        """
        try:
            val = self.ljm_module.eReadName(self.handle, str(name))
            # ljm.eReadName may return a single value or a tuple; handle both
            if isinstance(val, (list, tuple)) and len(val) == 1:
                val = val[0]
            if self.verbose:
                print(f"[INFO] eReadName: Read {name} = {val}")
            return val
        except Exception as e:
            msg = f"[ERROR] eReadName failed for {name}: {e}"
            if raise_on_fail:
                raise RuntimeError(msg)
            print(msg)
            return None

    def set_range(
        self,
        channel,
        value: float,
        verify: bool = True,
        delay: float = 0.05,
        tol: float = 1e-6,
        raise_on_mismatch: bool = False,
    ):
        """
        Convenience to set `AIN#_RANGE` for a channel with optional readback verification.

        Parameters
        - channel: int or str (e.g., 0 or 'AIN0')
        - value: float - value to write
        - verify: if True, read back the register after `delay` and compare within `tol`
        - delay: seconds to wait before verification (settling)
        - tol: absolute tolerance for readback equality
        - raise_on_mismatch: if True, raise on verification mismatch

        Note: This function does not return a boolean. Errors will either be
        logged (when `raise_on_mismatch` is False) or raised as RuntimeError
        (when `raise_on_mismatch` is True).
        """
        if isinstance(channel, int):
            reg = f"AIN{channel}_RANGE"
        else:
            ch = str(channel)
            if ch.upper().endswith("_RANGE"):
                reg = ch
            elif ch.upper().startswith("AIN"):
                reg = f"{ch}_RANGE"
            else:
                reg = f"AIN{ch}_RANGE"

        # perform the write; errors (and logging) are handled by `eWriteName`
        self.eWriteName(reg, float(value), raise_on_fail=False)
        if verify:
            time.sleep(max(0.0, float(delay)))
            readback = self.eReadName(reg, raise_on_fail=False)
            if readback is None:
                if raise_on_mismatch:
                    raise RuntimeError(f"Failed to read back {reg}")
                return

            diff = abs(readback - value)
            if diff > float(tol):
                msg = f"[WARNING] Range write mismatch {reg}: wrote {value}, read {readback} (diff={diff})"
                print(msg)
                if raise_on_mismatch:
                    raise RuntimeError(msg)
        # Success: no explicit True returned; errors are logged/raised above


# ---------------------------------------------------------------------------
# Module-level helpers (moved here so ophyd device is self-contained)
# ---------------------------------------------------------------------------


def detect_labjacks(verbose: bool = False):
    """
    Scan for connected LabJack devices (wraps ljm.listAllS).
    Returns a list of device info dicts.
    """
    devices = []
    try:
        res = ljm.listAllS("ANY", "ANY")
        num = res[0]
        for i in range(num):
            devices.append(
                {
                    "type": res[1][i],
                    "connection": res[2][i],
                    "serial": res[3][i],
                    "ip": ljm.numberToIP(res[4][i]),
                }
            )
    except Exception as e:
        print(f"[ERROR] detect_labjacks failed: {e}")
    finally:
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

    print(f"[INFO] detect_labjacks: found {len(devices)} device(s)")
    connection_map = {1: "USB", 2: "ETH", 3: "Wireless"}
    for idx, dev in enumerate(devices):
        conn_name = connection_map.get(dev["connection"], f"Unknown({dev['connection']})")
        port_info = f", Port: {dev['port']}" if dev.get("port") else ""
        usb_info = f", USB Address: {dev['usb_address']}" if dev.get("usb_address") else ""
        print(
            f"[{idx}] Device type: {dev['type']}, Connection: {conn_name}, Serial: {dev['serial']}, IP: {dev['ip']}{port_info}{usb_info}"
        )


def close_all_labjacks(verbose: bool = False):
    """Close all open LabJack connections."""
    try:
        ljm.closeAll()
        if verbose:
            print("[INFO] Closed all LabJack connections")
    except Exception as e:
        print(f"[ERROR] close_all_labjacks: {e}")


def set_DAC_voltage(handle, channel, voltage):
    """Set DAC channel voltage and return actual reading."""
    try:
        ljm.eWriteName(handle, f"DAC{channel}", float(voltage))
        actual = ljm.eReadName(handle, f"DAC{channel}")
        return actual
    except Exception as e:
        print(f"[ERROR] set_DAC_voltage: {e}")
        return None


def set_channels_ranges(handle, num_channels=None, ranges=None, check_ranges=False):
    """Set AIN channel ranges in batch.

    - `num_channels` can be iterable of ints; `ranges` can be dict or list.
    """
    if num_channels is None:
        num_channels = range(8)
    if ranges is None:
        ranges = {idx: 10 for idx in num_channels}
    for idx in num_channels:
        try:
            val = ranges[idx] if isinstance(ranges, dict) else ranges[list(num_channels).index(idx)]
            ljm.eWriteName(handle, f"AIN{idx}_RANGE", float(val))
            if check_ranges:
                _ = get_channels_ranges(handle, num_channels=[idx])
        except Exception as e:
            print(f"[ERROR] set_channels_ranges AIN{idx}: {e}")


def get_channels_ranges(handle, num_channels=None):
    """Read AIN channel ranges and return dict mapping index->range."""
    if num_channels is None:
        num_channels = range(8)
    out = {}
    for idx in num_channels:
        try:
            out[idx] = ljm.eReadName(handle, f"AIN{idx}_RANGE")
        except Exception as e:
            print(f"[ERROR] get_channels_ranges AIN{idx}: {e}")
            out[idx] = None
    return out


def get_channel_resolution(handle):
    """Return the global AIN_ALL_RESOLUTION_INDEX value (T8-specific)."""
    try:
        val = ljm.eReadName(handle, "AIN_ALL_RESOLUTION_INDEX")
        return int(val)
    except Exception as e:
        print(f"[ERROR] get_channel_resolution: {e}")
        return None


if __name__ == "__main__":
    # Quick self-test for developers: list devices, read ranges/resolution, then close
    print("[SELFTEST] Detecting connected LabJacks...")
    devs = detect_labjacks(verbose=True)
    if not devs:
        print("[SELFTEST] No devices found.")
    else:
        first = devs[0]
        print(f"[SELFTEST] First device: {first}")
        try:
            # Try opening by serial to read ranges/resolution
            h = ljm.openS("ANY", "ANY", first.get("serial"))
            print("[SELFTEST] Reading channel ranges for AIN0-AIN3")
            ranges = get_channels_ranges(h, num_channels=[0, 1, 2, 3])
            print(f"[SELFTEST] Ranges: {ranges}")
            res = get_channel_resolution(h)
            print(f"[SELFTEST] Global resolution index: {res}")
            ljm.close(h)
        except Exception as e:
            print(f"[SELFTEST] Could not open/read device: {e}")
    print("[SELFTEST] Closing all LabJack connections (cleanup)")
    close_all_labjacks(verbose=True)
