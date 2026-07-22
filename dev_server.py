from __future__ import annotations

import asyncio
import os
import signal

from temporalio.testing import WorkflowEnvironment


async def main() -> None:
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    env = await WorkflowEnvironment.start_local(
        ip="0.0.0.0",
        port=7233,
        namespace=namespace,
        ui=True,
        ui_port=8233,
    )
    print("Temporal dev server running on 0.0.0.0:7233 (UI on 8233)")
    print("Press Ctrl+C to stop")

    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    print("\nShutting down...")
    await env.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
