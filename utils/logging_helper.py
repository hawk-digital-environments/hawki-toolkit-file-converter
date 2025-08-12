import logging
import os
from pathlib import Path

def logging_help(log_path: str | os.PathLike = "conversion.log") -> logging.Logger:
    """
    Set up and return a logger named 'converter' that logs to both:
      1. A file which can be specified in log path
      2. Standard output in console

    This logger is process-safe for FastAPI/Uvicorn reloads and avoids duplicate handlers.
    """

    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    # creates a logger named "converter"
    logger = logging.getLogger("converter")
    logger.setLevel(logging.INFO)
    # without this, each reload would add a new file/stream handler, causing repeated log lines
    if not logger.handlers:
        # Create a FileHandler to log to the specified file in append mode with UTF-8 encoding
        fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        sh = logging.StreamHandler()
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        fh.setFormatter(fmt)
        sh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(sh)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    return logger
