import logging
import json
from datetime import datetime

logger = logging.getLogger("opsguard")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setLevel(logging.INFO)

formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)

logger.addHandler(handler)


def log_event(node: str, message: str, data: dict = None):
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "node": node,
        "message": message,
        "data": data or {}
    }
    logger.info(json.dumps(payload))
