"""v201: `python -m swingbot.refresher` -- the refresher compose service's entry point."""
import logging
import signal
import threading

from swingbot import config
from swingbot.refresher import loop, snapshot_job


def main() -> int:
    logging.basicConfig(level=getattr(logging, str(config.LOG_LEVEL).upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, lambda *_: config.reload())
    job = snapshot_job.worker()  # refresher process only, never the admin or bot containers
    job.start()
    try:
        loop.run_forever(stop)
    finally:
        job.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
