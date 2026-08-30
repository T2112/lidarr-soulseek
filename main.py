from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from config_loader import load_config
from worker import Worker


def setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


async def amain(config_path: Path) -> None:
    cfg = load_config(config_path)
    setup_logging(cfg.log_file)
    worker = Worker(cfg)
    try:
        await worker.run_forever()
    finally:
        worker.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Lidarr missing albums from Soulseek")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("config.toml")),
        help="Path to config.toml",
    )
    args = parser.parse_args()
    asyncio.run(amain(Path(args.config)))


if __name__ == "__main__":
    main()
