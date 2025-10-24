#!/usr/bin/env python3
"""
Test script to verify streaming functionality via HTTP SSE endpoint
This bypasses MCP and directly tests the server's streaming capability
"""

import json
import time
from datetime import datetime
from pathlib import Path

import requests

# Configuration
SERVER_URL = "http://localhost:4000"
TEST_FILE = Path(__file__).resolve().parent / "test_streaming.do"
TIMEOUT = 600

def test_streaming():
    """Test the SSE streaming endpoint"""
    print("=" * 80)
    print("STATA MCP STREAMING TEST")
    print("=" * 80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Test file: {TEST_FILE}")
    print(f"Timeout: {TIMEOUT} seconds")
    print("=" * 80)
    print()

    # First check if server is alive
    try:
        health = requests.get(f"{SERVER_URL}/health", timeout=5)
        print(f"✅ Server health check: {health.json()}")
        print()
    except Exception as e:
        print(f"❌ Server health check failed: {e}")
        return

    # Test the streaming endpoint
    url = f"{SERVER_URL}/run_file/stream"
    params = {"file_path": str(TEST_FILE), "timeout": TIMEOUT}

    print(f"📡 Connecting to streaming endpoint: {url}")
    print(f"📝 Parameters: {params}")
    print()
    print("-" * 80)
    print("STREAMING OUTPUT:")
    print("-" * 80)

    start_time = time.time()
    last_message_time = start_time
    message_count = 0

    try:
        # Make streaming request
        with requests.get(url, params=params, stream=True, timeout=TIMEOUT) as response:
            print(f"✅ Connected! Status: {response.status_code}")
            print(f"   Headers: {dict(response.headers)}")
            print()

            # Process SSE stream
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    current_time = time.time()
                    elapsed = current_time - start_time
                    since_last = current_time - last_message_time

                    # Print timestamp and message
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    print(f"[{timestamp}] +{elapsed:.1f}s (Δ{since_last:.1f}s): {line}")

                    message_count += 1
                    last_message_time = current_time

                    # Parse SSE events
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[5:].strip())
                            if "status" in data:
                                print(f"   📊 Status: {data['status']}")
                            if "result" in data:
                                print(f"   📄 Result received (length: {len(str(data['result']))} chars)")
                        except json.JSONDecodeError:
                            pass

    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print()
        print(f"⏱️  TIMEOUT after {elapsed:.1f} seconds")
        print(f"   Received {message_count} messages before timeout")
        return False

    except Exception as e:
        elapsed = time.time() - start_time
        print()
        print(f"❌ ERROR after {elapsed:.1f} seconds: {e}")
        print(f"   Received {message_count} messages before error")
        import traceback
        traceback.print_exc()
        return False

    # Summary
    elapsed = time.time() - start_time
    print()
    print("-" * 80)
    print("SUMMARY:")
    print("-" * 80)
    print(f"✅ Test completed successfully!")
    print(f"   Total time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print(f"   Messages received: {message_count}")
    print(f"   Average message interval: {elapsed/message_count if message_count > 0 else 0:.1f}s")
    print("=" * 80)

    return True

if __name__ == "__main__":
    success = test_streaming()
    exit(0 if success else 1)
