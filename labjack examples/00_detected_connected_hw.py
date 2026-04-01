'''
This is a utility script to verify that the LabJack LJM library is correctly 
installed and that the system can communicate with the hardware.

'''

# After running 'pip install -e .', you can import directly from the modules in src/
from labjack_utils import detect_labjacks, print_devices

if __name__ == "__main__":
      
      print('\n### Scan for LabJacks ###')
      devices = detect_labjacks()
      print('# Scan ENDED #\n')
      if devices:
            print(f"Found {len(devices)} device(s):")
            print_devices(devices)
      print('\n')
