#!/usr/bin/env python3
"""
Simple test to check if MCP server responds properly
"""

import json
from pathlib import Path

import requests

TEST_DIR = Path(__file__).resolve().parent
TEST_FILE = TEST_DIR / "test_streaming.do"

# Test 1: Health check
print("Test 1: Health Check")
resp = requests.get('http://localhost:4000/health')
print(f"  Status: {resp.status_code}")
print(f"  Response: {resp.json()}")

# Test 2: Direct HTTP call to run_file
print("\nTest 2: Direct HTTP /run_file endpoint")
resp = requests.get(
    'http://localhost:4000/run_file',
    params={
        'file_path': str(TEST_FILE),
        'timeout': 600
    },
    timeout=30
)
print(f"  Status: {resp.status_code}")
print(f"  Response (first 200 chars): {resp.text[:200]}")

# Test 3: Check if tool is in OpenAPI
print("\nTest 3: Check OpenAPI for stata_run_file")
resp = requests.get('http://localhost:4000/openapi.json')
openapi = resp.json()
operations = []
for path, methods in openapi.get('paths', {}).items():
    for method, details in methods.items():
        op_id = details.get('operationId', '')
        if 'stata' in op_id.lower():
            operations.append(f"{method.upper()} {path} -> {op_id}")

print(f"  Found {len(operations)} Stata operations:")
for op in operations:
    print(f"    - {op}")

print("\nAll tests completed!")
