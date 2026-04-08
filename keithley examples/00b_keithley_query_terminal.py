# %%

import keithley_utils as kthu

from datetime import datetime

_help_text = """
[INFO] SCPI Command Query Terminal
[INFO] Type 'exit' or 'quit' to leave the program.
[INFO] Type '?' or 'help' to show this message again.

[INFO] Examples of SCPI commands to try:
    - *IDN?                   : Query device identification
    - :READ?                  : Query the latest measurement
    - :SYST:ERR?              : Query system error queue
    - :STAT:QUES:COND?        : Query questionable status register
    - :STAT:OPER:COND?        : Query operation status register
    - :SYST:VERS?             : Query system firmware version
    - :SYST:COMM:LAN:IPAD?    : Query LAN IP address (if supported)
    - :SYST:COMM:SER:BAUD?    : Query serial baud rate (if supported)
    - :SYST:REM               : Set remote mode
    - :SYST:LOC               : Set local mode
    - :OUTP ON                : Enable output (if supported)
    - :OUTP OFF               : Disable output (if supported)
    - :SENS:CURR:RANG?        : Query current range setting
    - :SENS:VOLT:RANG?        : Query voltage range setting
    - :SENS:CURR:DC?          : Query current measurement
    - :SENS:VOLT:DC?          : Query voltage measurement
    - :SENS:CURR:NPLC?        : Query number of power line cycles for current measurement
    - :SENS:VOLT:NPLC?        : Query number of power line cycles for voltage measurement
    - :SENS:CURR:RANG:AUTO?   : Query if current range auto is enabled
    - :SENS:VOLT:RANG:AUTO?   : Query if voltage range auto is enabled
    - :TRIG:SOUR?             : Query trigger source
    - :TRIG:COUN?             : Query trigger count
    - :TRIG:DEL?              : Query trigger delay
    - :FORM:ELEM?             : Query data format elements
    - :FORM:DATA?             : Query data format type
    - :ROUT:TERM?             : Query terminal configuration
    - :ROUT:SCAN:SIZE?        : Query scan list size
    - :ROUT:SCAN:LSEL?        : Query scan list selection
    - :SYST:TIME:RESET        : Reset system time counter
    - :SYST:TIME?             : Query system time since last reset in seconds

[INFO] Tips:
    - Most queries end with '?'.
    - Use Ctrl+C to force exit at any time.
"""

# Numbered quick-command menu (type #<n> to send)
_numbered_commands = [
    ("*IDN?", "Query device identification"),
    (":READ?", "Query the latest measurement"),
    (":SYST:ERR?", "Query system error queue"),
    (":STAT:QUES:COND?", "Query questionable status register"),
    (":STAT:OPER:COND?", "Query operation status register"),
    (":SENS:CURR:RANG?", "Query current range setting"),
]

# Append numbered menu to help text for display
_help_quick_cmd = "\n[INFO] Numbered quick-commands (type '#N' to run):\n"
for idx, (cmd, desc) in enumerate(_numbered_commands):
    _help_quick_cmd += f"    - #{idx}: {cmd:<20} : {desc}\n"

_help_text += _help_quick_cmd


def choose_device(devs):
    if len(devs) == 1:
        return devs[0]
    print("[MENU] Select a device to query:")
    for i, d in enumerate(devs):
        print(f" - {i}: {d}")
    while True:
        sel = input("[INPUT] Enter device number: ")
        try:
            sel = int(sel)
            if 0 <= sel < len(devs):
                return devs[sel]
        except Exception:
            pass
        print(f"[ERROR] Enter an integer 0..{len(devs) - 1}.")


def handle_input(s: str) -> bool:
    """Parse and handle a single input string.

    Returns True to continue the REPL, False to exit.
    """
    if not s:
        return True
    ls = s.lower()
    if ls in ("exit", "quit"):
        return False
    if ls in ("?", "help"):
        print(_help_text)
        return True
    if s.startswith("#"):
        try:
            i = int(s[1:])
            cmd = _numbered_commands[i][0]
            print(f"[INFO] #{i} -> {cmd}")
            kthu.scpi_query(cmd, dev, verbose=True)
        except Exception:
            print("[ERROR] invalid quick-command index")
        return True
    kthu.scpi_query(s, dev, verbose=True)
    return True


# %%
if __name__ == "__main__":
    print("\n[INFO] ### Scan for Keithleys ###")
    try:
        devs = kthu.detect_keithley_devices(baudrate=None, verbose=True)
        print("[INFO] ### Scan ENDED ###\n")
    except Exception as e:
        print(f"[ERROR] Error during Keithley detection: {e}")

    if not devs:
        print("[ERROR] No Keithley devices found. Exiting.")
        raise SystemExit(1)

    dev = choose_device(devs)

    print("[INFO] Selected device:")
    kthu.print_dev_properties(dev)

    print("\n[INFO] Enter SCPI commands (type 'help' or '?' for help, 'exit' to quit)\n")
    try:
        while True:
            s = input(f"\n[INPUT] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - CMD: ").strip()
            if not handle_input(s):
                break
    except KeyboardInterrupt:
        print("\n[INFO] Exiting.")
