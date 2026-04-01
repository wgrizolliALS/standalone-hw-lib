import time
import threading
import numpy as np
import pandas as pd
from ophyd import Device, Signal
from ophyd.sim import motor
from labjack import ljm
from bluesky import RunEngine
from bluesky.plans import scan
from bluesky.callbacks.best_effort import BestEffortCallback

# --- 1. THE HARDWARE-ONLY DETECTOR ---
class LabJackMultiChannelDetector(Device):
    active_channels = [0, 1, 2, 8] 

    def __init__(self, name, handle=None, **kwargs):
        super().__init__(name=name, **kwargs)
        
        self.channel_names = [f"AIN{c}" for c in self.active_channels]
        self._ch_map = {}

        for ch_name in self.channel_names:
            sig = Signal(name=f"{name}_{ch_name}", kind='hinted')
            setattr(self, ch_name, sig)
            self._ch_map[ch_name] = sig

        # FAIL FAST: If we can't open the T8, stop the script here.
        try:
            self.handle = handle or ljm.openS("T8", "ANY", "ANY")
            print(f"--- Connected to LabJack T8 (Channels: {self.active_channels}) ---")
        except Exception as e:
            raise RuntimeError(f"CRITICAL: Could not connect to LabJack T8. {e}")
        
        self.act_time = 0.5 
        self.sample_rate = 20.0

    def trigger(self):
        collected_vals = {name: [] for name in self.channel_names}
        
        def _worker():
            interval = 1.0 / self.sample_rate
            t0 = time.time()
            while (time.time() - t0) < self.act_time:
                # If this fails, it will now raise an exception in the thread
                results = ljm.eReadNames(self.handle, len(self.channel_names), self.channel_names)
                for name, val in zip(self.channel_names, results):
                    collected_vals[name].append(val)
                time.sleep(interval)
            
            for name, sig in self._ch_map.items():
                avg = np.mean(collected_vals[name]) if collected_vals[name] else 0.0
                sig.put(avg)

        from ophyd.status import DeviceStatus
        status = DeviceStatus(self)
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        def _check_done():
            try:
                thread.join()
                status.set_finished()
            except Exception as e:
                status.set_exception(e) # Tell Bluesky the hardware failed
        
        threading.Thread(target=_check_done, daemon=True).start()
        return status

    def read(self):
        res = super().read()
        for sig in self._ch_map.values():
            res.update(sig.read())
        return res

    def describe(self):
        res = super().describe()
        for sig in self._ch_map.values():
            res.update(sig.describe())
        return res

# --- 2. BLUESKY & CSV SETUP ---
RE = RunEngine({})
RE.subscribe(BestEffortCallback())

scan_data = []
def collect_for_csv(name, doc):
    if name == 'start': scan_data.clear()
    if name == 'event': scan_data.append(doc['data'])
    if name == 'stop':
        if scan_data:
            pd.DataFrame(scan_data).to_csv("t8_real_data.csv", index=False)
            print("\n[SUCCESS] Saved real hardware data to t8_real_data.csv")

RE.subscribe(collect_for_csv)

# --- 3. EXECUTION ---
if __name__ == "__main__":
    t8 = LabJackMultiChannelDetector(name="t8")
    
    try:
        RE(scan([t8], motor, -2, 2, 5))
    finally:
        if hasattr(t8, 'handle') and t8.handle:
            ljm.close(t8.handle)