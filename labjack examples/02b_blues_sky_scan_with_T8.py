import time
import threading
import datetime
import numpy as np
from ophyd import Device, Signal
from ophyd.sim import SynAxis
from labjack import ljm
from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback
import bluesky.plans as bp

# --- 1. YOUR WORKING DETECTOR CLASS ---
class LabJackMultiChannelDetector(Device):
    def __init__(self, name, channels=[0], handle=None, **kwargs):
        self._ch_signals = {}
        self.channels = channels
        self.channel_names = [f"AIN{c}" for c in channels]
        super().__init__(name=name, **kwargs)

        for ch_name in self.channel_names:
            # Note: sig.name will be f"{self.name}_{ch_name}"
            sig = Signal(name=f"{self.name}_{ch_name}", kind='hinted')
            self._ch_signals[ch_name] = sig
            setattr(self, ch_name, sig)
            self._signals[ch_name] = sig

        # THIS IS THE KEY: Tell Ophyd these signals are allowed to be read
        self.read_attrs = list(self._signals.keys())

        try:
            self.handle = handle or ljm.openS("T8", "ANY", "ANY")
            print(f"--- Successfully connected to LabJack T8 ---")
        except Exception as e:
            print(f"--- LJM Connection FAILED: {e} ---")
            self.handle = None
        
        self.act_time = 1.0 
        self.sample_rate = 10.0

    def trigger(self):
        collected_vals = {name: [] for name in self.channel_names}
        
        def _worker():
            interval = 1.0 / self.sample_rate
            t0 = time.time()
            while (time.time() - t0) < self.act_time:
                if self.handle:
                    try:
                        results = ljm.eReadNames(self.handle, len(self.channel_names), self.channel_names)
                        for name, val in zip(self.channel_names, results):
                            collected_vals[name].append(val)
                    except Exception:
                        pass
                else:
                    for name in self.channel_names:
                        collected_vals[name].append(np.random.rand())
                time.sleep(interval)
            
            for name in self.channel_names:
                data = collected_vals[name]
                avg = np.mean(data) if data else np.nan
                self._ch_signals[name].put(avg)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        from ophyd.status import DeviceStatus
        status = DeviceStatus(self)
        def _check_done():
            thread.join()
            status.set_finished()
        threading.Thread(target=_check_done, daemon=True).start()
        return status

# --- 2. MINIMAL CSV WRITER ---
class SimpleCSVWriter:
    def __init__(self, filename, det_name, channels):
        self.filename = filename
        self.file = open(filename, 'w')
        # Exact keys Bluesky uses: {device_name}_{signal_name}
        self.keys = [f"{det_name}_{f'AIN{c}'}" for c in channels]
        
        header = ["YYYY-MM-DD, HH:mm:ss.SSSS", "motor_pos"] + self.keys
        self.file.write(",".join(header) + "\n")

    def __call__(self, name, doc):
        if name == 'event':
            data = doc['data']
            # Format time
            dt = datetime.datetime.fromtimestamp(doc['time'])
            time_str = dt.strftime('%Y-%m-%d, %H:%M:%S.%f')[:-2]
            
            pos = data.get('motor', 0.0)
            
            # Print AIN0 to terminal as requested
            ain0_key = self.keys[0]
            val0 = data.get(ain0_key, np.nan)
            print(f"   >>> {ain0_key}: {val0:.6f} V")
            
            # Write to file
            row = [time_str, f"{pos:.6g}"]
            for k in self.keys:
                row.append(f"{data.get(k, np.nan):.6g}")
            self.file.write(",".join(row) + "\n")
            self.file.flush()

    def close(self):
        self.file.close()

# --- 3. EXECUTION ---
def run_experiment():
    RE = RunEngine({})
    RE.subscribe(BestEffortCallback())

    motor = SynAxis(name="motor")
    channels = [0, 1]
    det = LabJackMultiChannelDetector(name="test_lj", channels=channels)
    
    writer = SimpleCSVWriter("scan_results.csv", det.name, channels)
    RE.subscribe(writer)

    print("\nStarting Bluesky Scan...")
    try:
        RE(bp.scan([det], motor, 0, 1, 5))
    finally:
        writer.close()
        if det.handle:
            ljm.close(det.handle)
        print(f"\nScan finished. Data saved to scan_results.csv")

if __name__ == "__main__":
    run_experiment()