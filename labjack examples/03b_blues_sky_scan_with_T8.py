"""
Bluesky Scan with LabJack T8 Multi-Channel Detector
This module demonstrates how to use the LabJackMultiChannelDetector with Bluesky to
perform a scan while recording data from multiple channels of the LabJack T8 device.
The workflow includes:
1. Initializing a RunEngine with the BestEffortCallback for real-time data visualization
2. Creating a LabJackMultiChannelDetector instance configured for channels 0, 1, and 2
3. Subscribing the detector's internal CSV saver to the RunEngine for automatic data logging
4. Executing a scan plan that moves a simulated motor from -5 to 5 in 11 steps while
    collecting detector data at each position
5. Properly closing the detector connection in a finally block to ensure resource cleanup
Key Features:
- Multi-channel data acquisition from LabJack T8 hardware
- Automatic CSV data export during scan execution
- Integration with Bluesky's scan plan infrastructure
- Ensures proper hardware resource management
Dependencies:
- bluesky: Experimental control framework
- ophyd: Control layer for hardware devices
- ophyd_local_labjack: Custom LabJack integration module
"""


import matplotlib.pyplot as plt
from bluesky import RunEngine
from bluesky.plans import scan, count
from bluesky.callbacks.best_effort import BestEffortCallback
from ophyd.sim import motor
from standalone_hw.labjack import LabJackT8 

# Initialize Bluesky
RE = RunEngine({})
RE.subscribe(BestEffortCallback())

# Initialize Hardware
t8 = LabJackT8(name="t8", channels=[0, 1, 2], act_time=1.0, sample_rate=1000.0)

# Link the internal saver
RE.subscribe(t8.csv_saver)

plt.ion()
try:
    # High-level command
    # RE(scan([t8], motor, -5, 5, 11))
    RE(count([t8]))
    
    plt.show(block=True) 
finally:
    t8.close()