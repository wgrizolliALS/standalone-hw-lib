"""
This example demonstrates how to use the LabJack T8 with the ophyd library in an asynchronous manner.

Summary:
1. We define a custom Ophyd Device for the LabJack T8, which includes methods for triggering and reading data.
2. We implement an asynchronous trigger using Python threading, allowing the main thread to remain responsive while waiting for the acquisition to complete.
3. The script handles both real hardware connections via LJM and simulated data, making it versatile for testing and development.
4. A manual execution loop triggers the device and reads back the averaged results.
5. This standalone test is useful for verifying hardware communication and Ophyd signal logic before integrating the device into a full Bluesky RunEngine scan.


"""

import time

# --- THE DETECTOR CLASS ---
from ophyd_labjack_t8 import LabJackT8


# --- THE STANDALONE TEST ---
def test_detector():
    print("[INFO] Starting Detector Test with Ophyd...")
    det = LabJackT8(name="test_lj", channels=[0, 1])
    print("[INFO] ophyd LabJackT8 instance created with channels: ", det.active_channels)

    for i in range(3):
        print(f"\n[INFO] Point {i + 1}:")

        print("[INFO] Triggering the detector...")
        status = det.trigger()
        print("[INFO] Detector triggered, waiting for acquisition to complete...")

        # Wait for the trigger to finish
        count = 0
        while not status.done:
            time.sleep(0.5)
            count += 1
            if count > 10:  # Safety timeout
                print("[TIMEOUT] Status never marked as done!")
                break

        # Check values
        readings = det.read()
        for key, val in readings.items():
            print(f"[RESULT] {key}: {val['value']}")  # type: ignore

    if det.handle:
        det.close()
        print("[INFO] Detector connection closed.")

    print("[INFO] Test Complete.")


if __name__ == "__main__":
    test_detector()
