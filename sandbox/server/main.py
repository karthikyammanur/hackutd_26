"""Entry point: `uvicorn main:app --host 127.0.0.1 --port 8765`. Configuration comes from the environment."""

import logging

from service import Service, Settings, build_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

app = build_app(Service(Settings.from_env()))
