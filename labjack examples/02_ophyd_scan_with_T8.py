import time
import threading
import numpy as np
from ophyd import Device, Signal
from labjack import ljm

# --- THE DETECTOR CLASS ---
class LabJackMultiChannelDetector(Device):
    def __init__(self, name, channels=[0], handle=None, **kwargs):
        self._ch_signals = {}
        self.channels = channels
        self.channel_names = [f"AIN{c}" for c in channels]
        super().__init__(name=name, **kwargs)

        for ch_name in self.channel_names:
            sig = Signal(name=f"{self.name}_{ch_name}", kind='hinted')
            self._ch_signals[ch_name] = sig
            setattr(self, ch_name, sig)
            self._signals[ch_name] = sig

        try:
            # Explicitly trying to open the handle
            self.handle = handle or ljm.openS("T8", "ANY", "ANY")
            print(f"--- Successfully connected to LabJack T8 ---")
        except Exception as e:
            print(f"--- LJM Connection FAILED: {e} ---")
            self.handle = None
        
        self.act_time = 1.0 
        self.sample_rate = 10.0

    def trigger(self):
        collected_vals = {name: [] for name in self.channel_names}
        print(f"  Triggered: Sampling for {self.act_time}s...")

        def _worker():
            interval = 1.0 / self.sample_rate
            t0 = time.time()
            while (time.time() - t0) < self.act_time:
                if self.handle:
                    try:
                        results = ljm.eReadNames(self.handle, len(self.channel_names), self.channel_names)
                        for name, val in zip(self.channel_names, results):
                            collected_vals[name].append(val)
                    except Exception as e:
                        print(f"  Error during eReadNames: {e}")
                else:
                    # Simulated Data
                    for name in self.channel_names:
                        collected_vals[name].append(np.random.rand())
                time.sleep(interval)
            
            for name in self.channel_names:
                data = collected_vals[name]
                avg = np.mean(data) if data else np.nan
                print(f"    Finished {name}: Captured {len(data)} samples. Mean: {avg}")
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

# --- THE STANDALONE TEST ---
def test_detector():
    print("Starting Standalone Detector Test...")
    det = LabJackMultiChannelDetector(name="test_lj", channels=[0, 1])
    
    for i in range(3):
        print(f"\nPoint {i+1}:")
        status = det.trigger()
        
        # Wait for the trigger to finish
        count = 0
        while not status.done:
            time.sleep(0.5)
            count += 1
            if count > 10: # Safety timeout
                print("  Timeout: Status never marked as done!")
                break
        
        # Check values
        readings = det.read()
        for key, val in readings.items():
            print(f"  Result -> {key}: {val['value']}")

    if det.handle:
        ljm.close(det.handle)
    print("\nTest Complete.")

if __name__ == "__main__":
    test_detector()