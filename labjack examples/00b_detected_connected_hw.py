"""
This is a utility script to verify that the LabJack LJM library is correctly
installed and that the system can communicate with the hardware.

"""

# After running 'pip install -e .', you can import directly from the modules in src/
import labjack_utils as lju

if __name__ == "__main__":
    print("\n### Scan for LabJacks ###")
    try:
        devices = lju.detect_labjacks()
        print("# Scan ENDED #\n")
        if devices:
            print(f"Found {len(devices)} device(s):")
            lju.print_devices(devices)
        print("\n")
    except Exception as e:
        print(f"Error during LabJack detection: {e}")
