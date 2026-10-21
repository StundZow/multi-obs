"""Bas à droite de la fenêtre : état du plugin Stream Deck (connecté, déconnecté) ou bouton pour
l'installer. Rien n'est affiché sur un PC sans logiciel Stream Deck."""
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QToolButton, QWidget

from .. import APP_NAME, streamdeck
from ..theme import YAMI

INSTALL_WAIT_S = 90   # après « Installer » : le logiciel Stream Deck attend la confirmation

# état → (couleur de la pastille, texte, bouton, info-bulle)
LOOKS = {
    "connected": (YAMI["green2"], "Stream Deck connecté", "", "Le plugin Stream Deck pilote Multi OBS."),
    "disconnected": (YAMI["grey1"], "Stream Deck déconnecté", "",
                     "Le plugin est installé mais ne répond pas : le logiciel Stream Deck est-il ouvert ?"),
    "missing": ("", "Plugin Stream Deck :", "Installer",
                "Installe le plugin Multi OBS dans le logiciel Stream Deck (il demande confirmation)."),
    "installing": ("", "Plugin Stream Deck : confirme dans Stream Deck…", "", ""),
    "outdated": (YAMI["yellow2"], "Plugin Stream Deck à mettre à jour :", "Mettre à jour",
                 "Une version plus récente du plugin est fournie avec Multi OBS."),
    "disabled": (YAMI["grey1"], "Stream Deck désactivé", "",
                 "Pilotage par le Stream Deck désactivé : Paramètres → Stream Deck."),
}


class DeckStatus(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(4)
        self.dot = QLabel("●", objectName="deckDot")
        self.text = QLabel(objectName="deckText")
        self.button = QToolButton(objectName="deckButton")
        self.button.clicked.connect(self._install)
        for w in (self.dot, self.text, self.button):
            lay.addWidget(w)
        self.state = ""
        self._install_asked = -INSTALL_WAIT_S
        self._timer = QTimer(self, interval=2000, timeout=self.refresh)   # installation faite dans Stream Deck
        self._timer.start()
        self.refresh()

    def _current(self) -> str:
        remote = self.window.remote
        clients = remote.connected_clients() if remote else []
        if clients:
            return "outdated" if any(streamdeck.is_outdated(c["version"]) for c in clients) else "connected"
        if not self.window.manager.settings.get("remote_enabled", True):
            return "disabled"
        installed = streamdeck.installed_version()
        if not installed:
            if not streamdeck.software_installed():
                return "none"
            return "installing" if time.monotonic() - self._install_asked < INSTALL_WAIT_S else "missing"
        return "outdated" if streamdeck.is_outdated(installed) else "disconnected"

    def refresh(self) -> None:
        state = self._current()
        if state == self.state:
            return
        self.state = state
        self.setVisible(state != "none")
        if state == "none":
            return
        color, text, button, tip = LOOKS[state]
        self.dot.setVisible(bool(color))
        self.dot.setStyleSheet(f"color: {color};")
        self.text.setText(text)
        self.button.setVisible(bool(button))
        self.button.setText(button)
        self.setToolTip(tip)

    def _install(self) -> None:
        try:
            streamdeck.install()
        except OSError as e:
            QMessageBox.warning(self.window, APP_NAME, f"Le logiciel Stream Deck n'a pas pu ouvrir le plugin :\n{e}")
            return
        self._install_asked = time.monotonic()
        self.refresh()
