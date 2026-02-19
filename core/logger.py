import logging
import json
import os
from datetime import datetime

logger = logging.getLogger("opsguard")
logger.setLevel(logging.INFO)

artifacts_dir = os.path.join(os.getcwd(), "artifacts")
internal_dir = os.path.join(artifacts_dir, "internal")
os.makedirs(internal_dir, exist_ok=True)

file_handler = logging.FileHandler(
    os.path.join(internal_dir, "run.log"),
    encoding="utf-8",
)
file_handler.setLevel(logging.INFO)

formatter = logging.Formatter('%(message)s')
file_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(file_handler)

if os.getenv("OPSGUARD_VERBOSE") == "1":
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)


def log_event(node: str, message: str, data: dict = None):
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "node": node,
        "message": message,
        "data": data or {}
    }
    logger.info(json.dumps(payload))
