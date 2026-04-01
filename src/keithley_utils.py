import serial
import serial.tools.list_ports
import time

def detect_keithley_devices(baudrate=57600, timeout=0.5):
    """
    Scans all available serial ports and attempts to identify Keithley 6514 instruments.
    
    Returns:
        list: A list of dictionaries containing port info and IDN strings.
    """
    found_devices = []
    ports = serial.tools.list_ports.comports()
    
    for port in ports:
        try:
            # Attempt to open the port and query identification
            with serial.Serial(port.device, baudrate=baudrate, timeout=timeout) as ser:
                ser.write(b"*IDN?\n")
                # Wait slightly for the instrument to respond
                time.sleep(0.1)
                response = ser.readline().decode().strip()
                
                if response:
                    found_devices.append({
                        "port": port.device,
                        "description": port.description,
                        "idn": response,
                        "is_keithley": "KEITHLEY" in response.upper()
                    })
        except (serial.SerialException, UnicodeDecodeError):
            # Port busy or incompatible settings
            continue
            
    return found_devices

def print_keithley_devices(devices):
    """Formats and prints the detected serial devices to the console."""
    if not devices:
        print("No Keithley instruments detected on available serial ports.")
        return
        
    print(f"{'Port':<12} | {'Identification (IDN)'}")
    print("-" * 60)
    for dev in devices:
        status = "[✓]" if dev['is_keithley'] else "[?]"
        print(f"{dev['port']:<12} | {status} {dev['idn']}")

def scan_for_keithley():
    """Helper function to perform a full scan and print results."""
    print("Scanning serial ports for Keithley instruments...")
    devs = detect_keithley_devices()
    print_keithley_devices(devs)
    return devs