import logging
import sys

logger = logging.getLogger("railmind")
logger.setLevel(logging.INFO)

# Uvicorn / FastAPI CLI often leave non-uvicorn loggers without handlers, so INFO is dropped.
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setLevel(logging.INFO)
    _handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(_handler)

logger.propagate = False
