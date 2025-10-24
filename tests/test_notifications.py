#!/usr/bin/env python3
"""
Test MCP HTTP transport notifications using Python SDK.

This script tests that notifications are properly routed through the HTTP transport
when using the /mcp-streamable endpoint.
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    logger.info("✓ MCP SDK imported successfully")
except ImportError as e:
    logger.error(f"Failed to import MCP SDK: {e}")
    logger.error("Install with: pip install mcp")
    sys.exit(1)


class NotificationMonitor:
    """Monitor and display MCP notifications."""

    def __init__(self):
        self.notifications = []
        self.log_messages = []
        self.progress_updates = []

    def handle_notification(self, notification):
        """Handle incoming notifications."""
        self.notifications.append(notification)

        # Parse notification type
        method = getattr(notification, 'method', None)
        params = getattr(notification, 'params', None)

        if method == 'notifications/message':
            # Log message notification
            level = params.get('level', 'info') if params else 'info'
            data = params.get('data', '') if params else ''
            logger.info(f"📢 Notification [{level}]: {data}")
            self.log_messages.append({'level': level, 'data': data, 'time': time.time()})

        elif method == 'notifications/progress':
            # Progress notification
            progress = params.get('progress', 0) if params else 0
            total = params.get('total', 0) if params else 0
            message = params.get('message', '') if params else ''
            logger.info(f"⏳ Progress: {progress}/{total} - {message}")
            self.progress_updates.append({'progress': progress, 'total': total, 'message': message, 'time': time.time()})

        else:
            logger.info(f"📨 Other notification: {method}")

    def summary(self):
        """Print summary of received notifications."""
        logger.info("\n" + "=" * 80)
        logger.info("NOTIFICATION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total notifications: {len(self.notifications)}")
        logger.info(f"Log messages: {len(self.log_messages)}")
        logger.info(f"Progress updates: {len(self.progress_updates)}")

        if self.log_messages:
            logger.info("\nLog messages received:")
            for i, msg in enumerate(self.log_messages, 1):
                logger.info(f"  {i}. [{msg['level']}] {msg['data']}")

        if self.progress_updates:
            logger.info("\nProgress updates received:")
            for i, update in enumerate(self.progress_updates, 1):
                logger.info(f"  {i}. {update['progress']}/{update['total']} - {update['message']}")

        logger.info("=" * 80)


DEFAULT_TEST_FILE = Path(__file__).resolve().parent / "test_timeout.do"


async def test_notifications(
    url: str = "http://localhost:4000/mcp-streamable",
    test_file: str | Path | None = None,
) -> bool:
    """Test notifications through HTTP transport."""

    logger.info("=" * 80)
    logger.info("MCP HTTP Transport Notification Test")
    logger.info("=" * 80)
    if test_file is None:
        test_file = DEFAULT_TEST_FILE
    else:
        test_file = Path(test_file)

    logger.info(f"Endpoint: {url}")
    logger.info(f"Test file: {test_file}")
    logger.info("=" * 80)

    # Verify test file exists
    if not test_file.exists():
        logger.error(f"Test file not found: {test_file}")
        return False

    monitor = NotificationMonitor()

    try:
        # Connect to server
        logger.info("\n[1/4] Connecting to MCP server...")
        start_time = time.time()

        async with streamablehttp_client(url) as (read_stream, write_stream, session_info):
            connect_time = time.time() - start_time
            logger.info(f"✓ Connected in {connect_time:.2f}s")

            # Initialize session
            logger.info("\n[2/4] Initializing session...")
            start_time = time.time()

            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                init_time = time.time() - start_time
                logger.info(f"✓ Session initialized in {init_time:.2f}s")

                # Set up notification handler
                # Note: The SDK handles notifications internally through the session
                # We'll monitor them by checking the session's internal state

                # Discover tools
                logger.info("\n[3/4] Discovering tools...")
                tools_result = await session.list_tools()
                logger.info(f"✓ Discovered {len(tools_result.tools)} tools")
                for tool in tools_result.tools:
                    logger.info(f"  - {tool.name}")

                # Execute stata_run_file
                logger.info("\n[4/4] Executing stata_run_file...")
                logger.info(f"  File: {test_file}")
                logger.info(f"  This will run for ~70 seconds (70 iterations @ 1s each)")
                logger.info(f"  Watch for real-time notifications below:")
                logger.info("-" * 80)

                start_time = time.time()

                # Call the tool - notifications should arrive during execution
                result = await session.call_tool(
                    "stata_run_file",
                    arguments={
                        "file_path": str(test_file),
                        "timeout": 600
                    }
                )

                exec_time = time.time() - start_time
                logger.info("-" * 80)
                logger.info(f"✓ Execution completed in {exec_time:.2f}s")

                # Display result
                logger.info("\nExecution Result:")
                for i, content in enumerate(result.content, 1):
                    if hasattr(content, 'text'):
                        text = content.text
                        # Show first and last 500 chars
                        if len(text) > 1000:
                            logger.info(f"  Output (truncated):\n{text[:500]}\n...\n{text[-500:]}")
                        else:
                            logger.info(f"  Output:\n{text}")

                if result.isError:
                    logger.error("  ✗ Tool reported an error!")
                    return False

                # Display notification summary
                monitor.summary()

                # Check if we received notifications
                logger.info("\n" + "=" * 80)
                if monitor.notifications or monitor.log_messages:
                    logger.info("✅ SUCCESS: Notifications were received through HTTP transport!")
                    return True
                else:
                    logger.warning("⚠️  WARNING: No notifications received during execution")
                    logger.warning("   This suggests notifications are not reaching the HTTP transport")
                    return False

    except Exception as e:
        logger.error(f"\n✗ Test failed: {e}", exc_info=True)
        return False


async def main():
    """Main test runner."""
    import argparse

    parser = argparse.ArgumentParser(description="Test MCP HTTP notifications")
    parser.add_argument(
        "--url",
        default="http://localhost:4000/mcp-streamable",
        help="MCP server URL"
    )
    parser.add_argument(
        "--test-file",
        default=str(DEFAULT_TEST_FILE),
        help="Path to test .do file"
    )

    args = parser.parse_args()

    success = await test_notifications(args.url, args.test_file)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
