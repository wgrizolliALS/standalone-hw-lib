from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback
import bluesky.plan_stubs as bps

# Initialize the RunEngine
RE = RunEngine({})

# Optional: Add a callback to see live tables/plots if desired
# bec = BestEffortCallback()
# RE.subscribe(bec)

def test_voltage_reading(device_list):
    """
    Triggers and reads the current value of Ophyd devices.
    """
    print(f"\n{'--- probing channels ---':^40}")
    print(f"{'Channel Name':<25} | {'Voltage':<10}")
    print("-" * 40)

    def _read_plan():
        for device in device_list:
            # Yielding the 'read' message to the RunEngine
            val = yield from bps.rd(device)
            print(f"{device.name:<25} | {val:>8.4f} V")

    RE(_read_plan())
    print(f"{'--- test complete ---':^40}\n")

# --- EXECUTION ---
# Assuming 'chan1', 'chan2', etc., are your instantiated Ophyd objects
# Example: chan1 = EpicsSignal('PV_NAME_HERE', name='chan1')

try:
    # Pass your actual Ophyd object instances here
    test_voltage_reading([chan1, chan2, chan3])
except NameError:
    print("Error: Ensure your Ophyd objects (e.g., chan1) are initialized before running the test.")
    