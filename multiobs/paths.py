"""Emplacements des fichiers de Multi OBS et détection de l'installation d'OBS."""
import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = _app_root()
DATA = ROOT / "data"
RUNTIME = DATA / "runtime"          # copie de référence d'OBS (source des liens physiques)
INSTANCES = DATA / "instances"      # une installation OBS portable par instance
VCAM = DATA / "vcam"                # modules de caméra virtuelle patchés
PRESETS = DATA / "presets"          # préconfigs enregistrées
TRASH = DATA / "corbeille"          # configs des instances supprimées
STATE_FILE = DATA / "multiobs.json"

if getattr(sys, "frozen", False):
    ASSETS = Path(getattr(sys, "_MEIPASS", ROOT)) / "multiobs" / "assets"
else:
    ASSETS = Path(__file__).resolve().parent / "assets"
ICONS = ASSETS / "icons"

OBS_EXE_REL = Path("bin") / "64bit" / "obs64.exe"
USER_OBS_CONFIG = Path(os.environ.get("APPDATA", "")) / "obs-studio"


def icon_path(name: str) -> str:
    return str(ICONS / name)


def find_obs_install() -> Path | None:
    """Cherche l'installation d'OBS Studio (registre puis emplacements par défaut)."""
    candidates: list[Path] = []
    try:
        import winreg
        for hive, key in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\OBS Studio"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\OBS Studio"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\OBS Studio"),
        ):
            try:
                with winreg.OpenKey(hive, key) as k:
                    value, _ = winreg.QueryValueEx(k, "")
                    if value:
                        candidates.append(Path(value))
            except OSError:
                pass
    except ImportError:
        pass
    for env in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        if os.environ.get(env):
            candidates.append(Path(os.environ[env]) / "obs-studio")
    for c in candidates:
        if (c / OBS_EXE_REL).exists():
            return c
    return None


def file_version(path: Path) -> str:
    """Version produit d'un exécutable Windows, ex. '32.1.2'."""
    try:
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(str(path), 0, size, buf):
            return ""
        ptr = ctypes.c_void_p()
        length = wintypes.UINT()
        langs = []
        if ver.VerQueryValueW(buf, r"\VarFileInfo\Translation", ctypes.byref(ptr), ctypes.byref(length)):
            arr = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint16 * (length.value // 2))).contents
            langs = [(arr[i], arr[i + 1]) for i in range(0, len(arr) - 1, 2)]
        for lang, cp in langs + [(0x0409, 0x04B0), (0x0409, 0x04E4)]:
            key = rf"\StringFileInfo\{lang:04x}{cp:04x}\ProductVersion"
            if ver.VerQueryValueW(buf, key, ctypes.byref(ptr), ctypes.byref(length)) and length.value:
                value = ctypes.wstring_at(ptr.value, length.value).rstrip("\x00").strip()
                if value:
                    return value.split("-")[0]
        return ""
    except Exception:
        return ""
