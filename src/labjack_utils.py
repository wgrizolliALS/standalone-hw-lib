from labjack import ljm

def detect_labjacks():
      devices = []
      try:
            res = ljm.listAllS("ANY", "ANY")
            num_devices = res[0]
            for i in range(num_devices):
                  device_info = {
                        "type": res[1][i],
                        "connection": res[2][i],
                        "serial": res[3][i],
                        "ip": ljm.numberToIP(res[4][i]),
                        "port": None,
                        "usb_address": None
                  }
                  try:
                        handle = ljm.openS("ANY", "ANY", device_info["serial"])
                        info = ljm.getHandleInfo(handle)
                        if len(info) > 4:
                              device_info["port"] = info[4]
                        if device_info["connection"] == 1:
                              try:
                                    device_info["usb_address"] = ljm.eReadName(handle, "DEVICE_PATH_USB")
                              except:
                                    pass
                        ljm.close(handle)
                  except ljm.LJMError:
                        # Device might be in use or disconnected
                        device_info["port"] = "Busy/Error"
                  devices.append(device_info)
      except ljm.LJMError as e:
            print(f"Error listing LabJacks: {e}")
      return devices

def print_devices(devices):
      if not devices:
            print("No LabJack devices found.")
            return
      connection_map = {1: "USB", 2: "ETH", 3: "Wireless"}
      for idx, dev in enumerate(devices, 1):
            conn_name = connection_map.get(dev['connection'], f"Unknown({dev['connection']})")
            port_info = f", Port: {dev['port']}" if dev.get('port') else ""
            usb_info = f", USB Address: {dev['usb_address']}" if dev.get('usb_address') else ""
            print(f"[{idx}] Device type: {dev['type']}, Connection: {conn_name}, Serial: {dev['serial']}, IP: {dev['ip']}{port_info}{usb_info}")

def scan_for_labjacks():
      devices = detect_labjacks()
      print_devices(devices)
      return devices