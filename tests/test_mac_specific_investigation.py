#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mac-Specific PNG Hang Investigation

Goal: Understand why PNG export hangs in daemon threads on Mac but not Windows
We'll investigate:
1. Threading model differences
2. Graphics subsystem initialization
3. PyStata platform-specific code paths
4. GCD (Grand Central Dispatch) vs Windows threading
"""

import sys
import os
import platform
import threading

STATA_PATH = '/Applications/StataNow/utilities'
sys.path.insert(0, STATA_PATH)

print("=" * 80)
print("MAC-SPECIFIC PNG HANG INVESTIGATION")
print("=" * 80)

# Platform info
print(f"\nPlatform: {platform.system()}")
print(f"Platform Version: {platform.version()}")
print(f"Python Version: {sys.version}")
print(f"Threading implementation: {threading.current_thread()}")

# Initialize PyStata
print("\n" + "=" * 80)
print("STEP 1: Initialize PyStata and check threading model")
print("=" * 80)

from pystata import config
config.init('mp')
from pystata import stata
from pystata.config import stlib, get_encode_str

print(f"PyStata config module: {config.__file__}")
print(f"Main thread: {threading.main_thread()}")
print(f"Current thread: {threading.current_thread()}")
print(f"Active threads: {threading.active_count()}")

# Check for Mac-specific threading issues
print("\n" + "=" * 80)
print("STEP 2: Check PyStata internals for Mac-specific code")
print("=" * 80)

# Read PyStata stata.py to check for platform-specific code
stata_py_path = os.path.join(STATA_PATH, 'pystata', 'stata.py')
print(f"\nReading: {stata_py_path}")

with open(stata_py_path, 'r') as f:
    stata_py_content = f.read()

# Look for platform checks
if 'darwin' in stata_py_content.lower() or 'platform' in stata_py_content:
    print("✓ Found platform-specific code in stata.py")
    # Extract relevant lines
    lines = stata_py_content.split('\n')
    for i, line in enumerate(lines):
        if 'platform' in line.lower() or 'darwin' in line.lower() or 'macos' in line.lower():
            print(f"  Line {i+1}: {line.strip()}")
else:
    print("  No obvious platform checks in stata.py")

# Check graph display module
print("\n" + "=" * 80)
print("STEP 3: Check graph display for Mac-specific behavior")
print("=" * 80)

grdisplay_path = os.path.join(STATA_PATH, 'pystata', 'ipython', 'grdisplay.py')
if os.path.exists(grdisplay_path):
    print(f"\nReading: {grdisplay_path}")
    with open(grdisplay_path, 'r') as f:
        grdisplay_content = f.read()

    if 'darwin' in grdisplay_content.lower() or 'platform' in grdisplay_content:
        print("✓ Found platform-specific code in grdisplay.py")
        lines = grdisplay_content.split('\n')
        for i, line in enumerate(lines):
            if 'platform' in line.lower() or 'darwin' in line.lower() or 'macos' in line.lower():
                print(f"  Line {i+1}: {line.strip()}")
    else:
        print("  No obvious platform checks in grdisplay.py")

# Check config.py for platform differences
print("\n" + "=" * 80)
print("STEP 4: Check config.py for platform-specific initialization")
print("=" * 80)

config_path = os.path.join(STATA_PATH, 'pystata', 'config.py')
print(f"\nReading: {config_path}")
with open(config_path, 'r') as f:
    config_content = f.read()

if 'darwin' in config_content.lower() or 'platform' in config_content:
    print("✓ Found platform-specific code in config.py")
    lines = config_content.split('\n')
    for i, line in enumerate(lines):
        if 'platform' in line.lower() or 'darwin' in line.lower() or 'windows' in line.lower():
            print(f"  Line {i+1}: {line.strip()}")

# Check for Mac-specific graphics libraries
print("\n" + "=" * 80)
print("STEP 5: Check for Mac graphics framework dependencies")
print("=" * 80)

# On Mac, PNG export might use CoreGraphics or other Mac frameworks
import importlib.util

frameworks_to_check = [
    'CoreGraphics',
    'Quartz',
    'AppKit',
    'Foundation'
]

print("\nChecking for Mac framework imports:")
for framework in frameworks_to_check:
    spec = importlib.util.find_spec(framework)
    if spec:
        print(f"  ✓ {framework}: Available at {spec.origin}")
    else:
        print(f"  ✗ {framework}: Not found")

# Test daemon thread with verbose output
print("\n" + "=" * 80)
print("STEP 6: Test PNG export with thread state inspection")
print("=" * 80)

stlib.StataSO_Execute(get_encode_str("qui _gr_list on"), False)

import tempfile

test_content = """
clear
set obs 5
gen x = _n
gen y = _n
twoway scatter y x, name(mactest, replace)
graph export "test_mac_investigation.png", replace
"""

with tempfile.NamedTemporaryFile(mode='w', suffix='.do', delete=False) as f:
    f.write(test_content)
    test_file = f.name

print(f"\nCreated test file: {test_file}")

# Test 1: Main thread
print("\n--- Test 1: Main thread PNG export ---")
print(f"Current thread: {threading.current_thread()}")
print(f"Is daemon: {threading.current_thread().daemon}")
print(f"Thread ident: {threading.current_thread().ident}")

try:
    stata.run(f'do "{test_file}"', echo=False, inline=False)
    print("✓ Main thread PNG export: SUCCESS")
except Exception as e:
    print(f"✗ Main thread PNG export: FAILED - {e}")

# Cleanup
if os.path.exists("test_mac_investigation.png"):
    os.unlink("test_mac_investigation.png")

# Test 2: Regular (non-daemon) thread
print("\n--- Test 2: Non-daemon thread PNG export ---")

result = {'success': False, 'error': None}

def run_in_regular_thread():
    print(f"  Thread: {threading.current_thread()}")
    print(f"  Is daemon: {threading.current_thread().daemon}")
    print(f"  Thread ident: {threading.current_thread().ident}")
    try:
        stata.run(f'do "{test_file}"', echo=False, inline=False)
        result['success'] = True
    except Exception as e:
        result['error'] = str(e)

thread = threading.Thread(target=run_in_regular_thread)
thread.daemon = False  # Non-daemon
thread.start()
thread.join(timeout=15)

if thread.is_alive():
    print("✗ Non-daemon thread: HUNG")
elif result['error']:
    print(f"✗ Non-daemon thread: ERROR - {result['error']}")
else:
    print("✓ Non-daemon thread PNG export: SUCCESS")

if os.path.exists("test_mac_investigation.png"):
    os.unlink("test_mac_investigation.png")

# Test 3: Daemon thread (the problematic case)
print("\n--- Test 3: Daemon thread PNG export ---")

result = {'success': False, 'error': None}

def run_in_daemon_thread():
    print(f"  Thread: {threading.current_thread()}")
    print(f"  Is daemon: {threading.current_thread().daemon}")
    print(f"  Thread ident: {threading.current_thread().ident}")
    try:
        stata.run(f'do "{test_file}"', echo=False, inline=False)
        result['success'] = True
    except Exception as e:
        result['error'] = str(e)

thread = threading.Thread(target=run_in_daemon_thread)
thread.daemon = True  # Daemon
thread.start()
thread.join(timeout=15)

if thread.is_alive():
    print("✗ Daemon thread: HUNG (this is the Mac-specific bug!)")
    print("  Thread is still alive after 15s timeout")
elif result['error']:
    print(f"✗ Daemon thread: ERROR - {result['error']}")
else:
    print("✓ Daemon thread PNG export: SUCCESS")

# Cleanup
os.unlink(test_file)
if os.path.exists("test_mac_investigation.png"):
    os.unlink("test_mac_investigation.png")

print("\n" + "=" * 80)
print("INVESTIGATION COMPLETE")
print("=" * 80)
print("\nKey findings will help identify Mac-specific threading issues")
print("Look for:")
print("  1. Platform-specific code paths in PyStata")
print("  2. Differences between daemon and non-daemon threads")
print("  3. Mac framework dependencies for PNG export")
print("  4. Whether non-daemon threads also hang (rules out daemon-specific issue)")
