"""Barre des tâches : chaque instance s'affiche « OBS Blue — Caméra » avec le logo OBS
à sa couleur, pour s'y retrouver d'un coup d'œil.

Le titre et l'icône sont posés sur la fenêtre d'OBS depuis Multi OBS (OBS remet son
titre quand on change de profil : il est simplement réappliqué). À la fermeture de
Multi OBS, l'icône d'origine est remise (les nôtres disparaîtraient avec le processus).
"""
import ctypes
import struct
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from . import paths, theme

COLOR_NAMES = {"blue": "Blue", "red": "Red", "green": "Green", "purple": "Purple",
               "teal": "Cyan", "pink": "Pink", "yellow": "Yellow"}
ICONS_DIR = paths.DATA / "icons"
ICON_VERSION = 1

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.PrivateExtractIconsW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.UINT),
                                        wintypes.UINT, wintypes.UINT]
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                       wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = ctypes.c_size_t
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]

WM_SETTEXT = 0x000C
WM_GETICON = 0x007F
WM_SETICON = 0x0080
ICON_SMALL, ICON_BIG = 0, 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x10
SMTO_ABORTIFHUNG = 0x2
SM_CXICON, SM_CXSMICON = 11, 49


def window_title(name: str, color: str) -> str:
    return f"OBS {COLOR_NAMES.get(color, 'Studio')} — {name}"


# --------------------------------------------------------------------------- #
# Icônes colorées
# --------------------------------------------------------------------------- #
def _obs_logo() -> QImage | None:
    for exe in (paths.RUNTIME / paths.OBS_EXE_REL,
                (paths.find_obs_install() or Path("-")) / paths.OBS_EXE_REL):
        if not exe.exists():
            continue
        hicon = wintypes.HICON()
        iid = wintypes.UINT()
        if user32.PrivateExtractIconsW(str(exe), 0, 256, 256, ctypes.byref(hicon), ctypes.byref(iid), 1, 0) \
                and hicon.value:
            img = QImage.fromHICON(hicon.value)
            user32.DestroyIcon(hicon)
            if not img.isNull():
                return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    return None


def _tint(logo: QImage, color: str) -> QImage:
    """Disque sombre du logo -> couleur de l'instance ; anneau et tourbillon restent clairs."""
    out = QImage(logo.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.drawImage(0, 0, logo)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(out.rect(), QColor(theme.accent(color, 2)))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)
    p.drawImage(0, 0, logo)
    p.end()
    return out


def _write_ico(path: Path, img: QImage) -> None:
    """ICO multi-tailles (images PNG), pour une icône nette à toutes les échelles."""
    entries = []
    for size in (16, 20, 24, 32, 40, 48, 64, 96, 256):
        scaled = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(buf, "PNG")
        entries.append((size, bytes(buf.data())))
    offset = 6 + 16 * len(entries)
    directory, blobs = b"", b""
    for size, data in entries:
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    path.write_bytes(struct.pack("<HHH", 0, 1, len(entries)) + directory + blobs)


def icon_file(color: str) -> Path | None:
    path = ICONS_DIR / f"obs-{color}-v{ICON_VERSION}.ico"
    if path.exists():
        return path
    logo = _obs_logo()
    if logo is None:
        return None
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    _write_ico(path, _tint(logo, color))
    return path


# --------------------------------------------------------------------------- #
# Application sur la fenêtre d'OBS
# --------------------------------------------------------------------------- #
def _send(hwnd, msg, wparam=0, lparam=0) -> int:
    result = ctypes.c_size_t()
    ok = user32.SendMessageTimeoutW(hwnd, msg, wparam, lparam, SMTO_ABORTIFHUNG, 300, ctypes.byref(result))
    return result.value if ok else 0


def _title(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


class TaskbarDecor:
    """Titre + icône d'une fenêtre OBS, avec mémoire de l'état d'origine."""

    def __init__(self):
        self.hwnd = None
        self.color = None
        self.icons: tuple[int, int] | None = None      # (grande, petite) — à nous
        self.original_icons: tuple[int, int] | None = None
        self.original_title: str | None = None

    def apply(self, hwnd, name: str, color: str) -> None:
        if hwnd != self.hwnd:
            self._forget()
            self.hwnd = hwnd
        title = window_title(name, color)
        current = _title(hwnd)
        if current != title:
            ours = tuple(f"OBS {n} — " for n in COLOR_NAMES.values())
            if not current.startswith(ours):
                self.original_title = current   # titre posé par OBS (il le remet au changement de profil)
            buf = ctypes.create_unicode_buffer(title)
            _send(hwnd, WM_SETTEXT, 0, ctypes.addressof(buf))
        if color != self.color:
            self._load_icons(color)
        if self.icons and _send(hwnd, WM_GETICON, ICON_BIG) != self.icons[0]:
            if self.original_icons is None:
                self.original_icons = (_send(hwnd, WM_GETICON, ICON_BIG), _send(hwnd, WM_GETICON, ICON_SMALL))
            _send(hwnd, WM_SETICON, ICON_BIG, self.icons[0])
            _send(hwnd, WM_SETICON, ICON_SMALL, self.icons[1])

    def _load_icons(self, color: str) -> None:
        path = icon_file(color)
        self.color = color
        if not path:
            self.icons = None
            return
        big = max(32, user32.GetSystemMetrics(SM_CXICON)) * 2   # assez grand pour la barre des tâches
        small = max(16, user32.GetSystemMetrics(SM_CXSMICON))
        h_big = user32.LoadImageW(None, str(path), IMAGE_ICON, big, big, LR_LOADFROMFILE)
        h_small = user32.LoadImageW(None, str(path), IMAGE_ICON, small, small, LR_LOADFROMFILE)
        self.icons = (h_big, h_small) if h_big and h_small else None

    def restore(self) -> None:
        """Remet l'icône (et le titre) d'origine : les nôtres meurent avec Multi OBS."""
        hwnd = self.hwnd
        if hwnd and user32.IsWindow(hwnd):
            if self.original_icons:
                _send(hwnd, WM_SETICON, ICON_BIG, self.original_icons[0])
                _send(hwnd, WM_SETICON, ICON_SMALL, self.original_icons[1])
            if self.original_title:
                buf = ctypes.create_unicode_buffer(self.original_title)
                _send(hwnd, WM_SETTEXT, 0, ctypes.addressof(buf))
        self._forget()

    def _forget(self) -> None:
        self.hwnd = None
        self.original_icons = None
        self.original_title = None
