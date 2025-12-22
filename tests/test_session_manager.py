#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Session Manager - Multi-session Stata support

These tests verify:
1. Session creation and destruction
2. Session state management
3. Parallel execution isolation
4. Session timeout and cleanup
5. Worker health monitoring
6. Backward compatibility (default session)

Run with: python tests/test_session_manager.py
"""

import os
import sys
import time
import queue
import unittest
import threading
import multiprocessing

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from session_manager import (
    SessionManager,
    SessionState,
    Session,
    init_session_manager,
    get_session_manager
)
from stata_worker import WorkerState, CommandType


# Configuration for tests
STATA_PATH = os.environ.get('STATA_PATH', '/Applications/StataNow')
STATA_EDITION = os.environ.get('STATA_EDITION', 'mp')
SKIP_STATA_TESTS = os.environ.get('SKIP_STATA_TESTS', 'false').lower() == 'true'


def skip_if_no_stata(func):
    """Decorator to skip tests if Stata is not available"""
    def wrapper(*args, **kwargs):
        if SKIP_STATA_TESTS:
            print(f"Skipping {func.__name__}: SKIP_STATA_TESTS=true")
            return
        if not os.path.exists(STATA_PATH):
            print(f"Skipping {func.__name__}: Stata not found at {STATA_PATH}")
            return
        return func(*args, **kwargs)
    return wrapper


class TestSessionState(unittest.TestCase):
    """Test session state management"""

    def test_session_states_exist(self):
        """Verify all session states are defined"""
        self.assertIsNotNone(SessionState.CREATING)
        self.assertIsNotNone(SessionState.READY)
        self.assertIsNotNone(SessionState.BUSY)
        self.assertIsNotNone(SessionState.ERROR)
        self.assertIsNotNone(SessionState.DESTROYING)
        self.assertIsNotNone(SessionState.DESTROYED)

    def test_session_to_dict(self):
        """Test session serialization"""
        session = Session(
            session_id="test123",
            state=SessionState.READY,
            is_default=False
        )
        d = session.to_dict()

        self.assertEqual(d['session_id'], 'test123')
        self.assertEqual(d['state'], 'ready')
        self.assertFalse(d['is_busy'])
        self.assertFalse(d['is_default'])
        self.assertIsNotNone(d['created_at'])
        self.assertIsNotNone(d['last_activity'])


class TestSessionManagerConfiguration(unittest.TestCase):
    """Test session manager configuration"""

    def test_default_configuration(self):
        """Test default configuration values"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            enabled=False  # Don't actually start workers
        )

        self.assertEqual(manager.max_sessions, 100)
        self.assertEqual(manager.session_timeout, 3600)
        self.assertEqual(manager.worker_start_timeout, 60)
        self.assertEqual(manager.command_timeout, 600)

    def test_custom_configuration(self):
        """Test custom configuration"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            max_sessions=8,
            session_timeout=1800,
            worker_start_timeout=30,
            command_timeout=300,
            enabled=False
        )

        self.assertEqual(manager.max_sessions, 8)
        self.assertEqual(manager.session_timeout, 1800)
        self.assertEqual(manager.worker_start_timeout, 30)
        self.assertEqual(manager.command_timeout, 300)

    def test_disabled_mode(self):
        """Test disabled multi-session mode"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            enabled=False
        )

        self.assertFalse(manager.enabled)
        # Should return True without creating workers
        self.assertTrue(manager.start())
        manager.stop()


