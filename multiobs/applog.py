"""Petit journal de Multi OBS (data/multiobs.log) : événements rares, utiles pour comprendre un souci."""
from datetime import datetime

from . import paths

MAX_BYTES = 200_000   # au-delà, on ne garde que les dernières lignes


def log(message: str) -> None:
    try:
        path = paths.DATA / "multiobs.log"
        if path.exists() and path.stat().st_size > MAX_BYTES:
            lines = path.read_text("utf-8", errors="replace").splitlines()[-500:]
            path.write_text("\n".join(lines) + "\n", "utf-8")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}\n")
    except OSError:
        pass
