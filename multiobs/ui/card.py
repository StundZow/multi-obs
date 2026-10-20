"""Carte d'une instance : aperçu, audio, état et commandes."""
import os

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from .. import naming, theme
from ..controller import InstanceController
from ..theme import YAMI
from .widgets import DiskBar, MeterWidget, PreviewWidget, color_dot, human_size, icon


def _restyle(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


class InstanceCard(QFrame):
    launchRequested = Signal(str)
    editRequested = Signal(str)
    deleteRequested = Signal(str)
    moveRequested = Signal(str, int)
    includeChanged = Signal(str, bool)
    recTypeChanged = Signal(str, str)
    previewHiddenChanged = Signal(str, bool)

    def __init__(self, ctrl: InstanceController, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.filename_preview = None   # fourni par la fenêtre principale
        self.setObjectName("instanceCard")
        self.setMinimumWidth(420)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.stripe = QFrame()
        self.stripe.setFixedHeight(4)
        outer.addWidget(self.stripe)

        body = QVBoxLayout()
        body.setContentsMargins(10, 8, 10, 10)
        body.setSpacing(7)
        outer.addLayout(body)

        # En-tête : nom, état, caméra virtuelle, type, menu
        head = QHBoxLayout()
        head.setSpacing(8)
        self.dot = QLabel()
        self.name = QLabel(objectName="cardName")
        self.chip = QLabel(objectName="chip")
        self.vcam_btn = QPushButton(objectName="vcamToggle")
        self.vcam_btn.setIcon(icon("webcam.svg"))
        self.vcam_btn.setIconSize(QSize(13, 13))
        self.vcam_btn.clicked.connect(ctrl.toggle_vcam)
        self.type_combo = QComboBox(objectName="typeCombo")
        self.type_combo.setToolTip("Type d'enregistrement (utilisé dans le nom des fichiers)")
        for key, label in naming.REC_TYPES:
            self.type_combo.addItem(label, key)
        self.type_combo.currentIndexChanged.connect(
            lambda: self.recTypeChanged.emit(self.ctrl.inst.id, self.type_combo.currentData()))
        self.menu_btn = QToolButton()
        self.menu_btn.setIcon(icon("dots-vert.svg"))
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_btn.setToolTip("Plus d'options")
        head.addWidget(self.dot)
        head.addWidget(self.name)
        head.addWidget(self.chip)
        head.addStretch(1)
        head.addWidget(self.vcam_btn)
        head.addWidget(self.type_combo)
        head.addWidget(self.menu_btn)
        body.addLayout(head)
        self._build_menu()

        self.preview = PreviewWidget()
        self.preview.doubleClicked.connect(self._show_window)
        self.preview.expandRequested.connect(lambda: self._set_preview_hidden(False))
        self.preview.targetChanged.connect(ctrl.set_preview_target)
        body.addWidget(self.preview)

        self.meters = MeterWidget()
        self.meters.muteToggled.connect(ctrl.toggle_mute)
        body.addWidget(self.meters)

        self.warning = QLabel(objectName="warning")
        self.warning.setWordWrap(True)
        body.addWidget(self.warning)

        self.stats = QLabel(objectName="stats")
        body.addWidget(self.stats)

        self.disk = DiskBar()
        body.addWidget(self.disk)

        # Commandes
        row = QHBoxLayout()
        row.setSpacing(5)
        self.power_btn = self._button("power.svg", "Allumer",
                                      "Allumer / éteindre l'OBS de cette instance.\n"
                                      "Il tourne réduit : tu le pilotes d'ici.")
        self.power_btn.clicked.connect(self._power)
        self.show_btn = self._button("window.svg", "Voir OBS",
                                     "Ouvrir la fenêtre OBS de cette instance (pour régler scènes et sources)")
        self.show_btn.clicked.connect(self._show_window)
        self.rec_btn = self._button("rec.svg", "Rec", "Démarrer / arrêter l'enregistrement de cette instance")
        self.rec_btn.clicked.connect(ctrl.toggle_record)
        self.pause_btn = self._button("pause.svg", "Pause", "Mettre en pause / reprendre l'enregistrement")
        self.pause_btn.clicked.connect(self._pause_clicked)
        self.include = QCheckBox("Synchro")
        self.include.setToolTip("Cochée : cette instance suit les boutons « Tout enregistrer » / « Tout en pause »\n"
                                "et les raccourcis clavier. Décoche-la pour la piloter à part (ex. l'OBS du live).")
        self.include.toggled.connect(lambda v: self.includeChanged.emit(self.ctrl.inst.id, v))
        row.addWidget(self.power_btn)
        row.addWidget(self.show_btn)
        row.addSpacing(8)
        row.addWidget(self.rec_btn)
        row.addWidget(self.pause_btn)
        row.addStretch(1)
        row.addWidget(self.include)
        body.addLayout(row)

        ctrl.changed.connect(self.refresh)
        ctrl.preview.connect(self.preview.set_image)
        ctrl.meters.connect(self._refresh_meters)
        self.apply_definition()
        self.refresh()
        self._refresh_meters()

    # ------------------------------------------------------------------ #
    def _button(self, icon_name: str, text: str, tip: str) -> QPushButton:
        b = QPushButton(text)
        b.setIcon(icon(icon_name))
        b.setIconSize(QSize(14, 14))
        b.setToolTip(tip)
        return b

    def _build_menu(self) -> None:
        m = QMenu(self)
        m.addAction("Paramètres de l'instance…", lambda: self.editRequested.emit(self.ctrl.inst.id))
        m.addAction("Voir la fenêtre OBS", self._show_window)
        m.addAction("Réduire la fenêtre OBS", self.ctrl.minimize_window)
        self.act_preview = m.addAction("Masquer l'aperçu",
                                       lambda: self._set_preview_hidden(not self.ctrl.inst.preview_hidden))
        m.addSeparator()
        self.act_rec_folder = m.addAction("Ouvrir le dossier des enregistrements", self.ctrl.open_record_folder)
        m.addAction("Ouvrir le dossier de l'instance", lambda: os.startfile(self.ctrl.inst.dir)
                    if self.ctrl.inst.dir.exists() else None)
        m.addSeparator()
        m.addAction("Déplacer à gauche", lambda: self.moveRequested.emit(self.ctrl.inst.id, -1))
        m.addAction("Déplacer à droite", lambda: self.moveRequested.emit(self.ctrl.inst.id, 1))
        m.addSeparator()
        self.act_kill = m.addAction("Forcer l'arrêt (si OBS ne répond plus)", self.ctrl.kill)
        m.addAction("Supprimer l'instance…", lambda: self.deleteRequested.emit(self.ctrl.inst.id))
        m.aboutToShow.connect(self._menu_state)
        self.menu_btn.setMenu(m)

    def _menu_state(self) -> None:
        self.act_kill.setEnabled(self.ctrl.running)
        self.act_rec_folder.setEnabled(self.ctrl.connected)
        self.act_preview.setText("Afficher l'aperçu" if self.ctrl.inst.preview_hidden else "Masquer l'aperçu")

    def _set_preview_hidden(self, hidden: bool) -> None:
        self.preview.set_collapsed(hidden)
        self.previewHiddenChanged.emit(self.ctrl.inst.id, hidden)

    def apply_definition(self) -> None:
        inst = self.ctrl.inst
        col = theme.accent(inst.color, 2)
        self.stripe.setStyleSheet(
            f"background: {col}; border-top-left-radius: 6px; border-top-right-radius: 6px;")
        self.setStyleSheet(
            f"QFrame#instanceCard {{ background: {theme.mix(YAMI['grey6'], col, 0.07)}; "
            f"border: 1px solid {theme.mix(YAMI['grey5'], col, 0.25)}; }}")
        self.dot.setPixmap(color_dot(col, 12))
        self.name.setText(inst.name)
        self.vcam_btn.setText(f"VCam {inst.vcam}")
        self.vcam_btn.setToolTip(f"Allumer / éteindre la caméra virtuelle « OBS Virtual Camera {inst.vcam} »\n"
                                 "(pour Discord, ou comme source dans une autre instance)")
        self.include.blockSignals(True)
        self.include.setChecked(inst.include_global)
        self.include.blockSignals(False)
        self.type_combo.blockSignals(True)
        self.type_combo.setCurrentIndex(max(0, self.type_combo.findData(inst.rec_type)))
        self.type_combo.blockSignals(False)
        self.preview.set_collapsed(inst.preview_hidden)

    # ------------------------------------------------------------------ #
    def _power(self) -> None:
        if self.ctrl.running:
            if self.ctrl.recording or self.ctrl.streaming:
                r = QMessageBox.question(self, "Éteindre l'instance",
                                         f"« {self.ctrl.inst.name} » enregistre ou est en live.\n"
                                         "L'éteindre quand même ? (l'enregistrement est finalisé proprement)")
                if r != QMessageBox.StandardButton.Yes:
                    return
            if not self.ctrl.shutdown_gracefully():
                self.ctrl.kill()
        else:
            self.launchRequested.emit(self.ctrl.inst.id)

    def _pause_clicked(self) -> None:
        if self.ctrl.pause_blocked and not self.ctrl.paused:
            r = QMessageBox.question(
                self, "Activer la pause",
                f"OBS désactive la pause de « {self.ctrl.inst.name} » : sa qualité d'enregistrement est "
                "« Identique au stream ».\n\nPasser en « Haute qualité, taille moyenne » pour pouvoir mettre en "
                "pause ? (prend effet au prochain enregistrement)")
            if r == QMessageBox.StandardButton.Yes:
                self.ctrl.fix_pause()
            return
        self.ctrl.toggle_pause()

    def _show_window(self) -> None:
        if self.ctrl.running:
            self.ctrl.show_window()
        else:
            self.launchRequested.emit(self.ctrl.inst.id)

    def _set_active(self, w: QWidget, value: str) -> None:
        if w.property("active") != value:
            w.setProperty("active", value)
            _restyle(w)

    def _set_chip(self, text: str, state: str) -> None:
        self.chip.setText(text)
        if self.chip.property("state") != state:
            self.chip.setProperty("state", state)
            _restyle(self.chip)

    def refresh(self) -> None:
        c = self.ctrl
        status = c.status
        connected = c.connected
        fps_setting = int(c.settings.get("preview_fps", 60)) if c.settings else 60

        if status == "stopped":
            self._set_chip("Éteinte", "")
            self.preview.placeholder = "Instance éteinte — double-clic pour l'allumer"
        elif status == "starting":
            self._set_chip("Extinction…" if c.closing else "Démarrage…", "busy")
            self.preview.placeholder = "Connexion à OBS…"
        else:
            self.preview.placeholder = ("Aperçu désactivé (Paramètres)" if fps_setting <= 0
                                        else "En attente de l'image…")
            if c.recording and c.paused:
                self._set_chip("PAUSE", "pause")
            elif c.recording:
                self._set_chip("REC", "rec")
            elif c.streaming:
                self._set_chip("LIVE", "live")
            else:
                self._set_chip("Prête", "ready")

        badges = []
        if c.recording:
            badges.append((("PAUSE  " if c.paused else "● ") + (c.rec_time or "00:00:00"),
                           YAMI["yellow3"] if c.paused else YAMI["red3"]))
        if c.streaming:
            badges.append(("LIVE " + (c.stream_time or ""), YAMI["red4"]))
        if (badges, self.preview.corner) != (self.preview.badges, "VCam active" if c.vcam_on else "") \
                or status == "stopped":
            self.preview.badges = badges
            self.preview.corner = "VCam active" if c.vcam_on else ""
            if status == "stopped":
                self.preview.image = None
            self.preview.update()

        self.power_btn.setText("Éteindre" if c.running else "Allumer")
        self._set_active(self.power_btn, "on" if c.running else "")
        self.show_btn.setEnabled(c.running)
        self.rec_btn.setEnabled(connected)
        self.vcam_btn.setEnabled(connected)
        self.pause_btn.setEnabled(connected and (c.recording or c.pause_blocked))
        self.pause_btn.setToolTip(
            "Pause désactivée par OBS (qualité « Identique au stream ») — clic pour corriger"
            if c.pause_blocked else "Mettre en pause / reprendre l'enregistrement")
        self.rec_btn.setText("Stop" if c.recording else "Rec")
        self.rec_btn.setIcon(icon("stop.svg" if c.recording else "rec.svg"))
        self._set_active(self.rec_btn, "rec" if c.recording else "")
        self.pause_btn.setText("Reprendre" if c.paused else "Pause")
        self.pause_btn.setIcon(icon("play.svg" if c.paused else "pause.svg"))
        self._set_active(self.pause_btn, "pause" if c.paused else "")
        self._set_active(self.vcam_btn, "on" if c.vcam_on else "")

        if connected:
            parts = [f"{c.fps or 0:.0f} ips", f"CPU {c.cpu or 0:.1f} %", f"{c.memory or 0:.0f} Mo"]
            if c.render_skipped or c.output_skipped:
                parts.append(f"perdues {c.render_skipped + c.output_skipped}")
            if c.recording and c.rec_bytes:
                parts.append(human_size(c.rec_bytes))
            if c.scene:
                parts.append(f"Scène : {c.scene}")
            if not c.inst.preview_hidden and fps_setting > 0:
                preview = f"aperçu {c.preview_fps_measured:.0f} i/s" if c.preview_fps_measured else "aperçu"
                if c.preview_note:
                    preview += f" ({c.preview_note})"
                parts.append(preview)
            self.stats.setText("  ·  ".join(parts))
        elif status == "starting":
            self.stats.setText("En attente d'OBS…")
        else:
            self.stats.setText(f"Port {c.inst.port}  ·  dossier {c.inst.id}")

        folder = getattr(c, "disk_path", "")
        display = folder
        if c.recording and c.rec_path:
            display = c.rec_path
        elif folder and self.filename_preview:
            display = folder.rstrip("/\\") + "\\" + self.filename_preview()
        self.disk.set_state(c.disk_free, c.disk_total, folder, c.bytes_per_second(), display)

        warns = c.warnings()
        self.warning.setVisible(bool(warns))
        self.warning.setText("⚠ " + "   ⚠ ".join(warns))

    def _refresh_meters(self) -> None:
        c = self.ctrl
        rows = [(n, c.levels.get(n, []), c.mutes.get(n, False)) for n in c.meter_order]
        empty = ""
        if c.connected and not rows:
            empty = "Aucune source audio active"
        self.meters.set_rows(rows, empty)
