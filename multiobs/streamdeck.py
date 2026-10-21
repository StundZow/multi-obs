"""Plugin Stream Deck livré avec Multi OBS : version installée et installation en un clic.

Un fichier .streamDeckPlugin est un zip du dossier du plugin ; ouvert, il est installé (ou mis à
jour) par le logiciel Stream Deck, qui demande confirmation. Pas besoin du Marketplace.
"""
import json
import os
import tempfile
import zipfile
from pathlib import Path

from . import paths

PLUGIN_UUID = "com.stundzow.multiobs"
FOLDER = f"{PLUGIN_UUID}.sdPlugin"
INSTALLED = Path(os.environ.get("APPDATA", "")) / "Elgato" / "StreamDeck" / "Plugins" / FOLDER


def source() -> Path:
    return paths.STREAMDECK / FOLDER


def _version(folder: Path) -> str:
    """Version complète du plugin, ex. « 1.0.8.1 » (le 4e chiffre : un plugin corrigé sans nouvelle
    version de Multi OBS)."""
    try:
        return json.loads((folder / "manifest.json").read_text("utf-8")).get("Version", "")
    except (OSError, ValueError):
        return ""


def short(version: str) -> str:
    """« 1.0.8.1 » → « 1.0.8 », pour l'affichage."""
    return ".".join(version.split(".")[:3])


def bundled_version() -> str:
    return _version(source())


def installed_version() -> str:
    """Version du plugin installé dans le logiciel Stream Deck ("" s'il ne l'est pas)."""
    return _version(INSTALLED)


def _key(version: str) -> tuple:
    try:
        return tuple(int(x) for x in version.split("."))
    except ValueError:
        return ()


def is_outdated(version: str) -> bool:
    """Le plugin en `version` est plus ancien que celui fourni avec cette version de Multi OBS."""
    return bool(version) and _key(version) < _key(bundled_version())


def software_installed() -> bool:
    """Le logiciel Stream Deck est là (c'est lui qui ouvre les fichiers .streamDeckPlugin)."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ".streamDeckPlugin"):
            return True
    except OSError:
        return False


def package(dest: Path) -> Path:
    src = source()
    out = dest / f"{PLUGIN_UUID}.streamDeckPlugin"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            rel = f.relative_to(src)
            if f.is_file() and rel.parts[0] != "logs":
                z.write(f, (Path(FOLDER) / rel).as_posix())
    return out


def install() -> Path:
    """Ouvre le plugin avec le logiciel Stream Deck, qui propose de l'installer."""
    out = package(Path(tempfile.mkdtemp(prefix="multiobs_streamdeck_")))
    os.startfile(out)  # noqa: S606 — c'est le but : le logiciel Stream Deck prend la main
    return out
