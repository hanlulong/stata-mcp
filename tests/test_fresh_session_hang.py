#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test: Fresh Stata session daemon thread PNG hang

This simulates the EXACT MCP server scenario:
1. Fresh PyStata initialization
2. Enable _gr_list on
3. Run do-file with PNG export in daemon thread
4. NO prior PNG initialization

This should replicate the Mac-specific hang issue.
"""

import sys
import os
import tempfile
import threading

STATA_PATH = '/Applications/StataNow/utilities'
sys.path.insert(0, STATA_PATH)

print("=" * 80)
print("FRESH SESSION TEST: Daemon Thread PNG Export (Mac Specific)")
print("=" * 80)

# Initialize PyStata (fresh session)
print("\n1. Fresh PyStata initialization...")
from pystata import config
config.init('mp')
from pystata import stata
from pystata.config import stlib, get_encode_str
print("   ✓ PyStata initialized (fresh session)")

# Enable _gr_list (like MCP server does)
print("\n2. Enabling _gr_list on...")
stlib.StataSO_Execute(get_encode_str("qui _gr_list on"), False)
print("   ✓ _gr_list enabled")

# Create test do-file
print("\n3. Creating test do-file with PNG export...")
test_content = """
clear
set obs 10
gen x = _n
gen y = _n + rnormal()
display "Creating graph..."
twoway scatter y x, name(freshtest, replace)
display "Exporting to PNG (this may hang on Mac in daemon thread)..."
graph export "test_fresh_hang.png", replace
display "SUCCESS: PNG export completed!"
"""

with tempfile.NamedTemporaryFile(mode='w', suffix='.do', delete=False) as f:
    f.write(test_content)
    test_file = f.name

print(f"   ✓ Test file created: {test_file}")

# Run in daemon thread (EXACTLY like MCP server)
print("\n4. Running do-file in DAEMON THREAD...")
print("   This simulates the MCP server execution model")
print("   Timeout: 20 seconds")
print("-" * 80)

error = None
hung = False

def run_stata_thread():
    global error
    try:
        stata.run(f'do "{test_file}"', echo=True, inline=False)
    except Exception as e:
        error = str(e)

stata_thread = threading.Thread(target=run_stata_thread)
stata_thread.daemon = True  # THIS IS KEY - daemon thread like MCP server
stata_thread.start()

print(f"\nThread started: {stata_thread}")
print(f"Is daemon: {stata_thread.daemon}")
print(f"Waiting for completion...\n")

stata_thread.join(timeout=20)

print("\n" + "-" * 80)

# Check result
if stata_thread.is_alive():
    print("RESULT: HUNG (Mac-specific bug confirmed!)")
    print("\nThe daemon thread is still alive after 20 seconds.")
    print("This confirms the Mac-specific PNG export hang in daemon threads.")
    print("\nWhy this happens on Mac:")
    print("  - Mac uses libstata-mp.dylib (dynamic library)")
    print("  - PNG export on Mac may use CoreGraphics/Quartz frameworks")
    print("  - These frameworks may require main thread initialization")
    print("  - Daemon threads may not have proper graphics context")
    hung = True
elif error:
    print(f"RESULT: ERROR - {error}")
else:
    print("RESULT: SUCCESS (PNG export completed)")
    print("\nThis means either:")
    print("  1. The issue was already fixed by earlier tests in this session")
    print("  2. The environment is different from MCP server environment")
    print("  3. Need to test in a completely isolated Python process")

# Cleanup
os.unlink(test_file)
if os.path.exists("test_fresh_hang.png"):
    os.unlink("test_fresh_hang.png")
    print("\n✓ Cleaned up PNG file")

print("\n" + "=" * 80)
if hung:
    print("CONCLUSION: Mac-specific daemon thread PNG hang CONFIRMED")
    print("\nThe one-time PNG initialization fix is necessary for Mac.")
    print("Windows likely doesn't have this issue because:")
    print("  - Different graphics subsystem (GDI/Direct2D)")
    print("  - Different threading model")
    print("  - stata-64.dll vs libstata-mp.dylib differences")
else:
    print("CONCLUSION: Could not replicate in this session")
    print("May need completely fresh process to replicate")
print("=" * 80)
