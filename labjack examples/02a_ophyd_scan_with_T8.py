"""
This script provides a standalone test for the LabJackMultiChannelDetector class using Ophyd.
It demonstrates:
1. How to define a custom Ophyd Device for the LabJack T8.
2. How to implement an asynchronous trigger using Python threading.
3. How to handle both real hardware connections via LJM and simulated data.
4. A manual execution loop that triggers the device and reads back the averaged results.

This is useful for verifying hardware communication and Ophyd signal logic before 
integrating the device into a full Bluesky RunEngine scan.


"""


import time
from labjack import ljm

# --- THE DETECTOR CLASS ---
from ophyd_labjack_t8 import LabJackT8


# --- THE STANDALONE TEST ---
def test_detector():
    print("Starting Standalone Detector Test...")
    det = LabJackT8(name="test_lj", channels=[0, 1])
    
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