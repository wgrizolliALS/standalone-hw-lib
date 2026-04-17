"""
Simple script to close all open connections to LabJack devices. This can be useful if you have accidentally left connections open in a previous session or if you want to ensure a clean slate before starting new work.

"""

import labjackT8_utils as t8u

t8u.close_all_labjacks()
