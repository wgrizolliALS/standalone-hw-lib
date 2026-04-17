"""
Simple script to close all open connections to LabJack devices. This can be useful if you have accidentally left connections open in a previous session or if you want to ensure a clean slate before starting new work.

"""

import labjack_t8_ophyd as ljt8o

ljt8o.close_all_labjacks(verbose=True)
