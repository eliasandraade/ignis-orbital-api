"""Run the demo seed.

    python -m seed              # fails (exit 1) when the environment forbids it
    python -m seed --if-allowed # used by the container entrypoint: skips quietly
"""

import asyncio
import sys

from seed.seed_all import DemoSeedRefusedError, ensure_seed_allowed, run_all

if __name__ == "__main__":
    if "--if-allowed" in sys.argv[1:]:
        try:
            ensure_seed_allowed()
        except DemoSeedRefusedError as exc:
            print(f"==> Seed demonstrativo ignorado: {exc}")
            sys.exit(0)
    asyncio.run(run_all())
