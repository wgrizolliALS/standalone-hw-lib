import time
import serial
from ophyd import Device, DeviceStatus

class Keithley6514Burst(Device):
    def __init__(self, port, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ser = serial.Serial(port, baudrate=57600, timeout=20)
        self.num_points = 2500 
        self._manual_range = "2e-9" 
        self._last_chosen_range = None

    def set_range(self, val):
        self._manual_range = str(val)
        print(f"Manual range set to: {self._manual_range}")

    def _do_autorange_scout(self):
        print("\n[Scout] Finding optimal range...")
        self._ser.write(b":SENS:CURR:RANG:AUTO ON\n")
        time.sleep(2.0)
        self._ser.write(b":SENS:CURR:RANG?\n")
        chosen_range = self._ser.readline().decode().strip()
        self._ser.write(b":SENS:CURR:RANG:AUTO OFF\n")
        print(f"** [Scout Result] Optimal range found: {chosen_range} Amps **")
        self._last_chosen_range = chosen_range
        return chosen_range

    def kickoff(self, use_autorange=False):
        self._status = DeviceStatus(self)
        selected_range = self._do_autorange_scout() if use_autorange else self._manual_range
        cmds = [
            "*RST", ":FORM:ELEM READ", ":SENS:FUNC 'CURR'",
            f":SENS:CURR:RANG {selected_range}", ":SENS:CURR:RANG:AUTO OFF",
            ":SENS:CURR:NPLC 0.01", ":SYST:AZER OFF", ":DISP:ENAB OFF",
            ":TRAC:CLE", f":TRAC:POIN {self.num_points}", ":TRAC:FEED SENS",
            ":TRAC:FEED:CONT NEXT"
        ]
        for cmd in cmds:
            self._ser.write(f"{cmd}\n".encode())
        self._status.set_finished()
        return self._status

    def complete(self):
        status = DeviceStatus(self)
        time.sleep(2.5) 
        status.set_finished()
        return status

    def collect(self):
        self._ser.write(b":TRAC:DATA?\n")
        raw_data = self._ser.read_until(b'\n').decode()
        raw_vals = [float(x) for x in raw_data.split(',') if x.strip()]
        clean_vals = [x if x < 9e36 else float('nan') for x in raw_vals]
        self._ser.write(b":DISP:ENAB ON\n")
        yield {
            'data': {'keithley_waveform': clean_vals},
            'timestamps': {'keithley_waveform': time.time()},
            'time': time.time()
        }

    def describe_collect(self):
        return {'keithley_burst': {
            'keithley_waveform': {
                'source': f'Serial:{self._ser.port}',
                'dtype': 'array',
                'shape': [self.num_points]
            }
        }}