class TestSessionManagerLifecycle(unittest.TestCase):
    """Test session manager lifecycle with real workers"""

    @skip_if_no_stata
    def test_start_creates_default_session(self):
        """Test that starting creates a default session"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            enabled=True
        )

        try:
            success = manager.start()
            self.assertTrue(success)

            # Default session should exist
            default_session = manager.get_session()
            self.assertIsNotNone(default_session)
            self.assertTrue(default_session.is_default)
            self.assertEqual(default_session.session_id, "default")
            self.assertEqual(default_session.state, SessionState.READY)

        finally:
            manager.stop()

    @skip_if_no_stata
    def test_create_and_destroy_session(self):
        """Test session creation and destruction"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            max_sessions=4,
            enabled=True
        )

        try:
            manager.start()

            # Create new session
            success, session_id, error = manager.create_session()
            self.assertTrue(success)
            self.assertNotEqual(session_id, "")
            self.assertEqual(error, "")

            # Session should exist
            session = manager.get_session(session_id)
            self.assertIsNotNone(session)
            self.assertEqual(session.state, SessionState.READY)
            self.assertFalse(session.is_default)

            # Destroy session
            success, error = manager.destroy_session(session_id)
            self.assertTrue(success)

            # Session should be gone
            session = manager.get_session(session_id)
            self.assertIsNone(session)

        finally:
            manager.stop()

    @skip_if_no_stata
    def test_session_limit_enforcement(self):
        """Test that session limit is enforced"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            max_sessions=2,  # Only 2 sessions (including default)
            enabled=True
        )

        try:
            manager.start()

            # Create one additional session (2 total with default)
            success, session_id, error = manager.create_session()
            self.assertTrue(success)

            # Try to create another - should fail
            success, _, error = manager.create_session()
            self.assertFalse(success)
            self.assertIn("Maximum sessions", error)

            # Destroy one session
            manager.destroy_session(session_id)

            # Now creation should succeed
            success, _, _ = manager.create_session()
            self.assertTrue(success)

        finally:
            manager.stop()

    @skip_if_no_stata
    def test_cannot_destroy_default_session(self):
        """Test that default session cannot be destroyed without force"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            enabled=True
        )

        try:
            manager.start()

            # Try to destroy default session
            success, error = manager.destroy_session("default")
            self.assertFalse(success)
            self.assertIn("Cannot destroy default", error)

            # With force=True it should work
            success, error = manager.destroy_session("default", force=True)
            self.assertTrue(success)

        finally:
            manager.stop()


class TestSessionExecution(unittest.TestCase):
    """Test command execution in sessions"""

    @skip_if_no_stata
    def test_execute_on_default_session(self):
        """Test execution on default session"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            enabled=True
        )

        try:
            manager.start()

            # Execute simple command
            result = manager.execute('display "Hello World"')

            self.assertEqual(result['status'], 'success')
            self.assertIn('Hello World', result['output'])
            self.assertEqual(result['error'], '')

        finally:
            manager.stop()

    @skip_if_no_stata
    def test_execute_on_specific_session(self):
        """Test execution on a specific session"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            enabled=True
        )

        try:
            manager.start()

            # Create new session
            success, session_id, _ = manager.create_session()
            self.assertTrue(success)

            # Execute on new session
            result = manager.execute('display "Session specific"', session_id=session_id)

            self.assertEqual(result['status'], 'success')
            self.assertIn('Session specific', result['output'])
            self.assertEqual(result['session_id'], session_id)

        finally:
            manager.stop()

    @skip_if_no_stata
    def test_session_isolation(self):
        """Test that sessions have isolated state"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            max_sessions=3,
            enabled=True
        )

        try:
            manager.start()

            # Create second session
            success, session_id, _ = manager.create_session()
            self.assertTrue(success)

            # Load different data in each session
            # Default session: 5 observations
            manager.execute('clear\nset obs 5\ngen x = _n')
            # New session: 3 observations
            manager.execute('clear\nset obs 3\ngen y = _n * 10', session_id=session_id)

            # Verify isolation - count observations
            result_default = manager.execute('count')
            result_new = manager.execute('count', session_id=session_id)

            # Default should have 5 obs
            self.assertIn('5', result_default['output'])
            # New session should have 3 obs
            self.assertIn('3', result_new['output'])

        finally:
            manager.stop()


class TestParallelExecution(unittest.TestCase):
    """Test parallel execution across sessions"""

    @skip_if_no_stata
    def test_parallel_execution_timing(self):
        """Test that parallel execution is actually parallel"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            max_sessions=3,
            enabled=True
        )

        try:
            manager.start()

            # Create second session
            success, session2_id, _ = manager.create_session()
            self.assertTrue(success)

            results = {}
            errors = []

            def run_in_session(session_id, name):
                try:
                    # Sleep for 2 seconds
                    result = manager.execute(
                        'sleep 2000\ndisplay "Done"',
                        session_id=session_id
                    )
                    results[name] = result
                except Exception as e:
                    errors.append(str(e))

            # Start both executions in parallel
            start_time = time.time()

            t1 = threading.Thread(target=run_in_session, args=(None, "default"))
            t2 = threading.Thread(target=run_in_session, args=(session2_id, "session2"))

            t1.start()
            t2.start()

            t1.join(timeout=30)
            t2.join(timeout=30)

            elapsed = time.time() - start_time

            # Both should complete successfully
            self.assertEqual(len(errors), 0, f"Errors: {errors}")
            self.assertIn('default', results)
            self.assertIn('session2', results)

            # Should take ~2 seconds (parallel), not ~4 seconds (serial)
            self.assertLess(elapsed, 4.0, "Parallel execution took too long")
            print(f"Parallel execution took {elapsed:.1f} seconds (expected ~2s)")

        finally:
            manager.stop()


