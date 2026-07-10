"""Entry point for ``python -m agent``."""

import asyncio

from agent.agent import main

asyncio.run(main())
