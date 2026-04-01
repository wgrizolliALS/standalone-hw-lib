import time
import threading
import numpy as np
import pandas as pd
from datetime import datetime
from ophyd import Device, Signal
import bluesky.plan_stubs as bps
from ophyd.sim import motor
from labjack import ljm
from bluesky import RunEngine
from bluesky.plans import scan
from bluesky.callbacks.best_effort import BestEffortCallback

# --- 1. THE DETECTOR CLASS ---
class LabJackMultiChannelDetector(Device):
    active_channels = [0, 1, 2] 

    def __init__(self, name, handle=None, **kwargs):
        super().__init__(name=name, **kwargs)
        self.channel_names = [f"AIN{c}" for c in self.active_channels]
        self._ch_map = {}
        self._hint_fields = []

        for ch_name in self.channel_names:
            full_name = f"{name}_{ch_name.lower()}"
            sig = Signal(name=full_name, kind='hinted')
            setattr(self, ch_name, sig)
            self._ch_map[ch_name] = sig
            self._hint_fields.append(full_name)

        try:
            self.handle = handle or ljm.openS("T8", "ANY", "ANY")
            print(f"--- Connected to LabJack T8 ---")
        except Exception as e:
            raise RuntimeError(f"Could not connect to LabJack: {e}")
        
        self.act_time = 0.5 
        self.sample_rate = 20.0

    @property
    def hints(self):
        return {'fields': self._hint_fields}

    def trigger(self):
        collected_vals = {name: [] for name in self.channel_names}
        def _worker():
            interval = 1.0 / self.sample_rate
            t0 = time.time()
            while (time.time() - t0) < self.act_time:
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
            thread.join(); status.set_finished()
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

# --- 2. BLUESKY SETUP & CSV SAVER ---
RE = RunEngine({})
RE.subscribe(BestEffortCallback())

scan_results = []

def csv_saver(name, doc):
    if name == 'start':
        scan_results.clear()
    if name == 'event':
        # Get current high-precision time
        dt_obj = datetime.fromtimestamp(doc['time'])
        formatted_time = dt_obj.strftime('%Y-%m-%d, %H:%M:%S.%f')[:-2] # 4 decimal places
        
        # Build the row dictionary
        row = {'timestamp': formatted_time}
        row.update(doc['data'])
        scan_results.append(row)
        
    if name == 'stop':
        if scan_results:
            df = pd.DataFrame(scan_results)
            
            # Clean Header: Ensure timestamp and motor are the first columns
            cols = df.columns.tolist()
            if 'timestamp' in cols: cols.insert(0, cols.pop(cols.index('timestamp')))
            if 'motor' in cols: cols.insert(1, cols.pop(cols.index('motor')))
            df = df[cols]
            
            filename = f"t8_scan_{datetime.now().strftime('%H%M%S')}.csv"
            df.to_csv(filename, index=False)
            print(f"\n[SUCCESS] Data saved to {filename}")

RE.subscribe(csv_saver)

# --- 3. EXECUTION ---
if __name__ == "__main__":
    t8 = LabJackMultiChannelDetector(name="t8")
    try:
        RE(scan([t8], motor, -5, 5, 11))

        # FINAL VOLTAGE TEST
        print("\n" + "="*50)
        print(f"{'Final Voltage Check (Snapshot)':^50}")
        print("-" * 50)
        def test_print_plan():
            yield from bps.trigger(t8, wait=True)
            for ch_num in t8.active_channels:
                ch_key = f"AIN{ch_num}"
                sig = getattr(t8, ch_key)
                val = yield from bps.rd(sig)
                print(f" Channel {ch_key:<5} | Current Voltage: {val:8.4f} V")
        RE(test_print_plan())
        print("="*50 + "\n")
    finally:
        if hasattr(t8, 'handle') and t8.handle:
            ljm.close(t8.handle)