class TestSessionCleanup(unittest.TestCase):
    """Test session cleanup and health monitoring"""

    @skip_if_no_stata
    def test_list_sessions(self):
        """Test listing active sessions"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            max_sessions=3,
            enabled=True
        )

        try:
            manager.start()

            # Initially just default session
            sessions = manager.list_sessions()
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]['session_id'], 'default')

            # Create another session
            success, session_id, _ = manager.create_session()
            self.assertTrue(success)

            sessions = manager.list_sessions()
            self.assertEqual(len(sessions), 2)

            session_ids = [s['session_id'] for s in sessions]
            self.assertIn('default', session_ids)
            self.assertIn(session_id, session_ids)

        finally:
            manager.stop()

    @skip_if_no_stata
    def test_get_stats(self):
        """Test getting manager statistics"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            max_sessions=4,
            enabled=True
        )

        try:
            manager.start()

            stats = manager.get_stats()

            self.assertTrue(stats['enabled'])
            self.assertEqual(stats['total_sessions'], 1)
            self.assertEqual(stats['active_sessions'], 1)
            self.assertEqual(stats['busy_sessions'], 0)
            self.assertEqual(stats['max_sessions'], 4)
            self.assertEqual(stats['available_slots'], 3)

        finally:
            manager.stop()

    @skip_if_no_stata
    def test_available_slots(self):
        """Test available slots tracking"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            max_sessions=3,
            enabled=True
        )

        try:
            manager.start()

            # Initially 2 slots available (default takes 1)
            self.assertEqual(manager.available_slots, 2)

            # Create a session
            success, session_id, _ = manager.create_session()
            self.assertTrue(success)
            self.assertEqual(manager.available_slots, 1)

            # Destroy it
            manager.destroy_session(session_id)
            self.assertEqual(manager.available_slots, 2)

        finally:
            manager.stop()


class TestErrorHandling(unittest.TestCase):
    """Test error handling"""

    def test_execute_on_nonexistent_session(self):
        """Test executing on non-existent session"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            enabled=False  # Don't start workers
        )

        result = manager.execute('display "test"', session_id="nonexistent")

        self.assertEqual(result['status'], 'error')
        self.assertIn('not found', result['error'])

    def test_destroy_nonexistent_session(self):
        """Test destroying non-existent session"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            enabled=False
        )

        success, error = manager.destroy_session("nonexistent")

        self.assertFalse(success)
        self.assertIn('not found', error)


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with single-session mode"""

    @skip_if_no_stata
    def test_none_session_id_uses_default(self):
        """Test that None session_id uses default session"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            enabled=True
        )

        try:
            manager.start()

            # Execute without session_id
            result = manager.execute('display "Using default"')

            self.assertEqual(result['status'], 'success')
            self.assertIn('Using default', result['output'])

        finally:
            manager.stop()

    @skip_if_no_stata
    def test_get_session_without_id(self):
        """Test getting session without ID returns default"""
        manager = SessionManager(
            stata_path=STATA_PATH,
            stata_edition=STATA_EDITION,
            enabled=True
        )

        try:
            manager.start()

            session = manager.get_session()  # No session_id
            self.assertIsNotNone(session)
            self.assertTrue(session.is_default)
            self.assertEqual(session.session_id, "default")

        finally:
            manager.stop()


def run_tests():
    """Run all tests"""
    # Set multiprocessing start method
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestSessionState))
    suite.addTests(loader.loadTestsFromTestCase(TestSessionManagerConfiguration))
    suite.addTests(loader.loadTestsFromTestCase(TestSessionManagerLifecycle))
    suite.addTests(loader.loadTestsFromTestCase(TestSessionExecution))
    suite.addTests(loader.loadTestsFromTestCase(TestParallelExecution))
    suite.addTests(loader.loadTestsFromTestCase(TestSessionCleanup))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandling))
    suite.addTests(loader.loadTestsFromTestCase(TestBackwardCompatibility))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    print(f"Using Stata path: {STATA_PATH}")
    print(f"Using Stata edition: {STATA_EDITION}")
    print(f"Skip Stata tests: {SKIP_STATA_TESTS}")
    print()

    success = run_tests()
    sys.exit(0 if success else 1)
