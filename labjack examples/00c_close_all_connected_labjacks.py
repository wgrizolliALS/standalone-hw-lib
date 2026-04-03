"""
Simple script to close all open connections to LabJack devices. This can be useful if you have accidentally left connections open in a previous session or if you want to ensure a clean slate before starting new work.

"""

from labjack import ljm

try:
    res = ljm.listAllS("ANY", "ANY")
    print('ljm.listAllS("ANY", "ANY") OUTPUT:')
    print(res)
    ljm.closeAll()

except Exception as e:
    print(f"[ERROR] Error during ljm.listAllS:\n\t{e}\nAttempting to close all handles with ljm.closeAll()...")
    ljm.closeAll()
    try:  # check if closeAll worked
        res2 = ljm.listAllS("ANY", "ANY")
        print('After ljm.closeAll(), ljm.listAllS("ANY", "ANY") OUTPUT:')
        print(res2)
    except Exception as e2:
        print(f"[ERROR] Still failed during ljm.listAllS after closeAll:\n\t{e2}")
    exit(1)

print("[INFO] All LabJack connections closed successfully.")
