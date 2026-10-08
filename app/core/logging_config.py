"""Small logging setup shared by the API and processing services."""

import logging


def configure_logging(level: str) -> None:
    """Configure consistent application logging without logging user payloads."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
