#!/usr/bin/env python3
"""
Test multiprocessing with PyStata - each worker gets its own Stata instance
"""

import multiprocessing
import sys
import os
import time
import queue

def worker_process(worker_id, command_queue, result_queue, stata_path):
    """Worker process that initializes its own PyStata instance"""
    try:
        # Add Stata utilities path - must be done before importing pystata
        utilities_path = os.path.join(stata_path, "utilities", "pystata")
        sys.path.insert(0, utilities_path)

        # Also add the utilities parent path
        utilities_parent = os.path.join(stata_path, "utilities")
        sys.path.insert(0, utilities_parent)

        # Set Java headless mode (for Mac)
        os.environ['_JAVA_OPTIONS'] = '-Djava.awt.headless=true'

        # Initialize PyStata (each process gets its own instance)
        from pystata import config
        config.init("mp")
        from pystata import stata

        result_queue.put({"status": "ready", "worker_id": worker_id})

        while True:
            try:
                cmd = command_queue.get(timeout=1)
            except queue.Empty:
                continue

            if cmd == "EXIT":
                result_queue.put({"status": "exiting", "worker_id": worker_id})
                break

            try:
                # Execute command
                stata.run(cmd, echo=True)
                result_queue.put({"status": "success", "worker_id": worker_id, "command": cmd[:50]})
            except Exception as e:
                result_queue.put({"status": "error", "worker_id": worker_id, "error": str(e)})

    except Exception as e:
        result_queue.put({"status": "init_error", "worker_id": worker_id, "error": str(e)})


def main():
    # Use spawn method for clean process isolation (required for PyStata)
    multiprocessing.set_start_method('spawn', force=True)

    stata_path = "/Applications/StataNow"

    # Create queues for IPC
    cmd_queue1 = multiprocessing.Queue()
    result_queue1 = multiprocessing.Queue()
    cmd_queue2 = multiprocessing.Queue()
    result_queue2 = multiprocessing.Queue()

    # Start two worker processes
    print("Starting worker 1...")
    p1 = multiprocessing.Process(target=worker_process, args=(1, cmd_queue1, result_queue1, stata_path))
    p1.start()

    print("Starting worker 2...")
    p2 = multiprocessing.Process(target=worker_process, args=(2, cmd_queue2, result_queue2, stata_path))
    p2.start()

    # Wait for workers to initialize
    print("Waiting for workers to initialize...")
    try:
        r1 = result_queue1.get(timeout=60)
        print(f"Worker 1: {r1}")
        r2 = result_queue2.get(timeout=60)
        print(f"Worker 2: {r2}")
    except queue.Empty:
        print("Timeout waiting for workers!")
        p1.terminate()
        p2.terminate()
        return

    # Test 1: Different data in each worker
    print("\n=== Test 1: Different data in each worker ===")
    cmd_queue1.put('clear\nset obs 5\ngen x = _n')
    cmd_queue2.put('clear\nset obs 3\ngen y = _n * 10')

    time.sleep(2)

    # Get results
    try:
        print(f"Worker 1 result: {result_queue1.get(timeout=5)}")
        print(f"Worker 2 result: {result_queue2.get(timeout=5)}")
    except queue.Empty:
        print("Timeout getting results")

    # Test 2: List data (verify isolation)
    print("\n=== Test 2: List data (verify isolation) ===")
    cmd_queue1.put('list')
    cmd_queue2.put('list')

    time.sleep(2)

    try:
        print(f"Worker 1 list: {result_queue1.get(timeout=5)}")
        print(f"Worker 2 list: {result_queue2.get(timeout=5)}")
    except queue.Empty:
        print("Timeout")

    # Test 3: Parallel execution
    print("\n=== Test 3: Parallel execution ===")
    start = time.time()
    cmd_queue1.put('sleep 2000\ndisplay "Worker 1 done"')
    cmd_queue2.put('sleep 2000\ndisplay "Worker 2 done"')

    try:
        r1 = result_queue1.get(timeout=10)
        r2 = result_queue2.get(timeout=10)
        elapsed = time.time() - start
        print(f"Both workers completed in {elapsed:.1f} seconds")
        print(f"  (Should be ~2 seconds if parallel, ~4 seconds if serial)")
    except queue.Empty:
        print("Timeout")

    # Cleanup
    print("\n=== Cleanup ===")
    cmd_queue1.put("EXIT")
    cmd_queue2.put("EXIT")

    p1.join(timeout=5)
    p2.join(timeout=5)

    if p1.is_alive():
        p1.terminate()
    if p2.is_alive():
        p2.terminate()

    print("Done!")


if __name__ == "__main__":
    main()
