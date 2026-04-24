"""
Simple script to verify the Keithley library installation and version.

"""

# %%
import os
import sys
import time

# This library
# %%

print(f"\n## Python version: {sys.version}")
print(f"Python executable: {sys.executable}")

# %%
try:
    import serial

    print("\n### SUCCESS: serial python library is installed ###")
    print("### serial python library version: " + serial.__version__ + " ###")
    # Print the installation path of the serial library
    print(f"serial Library Location: {os.path.dirname(serial.__file__)}")
except ImportError:
    print("\n### ERROR: serial python library not installed ###")

# %%
try:
    import keithley_utils as kthu

    print("\n### SUCCESS: keithley_utils python library is installed ###")
    # Print the installation path of the keithley_utils library
    print(f"keithley_utils Library Location: {os.path.dirname(kthu.__file__)}\n")
except ImportError:
    print("\n### ERROR: keithley_utils python library not installed ###\n")

# %%

print("DONE!\n")
