"""Raccourcis clavier globaux Windows (RegisterHotKey).

Enregistrés au niveau du thread (sans fenêtre) : ils restent valables même si Qt
recrée la fenêtre principale (son identifiant change alors).
"""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer, Qt
from PySide6.QtGui import QKeySequence

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
HOTKEY_BASE_ID = 0xB000   # identifiants propres à Multi OBS


def to_native(seq_text: str) -> tuple[int, int] | None:
    seq = QKeySequence(seq_text)
    if seq.isEmpty():
        return None
    combo = seq[0]
    key = combo.key()
    mods = combo.keyboardModifiers()
    native_mods = MOD_NOREPEAT
    if mods & Qt.KeyboardModifier.ControlModifier:
        native_mods |= MOD_CONTROL
    if mods & Qt.KeyboardModifier.AltModifier:
        native_mods |= MOD_ALT
    if mods & Qt.KeyboardModifier.ShiftModifier:
        native_mods |= MOD_SHIFT
    if mods & Qt.KeyboardModifier.MetaModifier:
        native_mods |= MOD_WIN
    k = key.value if hasattr(key, "value") else int(key)
    if Qt.Key.Key_A.value <= k <= Qt.Key.Key_Z.value or Qt.Key.Key_0.value <= k <= Qt.Key.Key_9.value:
        vk = k
    elif Qt.Key.Key_F1.value <= k <= Qt.Key.Key_F24.value:
        vk = 0x70 + (k - Qt.Key.Key_F1.value)
    elif k == Qt.Key.Key_Space.value:
        vk = 0x20
    elif k == Qt.Key.Key_Pause.value:
        vk = 0x13
    else:
        return None
    return native_mods, vk


class GlobalHotkeys(QAbstractNativeEventFilter):
    def __init__(self, _hwnd: int | None = None):
        super().__init__()
        self.callbacks: dict[int, object] = {}

    def set(self, bindings: list[tuple[str, object]]) -> list[str]:
        """Remplace les raccourcis. Renvoie ceux qui n'ont pas pu être pris (déjà utilisés…)."""
        self.clear()
        failed = []
        for idx, (text, cb) in enumerate(bindings):
            native = to_native(text)
            if not native:
                continue
            hid = HOTKEY_BASE_ID + idx
            if user32.RegisterHotKey(None, hid, native[0], native[1]):
                self.callbacks[hid] = cb
            else:
                failed.append(text)
        return failed

    def clear(self) -> None:
        for hid in list(self.callbacks):
            user32.UnregisterHotKey(None, hid)
        self.callbacks.clear()

    def nativeEventFilter(self, event_type, message):
        # Raccourci de thread : message sans fenêtre, vu au niveau du répartiteur d'événements.
        if bytes(event_type) in (b"windows_dispatcher_MSG", b"windows_generic_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and not msg.hWnd:
                cb = self.callbacks.get(int(msg.wParam))
                if cb:
                    QTimer.singleShot(0, cb)
                    return True, 0
        return False, 0
