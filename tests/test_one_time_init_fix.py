#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Verification Test: One-time PNG initialization at startup fixes daemon thread hang

This test simulates the MCP server behavior:
1. Initialize PyStata once (server startup)
2. Do ONE-TIME PNG initialization in main thread
3. Run multiple do-files with PNG export in daemon threads (multiple user requests)
4. Verify all PNG exports complete successfully

If this test passes, it proves the fix will work!
"""

import sys
import os
import tempfile
import threading
import time

STATA_PATH = '/Applications/StataNow/utilities'
sys.path.insert(0, STATA_PATH)

print("=" * 70)
print("VERIFICATION TEST: One-Time PNG Init at Startup")
print("=" * 70)

# ==============================================================================
# STEP 1: Server Startup - Initialize PyStata
# ==============================================================================
print("\n1. SERVER STARTUP: Initializing PyStata...")
from pystata import config
config.init('mp')
from pystata import stata
from pystata.config import stlib, get_encode_str

stlib.StataSO_Execute(get_encode_str("qui _gr_list on"), False)
print("   ✓ PyStata initialized")
print("   ✓ _gr_list enabled")

# ==============================================================================
# STEP 2: One-time PNG Initialization (proposed fix)
# ==============================================================================
print("\n2. ONE-TIME PNG INITIALIZATION (THE FIX)...")
print("   This runs ONCE at server startup in main thread")
print("-" * 70)

try:
    # Create minimal dataset
    stlib.StataSO_Execute(get_encode_str("qui clear"), False)
    stlib.StataSO_Execute(get_encode_str("qui set obs 2"), False)
    stlib.StataSO_Execute(get_encode_str("qui gen x=1"), False)
    stlib.StataSO_Execute(get_encode_str("qui twoway scatter x x, name(_init, replace)"), False)

    # Export to PNG to initialize PNG subsystem
    png_init = os.path.join(tempfile.gettempdir(), "_stata_png_init.png")
    stlib.StataSO_Execute(get_encode_str(f'qui graph export "{png_init}", name(_init) replace width(10) height(10)'), False)
    stlib.StataSO_Execute(get_encode_str("qui graph drop _init"), False)

    # Cleanup
    if os.path.exists(png_init):
        os.unlink(png_init)

    print("   ✓ PNG initialization completed")
    print("   ✓ Cleanup done")
    init_success = True
except Exception as e:
    print(f"   ✗ PNG initialization failed: {e}")
    init_success = False

if not init_success:
    print("\n✗ FAILED: Could not initialize PNG")
    sys.exit(1)

print("-" * 70)
print("   Server is ready to handle user requests!\n")

# ==============================================================================
# STEP 3: Simulate Multiple User Requests (daemon threads)
# ==============================================================================
print("=" * 70)
print("3. SIMULATING MULTIPLE USER REQUESTS")
print("=" * 70)

def create_test_do(test_num, graph_name):
    """Create a test do-file with PNG export"""
    content = f"""
clear
set obs 15
gen x = _n
gen y = _n + rnormal()
twoway scatter y x, name({graph_name}, replace) title("Test {test_num}")
display "Test {test_num}: About to export PNG in daemon thread..."
graph export "test_request_{test_num}.png", replace
display "Test {test_num}: PNG export SUCCESS!"
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.do', delete=False) as f:
        f.write(content)
        return f.name

def run_do_in_daemon(do_file, test_num, results):
    """Run do-file in daemon thread (like MCP server does)"""
    error = None
    try:
        stata.run(f'do "{do_file}"', echo=False, inline=False)
    except Exception as e:
        error = str(e)
    results[test_num] = {'error': error, 'hung': False}

# Test multiple consecutive requests
num_tests = 3
results = {}

for i in range(1, num_tests + 1):
    print(f"\n--- Request {i}: Running do-file in daemon thread ---")

    # Create test do-file
    test_file = create_test_do(i, f"test{i}")

    # Run in daemon thread (simulating MCP server request handler)
    thread = threading.Thread(target=run_do_in_daemon, args=(test_file, i, results))
    thread.daemon = True
    thread.start()
    thread.join(timeout=15)

    # Check result
    if thread.is_alive():
        print(f"   ✗ Request {i}: HUNG (thread still alive)")
        results[i] = {'error': None, 'hung': True}
    elif i in results and results[i]['error']:
        print(f"   ✗ Request {i}: ERROR - {results[i]['error']}")
    else:
        print(f"   ✓ Request {i}: SUCCESS")

    # Cleanup
    os.unlink(test_file)
    if os.path.exists(f"test_request_{i}.png"):
        os.unlink(f"test_request_{i}.png")

    time.sleep(0.5)  # Brief pause between requests

# ==============================================================================
# STEP 4: Results Summary
# ==============================================================================
print("\n" + "=" * 70)
print("VERIFICATION RESULTS")
print("=" * 70)

all_passed = True
for i in range(1, num_tests + 1):
    if results[i]['hung']:
        print(f"Request {i}: ✗ HUNG")
        all_passed = False
    elif results[i]['error']:
        print(f"Request {i}: ✗ ERROR - {results[i]['error']}")
        all_passed = False
    else:
        print(f"Request {i}: ✓ PASSED")

print("=" * 70)

if all_passed:
    print("\n" + "🎉" * 20)
    print("✓✓✓ VERIFICATION SUCCESSFUL ✓✓✓")
    print("🎉" * 20)
    print("\nCONCLUSION:")
    print("One-time PNG initialization at server startup FIXES the issue!")
    print("\nThe fix is safe to implement in the MCP server:")
    print("1. Add PNG initialization code after line 206 in stata_mcp_server.py")
    print("2. This runs ONCE at startup in main thread")
    print("3. All subsequent daemon thread PNG exports will work")
    print("4. No impact on user data or operations")
else:
    print("\n✗ VERIFICATION FAILED")
    print("One-time initialization is NOT sufficient")
    print("Need to investigate further")
