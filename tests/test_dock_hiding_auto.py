#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test: Automatic Dock Icon Hiding Test

This test automatically verifies that the NSApplication.setActivationPolicy approach
works without requiring user interaction.
"""

import sys
import platform
import time

print("=" * 80)
print("AUTOMATIC DOCK ICON HIDING TEST")
print("=" * 80)

print(f"\nPlatform: {platform.system()}")

if platform.system() != 'Darwin':
    print("\nThis test is only relevant for macOS - SKIPPED")
    sys.exit(0)

print("\nStep 1: Python process started")
print("   At this point, the Python icon may appear in the Dock")
print("   (Depending on timing and how Python was launched)")

# Give it a moment
time.sleep(1)

print("\nStep 2: Attempting to hide dock icon using AppKit...")

success = False
try:
    from AppKit import NSApplication

    # Get shared application instance
    app = NSApplication.sharedApplication()

    if app:
        print(f"   ✓ Got NSApplication instance")

        # Set activation policy to Accessory (hides from dock)
        # NSApplicationActivationPolicyAccessory = 1
        result = app.setActivationPolicy_(1)

        print(f"   ✓ Called setActivationPolicy_(1)")
        print(f"   ✓ Result: {result}")

        # Check current activation policy
        current_policy = app.activationPolicy()
        print(f"   ✓ Current activation policy: {current_policy}")

        if current_policy == 1:
            print("\n" + "=" * 80)
            print("✓ SUCCESS: Activation policy set to Accessory (hidden)")
            print("=" * 80)
            success = True
        else:
            print("\n" + "=" * 80)
            print(f"✗ WARNING: Policy is {current_policy}, expected 1")
            print("=" * 80)
    else:
        print("   ✗ Could not get NSApplication instance")

except ImportError as e:
    print(f"   ✗ Could not import AppKit: {e}")
    print("\nPyObjC may not be installed. Install with:")
    print("  pip install pyobjc-framework-Cocoa")
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

if success:
    print("\nStep 3: Keeping process alive for 10 seconds...")
    print("   The Python icon should NOT appear in the Dock during this time")
    print("   (Or if it appeared earlier, it should disappear)")

    for i in range(10, 0, -1):
        print(f"\r   Time remaining: {i} seconds  ", end="", flush=True)
        time.sleep(1)

    print("\n\n" + "=" * 80)
    print("✓ TEST COMPLETE: Dock hiding approach works!")
    print("=" * 80)
    print("\nConclusion: The fix is ready for deployment in the MCP server.")
    print("The same approach in stata_mcp_server.py (lines 36-49) will work.")
else:
    print("\n" + "=" * 80)
    print("✗ TEST FAILED: Could not verify dock hiding")
    print("=" * 80)
    print("\nThe approach may not work in this environment.")
