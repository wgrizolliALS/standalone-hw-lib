# %%

import time
from datetime import datetime

import keithley_utils as kthu


_help_text = "=" * 32 + " [HELP] " + "=" * 32 + "\n"
_help_text += """
[HELP] SCPI Command Query Terminal
[HELP] Type 'exit' or 'quit' to leave the program.
[HELP] Type '?' or 'help' to show this message again.

[HELP] Examples of SCPI commands to try:
    - *IDN?                   : Query device identification
    - :READ?                  : Query the latest measurement
    - :SYST:ERR?              : Query system error queue
    - :FORM:ELEM?             : Query data format elements
    - :FORM:DATA?             : Query data format type
    - :SYST:TIME:RESET        : Reset system time counter
    - :SYST:TIME?             : Query system time since last reset in seconds

[HELP] Tips:
    - Most queries end with '?'.
    - Use Ctrl+C to force exit at any time.
"""

# Numbered quick-command menu (type #<n> to send)
_numbered_commands = [
    ("*IDN?", "Query device identification"),
    (":SYST:ERR?", "Query system error queue"),
    ("*OPC?", "Query operation complete status. 1: complete, 0: busy"),
    (":READ?", "Query the latest measurement"),
    (":TRAC:DATA?", "Query trace data"),
    (":SYST:ZCH?", "Query zero check status. 1: on, 0: off"),
    (":SYST:ZCH ON", "Turn on zero check"),
    (":SYST:ZCH OFF", "Turn off zero check (for faster measurements)"),
    (":SYST:TIME:RESET", "Reset system time counter"),
    (":SYST:TIME?", "Query system time since last reset in seconds"),
    (":SENS:CURR:RANG:AUTO?", "Query current range autorange status. 1: on, 0: off"),
    (":SENS:CURR:RANG:AUTO ON", "Enable current range autorange"),
    (":SENS:CURR:RANG:AUTO OFF", "Disable current range autorange"),
    (":SENS:CURR:RANG?", "Query current range setting"),
    (":FORM:ELEM?", "Query data format elements"),
    (":FORM:DATA?", "Query data format type"),
    (":STAT:QUES:COND?", "Query questionable status register"),
    (":STAT:OPER:COND?", "Query operation status register"),
    (":CURR:NPLC?", "Query NPLC setting"),
    ("*RST", "Reset the instrument"),
]

# Append numbered menu to help text for display
_help_quick_cmd = "\n[HELP] Numbered quick-commands (type '#N' to run):\n"
for idx, (cmd, desc) in enumerate(_numbered_commands):
    _help_quick_cmd += f"    - #{idx}:\t{cmd:<20}\t{desc}\n"

_help_text += _help_quick_cmd
_help_text += "=" * 30 + " [END HELP] " + "=" * 30 + "\n"


def _colorStr(s, color=None, bold=False):
    color_codes = {
        "red": "91",
        "green": "92",
        "blue": "94",
        "purple": "95",
        "cyan": "96",
    }

    color_code = color_codes.get(color, "")  # type: ignore
    bold_code = "1;" if bold else ""
    return f"\033[{bold_code}{color_code}m{s}\033[0m"


def parse_input(s: str):
    """Parse input string and return command to execute or None.

    Returns:
        str or None: SCPI command string to execute, "EXIT" for exit, or None for no action
    """
    if not s:
        return None

    lower_s = s.lower()
    if lower_s in ("exit", "quit"):
        return "EXIT"
    elif lower_s in ("?", "help"):
        print(_help_text)
        return None
    elif lower_s in ("#", "#?"):
        print(_help_quick_cmd)
        return None
    elif lower_s.startswith("#"):
        try:
            i = int(s[1:])
            cmd = _numbered_commands[i][0]
            print(_colorStr(f"[INFO] Quick-Command Selected: #{i} -> {cmd}", color="green", bold=True))
            return cmd
        except (ValueError, IndexError):
            print(_colorStr("[ERROR] invalid quick-command index", color="red", bold=True))
            return None
    else:
        return s


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


def handle_input(s: str, serial_port: str) -> bool:
    """Parse and handle a single input string.

    Returns True to continue the REPL, False to exit.
    """
    command = parse_input(s)

    if command is None:
        return True
    elif command == "EXIT":
        return False
    else:
        kthu.serial_query(command, serial_port, verbose=True)

    while True:
        time.sleep(0.1)  # small delay to ensure command is processed before next query
        _res = kthu.serial_query(":SYST:ERR?", serial_port, verbose=True)
        if _res is not None and "0," in _res[0:2]:
            break
        else:
            kthu.print_verbose(
                "[WARNING] Instrument reports error after command. Check error ABOVE for details.",
                verbose=True,
                color="red",
                bold=True,
            )
    return True


def _datenowstr():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    """Main application entry point."""
    print("\n[INFO] ### Scan for Keithleys ###")
    try:
        devs = kthu.detect_keithley_devices(baudrate=None, verbose=True)
    except Exception as e:
        print(f"[ERROR] Error during Keithley detection: {e}")
        return

    print("[INFO] ### Scan ENDED ###\n")

    if not devs:
        print("[ERROR] No Keithley devices found. Exiting.")
        return

    dev = choose_device(devs)
    serial_port = dev["port"]

    print("[INFO] Selected device:")
    kthu.print_keithley_properties(dev)
    print("\n[INFO] Enter SCPI commands (type 'help' or '?' for help, 'exit' to quit)")

    try:
        while True:
            s = input(_colorStr("\n[INPUT] Enter Command:\n", color="cyan", bold=True)).strip()
            if not handle_input(s, serial_port):
                break
    except KeyboardInterrupt:
        print("\n[INFO] Cleaning up and exiting...")
        kthu.serial_query(":ABORT", serial_port, verbose=True)


# %%
if __name__ == "__main__":
    main()

# %%
