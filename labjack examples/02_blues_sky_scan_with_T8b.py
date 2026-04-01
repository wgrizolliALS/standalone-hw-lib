import time
import threading
import numpy as np
import pandas as pd
from ophyd import Device, Signal, Component as Cpt
from ophyd.sim import motor
from labjack import ljm
from bluesky import RunEngine
from bluesky.plans import scan
from bluesky.callbacks.best_effort import BestEffortCallback

# --- 1. THE DETECTOR CLASS ---
class LabJackMultiChannelDetector(Device):
    # We define these as Components so Ophyd/Bluesky "sees" them
    ain0 = Cpt(Signal, kind='hinted')
    ain1 = Cpt(Signal, kind='hinted')
    ain2 = Cpt(Signal, kind='hinted')

    def __init__(self, name, handle=None, **kwargs):
        super().__init__(name=name, **kwargs)
        
        # Map our components to a list for easy iteration in the worker
        self.channel_map = {
            "AIN0": self.ain0,
            "AIN1": self.ain1,
            "AIN2": self.ain2
        }
        self.channel_names = list(self.channel_map.keys())

        try:
            self.handle = handle or ljm.openS("T8", "ANY", "ANY")
            print(f"--- Connected to LabJack T8 ---")
        except Exception as e:
            print(f"--- LJM Connection FAILED: {e}. Simulation Mode active. ---")
            self.handle = None
        
        self.act_time = 0.5 
        self.sample_rate = 20.0

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
                    except:
                        pass
                else:
                    # Simulated noise
                    for name in self.channel_names:
                        collected_vals[name].append(np.random.rand())
                time.sleep(interval)
            
            # PUSH DATA TO SIGNALS
            for name, sig in self.channel_map.items():
                data = collected_vals[name]
                avg = np.mean(data) if data else 0.0
                sig.put(avg)

        from ophyd.status import DeviceStatus
        status = DeviceStatus(self)
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        def _check_done():
            thread.join()
            status.set_finished()
        
        threading.Thread(target=_check_done, daemon=True).start()
        return status

# --- 2. BLUESKY SETUP ---
RE = RunEngine({})
bec = BestEffortCallback()
RE.subscribe(bec)

# Storage for CSV
scan_data = []

def collect_for_csv(name, doc):
    if name == 'start':
        scan_data.clear()
    if name == 'event':
        scan_data.append(doc['data'])
    if name == 'stop':
        if scan_data:
            df = pd.DataFrame(scan_data)
            df.to_csv("t8_scan_results.csv", index=False)
            print(f"\n[SUCCESS] Saved to t8_scan_results.csv")
            print(df.tail())

RE.subscribe(collect_for_csv)

# --- 3. EXECUTION ---
if __name__ == "__main__":
    # Note: Using the class with predefined Components
    t8 = LabJackMultiChannelDetector(name="t8")
    
    print("\nStarting Scan (T8 readings should now appear in table)...")
    try:
        RE(scan([t8], motor, -5, 5, 11))
    finally:
        if t8.handle:
            ljm.close(t8.handle)