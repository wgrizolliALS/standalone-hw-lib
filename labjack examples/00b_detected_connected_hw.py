"""
This is a utility script to verify that the LabJack LJM library is correctly
installed and that the system can communicate with the hardware.

"""

# After running 'pip install -e .', you can import directly from the modules in src/
import labjack_t8_ophyd as ljt8o

if __name__ == "__main__":
    print("\n### Scan for LabJacks ###")
    try:
        devices = ljt8o.detect_labjacks(verbose=True)
        print("### Scan ENDED ###\n")
    except Exception as e:
        print(f"Error during LabJack detection: {e}")
