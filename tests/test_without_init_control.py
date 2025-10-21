#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Control Test: WITHOUT one-time PNG initialization
This should HANG on first daemon thread PNG export to confirm the bug exists
"""

import sys
import os
import tempfile
import threading

STATA_PATH = '/Applications/StataNow/utilities'
sys.path.insert(0, STATA_PATH)

print("=" * 70)
print("CONTROL TEST: WITHOUT One-Time PNG Init (Should HANG)")
print("=" * 70)

print("\n1. SERVER STARTUP: Initializing PyStata...")
from pystata import config
config.init('mp')
from pystata import stata
from pystata.config import stlib, get_encode_str

stlib.StataSO_Execute(get_encode_str("qui _gr_list on"), False)
print("   ✓ PyStata initialized")
print("   ✓ _gr_list enabled")

# SKIP PNG INITIALIZATION (this is the control - no fix applied)
print("\n2. SKIPPING PNG INITIALIZATION")
print("   (This is the control test - no fix applied)\n")

print("=" * 70)
print("3. RUNNING FIRST REQUEST IN DAEMON THREAD")
print("=" * 70)

test_content = """
clear
set obs 10
gen x = _n
gen y = _n
twoway scatter y x, name(test1, replace)
display "About to export PNG in daemon thread WITHOUT initialization..."
graph export "test_control.png", replace
display "SUCCESS (if you see this!)"
"""

with tempfile.NamedTemporaryFile(mode='w', suffix='.do', delete=False) as f:
    f.write(test_content)
    test_file = f.name

error = None
def run_in_daemon():
    global error
    try:
        stata.run(f'do "{test_file}"', echo=False, inline=False)
    except Exception as e:
        error = str(e)

print("\n--- Request 1: Running do-file in daemon thread (15s timeout) ---")
thread = threading.Thread(target=run_in_daemon)
thread.daemon = True
thread.start()
thread.join(timeout=15)

print("\n" + "=" * 70)
if thread.is_alive():
    print("✓ CONTROL TEST RESULT: Request HUNG as expected!")
    print("=" * 70)
    print("\nThis confirms the bug exists without the fix!")
    print("The one-time PNG initialization is necessary.")
else:
    if error:
        print(f"✗ ERROR: {error}")
    else:
        print("✗ UNEXPECTED: Request succeeded without initialization")
        print("   (May indicate different environment or timing)")

os.unlink(test_file)
if os.path.exists("test_control.png"):
    os.unlink("test_control.png")
