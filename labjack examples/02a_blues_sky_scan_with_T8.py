'''
This example demonstrates how to integrate a LabJack T8 multi-channel data logger with Bluesky.
Key features:
0. EVERYTHIN IN A SIGLE FILE: The entire workflow is contained in one script for simplicity.
1. Hardware Connection: Uses LJM to connect to the T8 and read multiple channels.
2. Asynchronous Triggering: Implements a non-blocking trigger method that collects data for a specified duration.
3. Data Processing: Averages the collected samples for each channel to provide a single value per
scan step, which is displayed in the Bluesky terminal table.
4. Data Logging: Stores the full list of raw samples in a 'normal' signal and saves it to a CSV file at the end of the scan.
This example is designed to be run in a Python environment with access to the LabJack hardware and the necessary libraries installed.



'''

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
    """
    A self-contained Ophyd device for the LabJack T8.
    It handles:
    1. Hardware Connection (LJM)
    2. Asynchronous Triggering (Threading)
    3. Data Processing (Averaging for Bluesky)
    4. Data Logging (Self-contained CSV saving for Raw Data)
    """
    def __init__(self, name, channels=None, handle=None, **kwargs):
        super().__init__(name=name, **kwargs)
        self.active_channels = channels if channels is not None else [0]
        self.channel_names = [f"AIN{c}" for c in self.active_channels]
        
        # Internal buffer to store every raw sample for the CSV export
        self._scan_results = []
        
        # raw_block is a 'normal' signal: it's recorded in the background
        # but doesn't clutter the terminal table.
        self.raw_block = Signal(name=f"{name}_raw_block", kind='normal')
        
        self._ch_map = {}
        self._hint_fields = []

        # Generate signals for each channel (e.g., t8_ain0)
        for ch in self.channel_names:
            full_name = f"{name}_{ch.lower()}"
            # 'hinted' tells BestEffortCallback: "Put this in the Live Table!"
            sig = Signal(name=full_name, kind='hinted')
            setattr(self, ch, sig)
            self._ch_map[ch] = sig
            self._hint_fields.append(full_name)

        try:
            self.handle = handle or ljm.openS("T8", "ANY", "ANY")
            print(f"--- Connected to LabJack T8 ---")
        except Exception as e:
            raise RuntimeError(f"LJM Connection FAILED: {e}")
        
        # Default sampling parameters
        self.act_time = 0.5 
        self.sample_rate = 20.0

    @property
    def hints(self):
        """Used by BestEffortCallback to build the terminal table."""
        return {'fields': self._hint_fields}

    def trigger(self):
        """Called by Bluesky at every scan step."""
        samples = []
        def _worker():
            t0 = time.time()
            while (time.time() - t0) < self.act_time:
                ts = time.time()
                # Read voltages from hardware
                results = ljm.eReadNames(self.handle, len(self.channel_names), self.channel_names)
                samples.append([ts] + results)
                time.sleep(1.0 / self.sample_rate)
            
            # 1. Update 'hinted' signals with the Mean for the Live Table
            arr = np.array(samples)
            for i, ch in enumerate(self.channel_names):
                avg = np.mean(arr[:, i+1]) if len(samples) > 0 else 0.0
                self._ch_map[ch].put(avg)
            
            # 2. Store the full list of raw sub-samples for the CSV Saver
            self.raw_block.put(samples)

        from ophyd.status import DeviceStatus
        status = DeviceStatus(self)
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        def _check_done():
            thread.join()
            status.set_finished()
        threading.Thread(target=_check_done, daemon=True).start()
        return status

    # --- OPHYD BOILERPLATE ---
    # We override these to ensure the dynamic 'raw_block' is included in the scan data
    def read(self):
        res = super().read()
        res.update(self.raw_block.read())
        for sig in self._ch_map.values():
            res.update(sig.read())
        return res

    def describe(self):
        res = super().describe()
        res.update(self.raw_block.describe())
        for sig in self._ch_map.values():
            res.update(sig.describe())
        return res

    # --- INTEGRATED CSV SAVER ---
    def csv_saver(self, name, doc):
        """
        A callback method that listens to the Bluesky document stream.
        This 'explodes' the raw data buffer into individual rows in a CSV.
        """
        if name == 'start':
            self._scan_results.clear()
            
        if name == 'event':
            # Extract motor position and the raw block specific to THIS detector
            m_pos = doc['data'].get('motor', 0.0)
            raw_data = doc['data'].get(f'{self.name}_raw_block', [])
            
            for sample in raw_data:
                # Convert Unix timestamp to human-readable format
                dt_obj = datetime.fromtimestamp(sample[0])
                formatted_time = dt_obj.strftime('%Y-%m-%d, %H:%M:%S.%f')[:-2]
                
                row = {'Time': formatted_time, 'motor': m_pos}
                for i, ch_name in enumerate(self.channel_names):
                    row[ch_name] = sample[i+1]
                self._scan_results.append(row)
                
        if name == 'stop':
            if self._scan_results:
                df = pd.DataFrame(self._scan_results)
                
                # Reorder columns so Time and Motor are on the left
                cols = df.columns.tolist()
                if 'Time' in cols: cols.insert(0, cols.pop(cols.index('Time')))
                if 'motor' in cols: cols.insert(1, cols.pop(cols.index('motor')))
                df = df[cols]
                
                fname = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                df.to_csv(fname, index=False)
                print(f"\n[CSV] Device '{self.name}' saved {len(df)} rows to {fname}")

# --- 2. EXECUTION ---
RE = RunEngine({})

# BestEffortCallback (BEC) provides the "Dashboard":
# 1. Live Table: Formats the terminal output based on our 'hinted' signals.
# 2. Live Plots: Automatically graphs motor vs. voltages (if matplotlib is active).
# 3. Status: Prints IDs and timestamps for situational awareness.
bec = BestEffortCallback()
RE.subscribe(bec)

if __name__ == "__main__":
    # Create the detector instance
    t8 = LabJackMultiChannelDetector(name="t8", channels=[0, 1, 2])
    
    # We subscribe the detector's own logging method to the RunEngine.
    # This keeps our data preservation logic inside the hardware class.
    RE.subscribe(t8.csv_saver)
    
    try:
        # Step the motor, trigger T8, display table (via BEC), save file (via csv_saver)
        RE(scan([t8], motor, -5, 5, 11))
    finally:
        if hasattr(t8, 'handle') and t8.handle:
            ljm.close(t8.handle)
            print("LabJack connection closed.")