"""
Simple script to verify the LabJack LJM library installation and version.

"""

# %%
import os
from labjack import ljm

# %%
print('### labjack python library version: ' + ljm.__version__ + ' ###')

# Print the installation path of the LJM library
print(f"LJM Library Location: {os.path.dirname(ljm.__file__)}")

