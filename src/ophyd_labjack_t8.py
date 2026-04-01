import csv
import time
import threading
import numpy as np
from datetime import datetime
from ophyd import Device, Signal

class LabJackT8(Device):
    """
    A self-contained Ophyd device for the LabJack T8.
    It handles:
    1. Hardware Connection (LJM)
    2. Asynchronous Triggering (Threading)
    3. Data Processing (Averaging for Bluesky)
    4. Data Logging (Self-contained CSV saving for Raw Data)  

    Parameters
    ---------- 

    name : str
        The name of the device for Ophyd/Bluesky.
    channels : list[int] | int | None, optional
        List of AIN channel indices to read (e.g., [0, 1] for AIN0 and AIN1).
    handle : str | None, optional
        An existing LJM handle. If None, a new connection is opened.
    act_time : float, optional
        The duration of the stream acquisition in seconds. Default is 0.5s.
    sample_rate : float, optional
        The sampling frequency in Hz. Default is 20.0 Hz.
    connectionType : str, optional
        LJM connection type (e.g., "USB", "ETHERNET", "ANY").
    identifier : str, optional
        LJM identifier (e.g., "ANY", or a specific serial number).
    csv_fname : str | None, optional
        Optional filename for the raw data CSV export.
        
    """


    def __init__(self, name, channels:list[int] | int | None=None,
                 handle:str| None=None,
                 act_time:float=0.5, sample_rate:float=20.0,
                 connectionType:str="ANY", identifier:str="ANY", 
                 csv_fname:str| None = None, 
                 verbose:bool = False,
                 **kwargs):

        
        super().__init__(name=name, **kwargs)
        if isinstance(channels, (int, float)):
            channels = [int(channels)]

        self.active_channels = channels if channels is not None else [0]
        self.channel_names = [f"AIN{c}" for c in self.active_channels]
        self._scan_results = []
        self.raw_block = Signal(name=f"{name}_raw_block", kind='omitted') # type: ignore
        self._ch_map = {}
        self._hint_fields = []
        self._csv_file = None
        self._csv_writer = None
        self.csv_fname = csv_fname

        self.verbose = verbose

        self.act_time = act_time
        self.sample_rate = sample_rate
        self.last_scan_actual_rate = None

        for ch in self.channel_names:
            full_name = f"{name}_{ch.lower()}"
            sig = Signal(name=full_name, kind='hinted')
            setattr(self, ch, sig)
            self._ch_map[ch] = sig
            self._hint_fields.append(full_name)

        from labjack import ljm
        try:
            self.handle = handle or ljm.openS("T8", connectionType, identifier)
            self.ljm_module = ljm
            if self.verbose:
                print("[STATUS] Succesfully Connected to LabJack T8")
                info = ljm.getHandleInfo(self.handle)
                print(f"[INFO] Connected Device: {info[0]}, Connection: {info[1]}, Serial: {info[2]}, IP: {info[3]}, Port: {info[4]}\n")
        except Exception as e:
            self.close()
            raise RuntimeError(f"[ERROR] LJM Connection FAILED: {e}")

    @property
    def hints(self):
        return {'fields': self._hint_fields}

    def trigger(self):
        samples = []
        scan_rate = self.sample_rate
        scans_per_read = int(scan_rate * self.act_time)
        
        def _worker():
            if self.verbose:
                    print(f"[INFO] {datetime.now()}: Aquisition STARTED.")
            try:
                aAddresses = self.ljm_module.namesToAddresses(len(self.channel_names), self.channel_names)[0]
                actual_rate = self.ljm_module.eStreamStart(self.handle, scans_per_read, len(aAddresses), aAddresses, scan_rate)
                self.last_scan_actual_rate = actual_rate
                ret = self.ljm_module.eStreamRead(self.handle)
                raw_data = ret[0]
                self.ljm_module.eStreamStop(self.handle)

                num_channels = len(self.channel_names)
                reshaped = np.array(raw_data).reshape(-1, num_channels)
                t0 = time.time() - self.act_time
                for i, row in enumerate(reshaped):
                    ts = t0 + (i / actual_rate)
                    samples.append([ts] + row.tolist())
                    
                for i, ch in enumerate(self.channel_names):
                    avg = np.mean(reshaped[:, i])
                    self._ch_map[ch].put(avg)

                try:
                    arr = np.array(samples, dtype=float)
                except Exception:
                    arr = np.array(samples, dtype=object)
                self.raw_block.put(arr)

                if self.verbose:
                    print(f"[INFO] {datetime.now()}: Aquisition FINISHED.")
                    print(f'[INFO] Acquired {len(reshaped)} samples from {num_channels} channels at {actual_rate:} Hz.\n')

            except Exception as e:
                print(f"[STREAM ERROR] : {e}")
                try:
                    self.ljm_module.eStreamStop(self.handle)
                except:
                    pass

        from ophyd.status import DeviceStatus
        status = DeviceStatus(self)
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        def _check_done():
            thread.join()
            status.set_finished()
        threading.Thread(target=_check_done, daemon=True).start()
        return status

    def read(self):
        res = super().read()
        res.update(self.raw_block.read())
        for sig in self._ch_map.values():
            res.update(sig.read())
        return res

    def describe(self):
        res = super().describe()
        num_channels = len(self.channel_names)
        scans_per_read = int(self.sample_rate * self.act_time)
        key = f"{self.name}_raw_block"
        res[key] = {
            'source': 'LabJackT8 raw block',
            'dtype': 'number',
            'shape': (scans_per_read, num_channels + 1),
        }
        for sig in self._ch_map.values():
            res.update(sig.describe())
        return res

    def csv_saver(self, name, doc):
        if name == 'start':
            self._scan_results.clear()
            self.csv_fname = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            self._csv_file = open(self.csv_fname, 'w', newline='', encoding='utf-8')
            fieldnames = ['Time', 'motor'] + self.channel_names
            self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=fieldnames)
            self._csv_writer.writeheader()

        if name == 'event':
            m_pos = doc.get('data', {}).get('motor', 0.0)
            raw_data = doc.get('data', {}).get(f'{self.name}_raw_block', [])
            for sample in raw_data:
                row = {'Time': datetime.fromtimestamp(sample[0]).strftime('%Y-%m-%d %H:%M:%S.%f'), 'motor': m_pos}
                for i, ch_name in enumerate(self.channel_names):
                    row[ch_name] = sample[i+1]
                self._scan_results.append(row)
                if self._csv_writer:
                    self._csv_writer.writerow(row)
            if self._csv_file:
                self._csv_file.flush()

        if name == 'stop':
            if self._csv_file:
                self._csv_file.close()
                print(f"\n[CSV] Saved {len(self._scan_results)} rows to {self.csv_fname}")
                self._csv_file = None

    def close(self):
        if hasattr(self, 'handle') and self.handle:
            self.ljm_module.close(self.handle)
            print("[INFO] LabJack connection closed.")