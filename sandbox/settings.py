"""Configuration from sandbox/.env. No secrets in code (R14)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    jev_api_key: str
    jev_model: str
    nemotron_api_key: str
    fast_url: str
    deep_url: str
    fast_model: str
    deep_model: str

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(ROOT / ".env")
        missing = [k for k in ("TYPESAFE_API_KEY", "NEMOTRON_API_KEY") if not os.environ.get(k, "").strip()]
        if missing:
            raise SystemExit(f"Missing in sandbox/.env: {', '.join(missing)}")
        return cls(
            jev_api_key=os.environ["TYPESAFE_API_KEY"].strip(),
            jev_model=os.environ.get("JEV_MODEL", "jev-latest"),
            nemotron_api_key=os.environ["NEMOTRON_API_KEY"].strip(),
            fast_url=os.environ.get("NEMOTRON_FAST_URL", "http://localhost:8000/v1"),
            deep_url=os.environ.get("NEMOTRON_DEEP_URL", "http://localhost:8001/v1"),
            fast_model=os.environ.get("NEMOTRON_FAST_MODEL", "nemotron-fast"),
            deep_model=os.environ.get("NEMOTRON_DEEP_MODEL", "nemotron-deep"),
        )
