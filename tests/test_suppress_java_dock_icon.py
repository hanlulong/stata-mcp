#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test: Suppress Java/Stata Dock Icon During PNG Initialization

The dock icon appears when Stata's embedded JVM initializes for graphics.
We need to set java.awt.headless=true or similar BEFORE the JVM starts.
"""

import sys
import os
import tempfile
import platform

STATA_PATH = '/Applications/StataNow/utilities'
sys.path.insert(0, STATA_PATH)

print("=" * 80)
print("SUPPRESSING JAVA DOCK ICON TEST")
print("=" * 80)

if platform.system() != 'Darwin':
    print("\nThis test is Mac-specific - skipping")
    sys.exit(0)

print("\nStrategy: Set Java system properties BEFORE PyStata initialization")
print("This should prevent the JVM from creating a Dock icon")

# CRITICAL: Set Java headless mode BEFORE any Stata/Java initialization
print("\n1. Setting Java headless environment variable...")
os.environ['JAVA_TOOL_OPTIONS'] = '-Djava.awt.headless=true'
print(f"   ✓ Set JAVA_TOOL_OPTIONS={os.environ['JAVA_TOOL_OPTIONS']}")

# Also try AWT_TOOLKIT for good measure
os.environ['AWT_TOOLKIT'] = 'MToolkit'
print(f"   ✓ Set AWT_TOOLKIT={os.environ['AWT_TOOLKIT']}")

print("\n2. Initializing PyStata...")
from pystata import config
config.init('mp')
from pystata import stata
from pystata.config import stlib, get_encode_str

print("   ✓ PyStata initialized")

print("\n3. Enabling _gr_list...")
stlib.StataSO_Execute(get_encode_str("qui _gr_list on"), False)
print("   ✓ _gr_list enabled")

print("\n4. PNG INITIALIZATION (the critical moment)...")
print("   This is when the JVM starts and normally creates a Dock icon")
print("   With headless mode, NO icon should appear")

try:
    # Create minimal dataset and graph
    stlib.StataSO_Execute(get_encode_str("qui clear"), False)
    stlib.StataSO_Execute(get_encode_str("qui set obs 2"), False)
    stlib.StataSO_Execute(get_encode_str("qui gen x=1"), False)
    stlib.StataSO_Execute(get_encode_str("qui twoway scatter x x, name(_init, replace)"), False)

    # Export to PNG - this triggers JVM/graphics initialization
    png_init = os.path.join(tempfile.gettempdir(), "_stata_png_init_headless.png")
    print(f"\n   Exporting PNG to: {png_init}")
    print("   Watch your Dock - if headless works, NO icon should appear!")

    stlib.StataSO_Execute(get_encode_str(f'qui graph export "{png_init}", name(_init) replace width(10) height(10)'), False)
    stlib.StataSO_Execute(get_encode_str("qui graph drop _init"), False)

    # Cleanup
    if os.path.exists(png_init):
        os.unlink(png_init)

    print("\n   ✓ PNG export completed successfully")
    print("\n" + "=" * 80)
    print("✓ SUCCESS: PNG initialization completed")
    print("=" * 80)
    print("\nDid a Java/Python/Stata icon appear in your Dock? (yes/no)")
    print("If NO: Headless mode works! This is the solution.")
    print("If YES: Headless mode doesn't prevent Dock icon.")

except Exception as e:
    print(f"\n   ✗ PNG initialization failed: {e}")
    import traceback
    traceback.print_exc()
    print("\n" + "=" * 80)
    print("✗ FAILED: Could not complete PNG initialization")
    print("=" * 80)

print("\nAlternative approaches if headless doesn't work:")
print("1. Use NSApplication.setActivationPolicy before PyStata init")
print("2. Set LSUIElement=1 in Python's Info.plist")
print("3. Run Stata commands without graphics (use SVG or PDF instead)")
