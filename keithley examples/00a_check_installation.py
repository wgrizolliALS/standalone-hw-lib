"""
Simple script to verify the Keithley library installation and version.

"""

# %%
import os
import sys
import serial

# This library
import keithley_utils as kthu
# %%

print(f"\n## Python version: {sys.version}")
print(f"Python executable: {sys.executable}")

print("\n### serial python library version: " + serial.__version__ + " ###")
# Print the installation path of the serial library
print(f"serial Library Location: {os.path.dirname(serial.__file__)}")

# Print the installation path of the keithley_utils library
print(f"\nkeithley_utils Library Location: {os.path.dirname(kthu.__file__)}\n")
