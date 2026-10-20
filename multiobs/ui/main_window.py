"""Fenêtre principale de Multi OBS."""
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from .. import APP_NAME, APP_VERSION, obsfiles, paths, vcam
from ..hotkeys import GlobalHotkeys
from ..manager import AUTOSAVE_SLUG, Manager
from ..preview import STATE_ACTIVE, STATE_AWAY, STATE_BACKGROUND
from ..syswatch import SystemEvents
from .card import InstanceCard
from .dialogs import InstanceDialog, SettingsDialog
from .tasks import Task, run_task
from .widgets import icon

CARD_MIN_W = 440
COMPACT_BELOW = 1060


def _vsep() -> QFrame:
    f = QFrame()
    f.setObjectName("vsep")
    return f


class MainWindow(QMainWindow):
    def __init__(self, manager: Manager):
        super().__init__()
        self.manager = manager
        self.cards: dict[str, InstanceCard] = {}
        self._columns = 0
        self._compact = False
        self.setWindowTitle(APP_NAME)
        self.resize(1320, 900)
        self.setMinimumSize(900, 520)

        central = QWidget(objectName="central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_top_bar())
        root.addWidget(self._build_naming_bar())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget(objectName="cardsContainer")
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(14, 14, 14, 14)
        self.grid.setSpacing(12)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)
        self.empty = self._build_empty_state()

        self.status_obs = QLabel()
        self.status_vcam = QLabel()
        self.status_hotkeys = QLabel()
        sb = self.statusBar()
        sb.addWidget(self.status_obs)
        sb.addWidget(self.status_vcam)
        sb.addPermanentWidget(self.status_hotkeys)

        manager.instancesChanged.connect(self.rebuild_cards)
        self.rebuild_cards()
        self.refresh_presets()

        self.hotkeys = GlobalHotkeys(int(self.winId()))
        QApplication.instance().installNativeEventFilter(self.hotkeys)
        self.apply_hotkeys()

        # Contexte des aperçus : premier plan, arrière-plan, absent ; cartes visibles ou non.
        self.system = SystemEvents(int(self.winId()))
        QApplication.instance().installNativeEventFilter(self.system.filter)
        self.system.awayChanged.connect(lambda _a: self._schedule_context())
        QGuiApplication.instance().applicationStateChanged.connect(lambda _s: self._schedule_context())
        self._context_timer = QTimer(self, singleShot=True, interval=120, timeout=self._update_preview_context)
        self.scroll.verticalScrollBar().valueChanged.connect(lambda _v: self._schedule_context())

        self._timer = QTimer(self, interval=500, timeout=self.refresh_global)
        self._timer.start()
        self.refresh_global()
        self.refresh_status()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def _btn(self, text: str, icon_name: str | None, tip: str, slot) -> QPushButton:
        b = QPushButton(text)
        if icon_name:
            b.setIcon(icon(icon_name))
            b.setIconSize(QSize(14, 14))
        b.setToolTip(tip)
        b.clicked.connect(slot)
        return b

    def _build_top_bar(self) -> QFrame:
        bar = QFrame(objectName="topBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(6)

        logo = QLabel()
        logo.setPixmap(QApplication.instance().windowIcon().pixmap(26, 26))
        title = QLabel(APP_NAME, objectName="appTitle")
        lay.addWidget(logo)
        lay.addWidget(title)
        lay.addWidget(_vsep())

        self.launch_all_btn = self._btn("Tout allumer", "power.svg", "Allumer toutes les instances", self.launch_all)
        self.close_all_btn = self._btn("Tout éteindre", "close.svg", "Éteindre toutes les instances", self.close_all)
        lay.addWidget(self.launch_all_btn)
        lay.addWidget(self.close_all_btn)
        lay.addWidget(_vsep())

        self.rec_all_btn = self._btn("Tout enregistrer", "rec.svg",
                                     "Démarrer / arrêter l'enregistrement des instances liées (Link)",
                                     self.toggle_record_all)
        self.pause_all_btn = self._btn("Tout en pause", "pause.svg",
                                       "Mettre en pause / reprendre les enregistrements des instances liées (Link)",
                                       self.toggle_pause_all)
        lay.addWidget(self.rec_all_btn)
        lay.addWidget(self.pause_all_btn)
        lay.addStretch(1)

        new_btn = self._btn("Nouvelle instance", "plus.svg", "Créer une nouvelle instance OBS", self.new_instance)
        new_btn.setProperty("role", "primary")
        lay.addWidget(new_btn)
        lay.addWidget(self._btn("", "cogs.svg", "Paramètres", self.open_settings))
        return bar

    def _build_naming_bar(self) -> QFrame:
        bar = QFrame(objectName="namingBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 7, 14, 7)
        lay.setSpacing(6)
        s = self.manager.settings
        lbl = QLabel("Nom")
        lbl.setProperty("muted", True)
        lay.addWidget(lbl)
        self.creator_edit = QLineEdit(s.get("creator", ""))
        self.creator_edit.setPlaceholderText("ton nom")
        self.creator_edit.setFixedWidth(150)
        self.creator_edit.setToolTip("Ton nom, au début du nom de chaque fichier")
        lay.addWidget(self.creator_edit)
        lbl = QLabel("Vidéo")
        lbl.setProperty("muted", True)
        lay.addWidget(lbl)
        self.video_edit = QLineEdit(s.get("video_name", ""))
        self.video_edit.setPlaceholderText("nom de la vidéo")
        self.video_edit.setToolTip("Nom de la vidéo, appliqué au nom des fichiers de toutes les instances")
        self.video_edit.setMinimumWidth(180)
        lay.addWidget(self.video_edit, 2)
        self.naming_preview = QLabel(objectName="namingPreview")
        self.naming_preview.setMinimumWidth(80)
        self.naming_preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.naming_preview, 3)
        self._naming_timer = QTimer(self, singleShot=True, interval=500, timeout=self._apply_naming)
        self.creator_edit.textChanged.connect(lambda: (self._naming_timer.start(), self._refresh_naming_preview()))
        self.video_edit.textChanged.connect(lambda: (self._naming_timer.start(), self._refresh_naming_preview()))
        lay.addWidget(_vsep())

        lbl = QLabel("Préconfig")
        lbl.setProperty("muted", True)
        lay.addWidget(lbl)
        self.preset_combo = QComboBox()
        self.preset_combo.setFixedWidth(230)
        lay.addWidget(self.preset_combo)
        self.preset_open_btn = self._btn("Ouvrir", None, "Ouvrir la préconfig choisie (remplace les instances)",
                                         self.open_preset)
        lay.addWidget(self.preset_open_btn)
        lay.addWidget(self._btn("Enregistrer", "save.svg", "Enregistrer la configuration actuelle comme préconfig",
                                self.save_preset))
        self.preset_del_btn = self._btn("", "trash.svg", "Supprimer la préconfig choisie", self.delete_preset)
        lay.addWidget(self.preset_del_btn)
        return bar

    def _apply_naming(self) -> None:
        self.manager.set_naming(self.creator_edit.text(), self.video_edit.text())
        for card in self.cards.values():
            card.refresh()

    def _refresh_naming_preview(self) -> None:
        from .. import naming
        s = self.manager.settings
        example = naming.preview(s.get("filename_template"), self.creator_edit.text(), "cam", self.video_edit.text())
        fm = self.naming_preview.fontMetrics()
        self.naming_preview.setToolTip(f"Nom du prochain fichier : {example}")
        self.naming_preview.setText(fm.elidedText(f"output : {example}", Qt.TextElideMode.ElideRight,
                                                  max(60, self.naming_preview.width())))

    def _build_empty_state(self) -> QFrame:
        f = QFrame(objectName="emptyState")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(12)
        t = QLabel("Aucune instance OBS")
        t.setStyleSheet("font-size: 14pt; font-weight: 600;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d = QLabel("Chaque instance est un OBS indépendant avec ses propres scènes, réglages, couleur\n"
                   "et caméra virtuelle. Crée-en une par usage : caméra, écran, live…")
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d.setProperty("muted", True)
        b = QPushButton("Créer une instance")
        b.setIcon(icon("plus.svg"))
        b.setProperty("role", "primary")
        b.clicked.connect(self.new_instance)
        lay.addWidget(t)
        lay.addWidget(d)
        lay.addWidget(b, 0, Qt.AlignmentFlag.AlignCenter)
        return f

    # ------------------------------------------------------------------ #
    # Cartes
    # ------------------------------------------------------------------ #
    def rebuild_cards(self) -> None:
        ids = [i.id for i in self.manager.instances]
        for inst_id in list(self.cards):
            card = self.cards[inst_id]
            if inst_id not in ids or card.ctrl is not self.manager.controllers.get(inst_id):
                card.setParent(None)
                card.deleteLater()
                del self.cards[inst_id]
        for inst in self.manager.instances:
            if inst.id not in self.cards:
                card = InstanceCard(self.manager.controller(inst.id))
                card.ctrl.actionFailed.connect(lambda m: self.statusBar().showMessage("⚠ " + m, 10000))
                card.launchRequested.connect(lambda i: self.launch([i]))
                card.editRequested.connect(self.edit_instance)
                card.deleteRequested.connect(self.delete_instance)
                card.moveRequested.connect(self.manager.move_instance)
                card.includeChanged.connect(self._set_include)
                card.recTypeChanged.connect(self.manager.set_rec_type)
                card.previewHiddenChanged.connect(self._set_preview_hidden)
                card.filename_preview = (lambda i=inst.id: self.manager.filename_preview(
                    next(x for x in self.manager.instances if x.id == i)))
                self.cards[inst.id] = card
            else:
                self.cards[inst.id].apply_definition()
        self._columns = 0
        self._relayout()
        self.refresh_status()
        self._schedule_context()

    def _relayout(self) -> None:
        avail = self.scroll.viewport().width() - 28
        cols = max(1, min(len(self.cards) or 1, (avail + 12) // (CARD_MIN_W + 12)))
        if cols == self._columns and self.grid.count() == max(1, len(self.cards)):
            return
        self._columns = cols
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None) if item.widget() is self.empty else None
        for c in range(self.grid.columnCount()):
            self.grid.setColumnStretch(c, 0)
        if not self.cards:
            self.grid.addWidget(self.empty, 0, 0, Qt.AlignmentFlag.AlignTop)
            self.grid.setColumnStretch(0, 1)
            self.grid.setRowStretch(1, 1)
            return
        self.grid.setRowStretch(1, 0)
        for k, inst in enumerate(self.manager.instances):
            self.grid.addWidget(self.cards[inst.id], k // cols, k % cols, Qt.AlignmentFlag.AlignTop)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        rows = (len(self.cards) + cols - 1) // cols
        self.grid.setRowStretch(rows, 1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()
        self._schedule_context()
        compact = self.width() < COMPACT_BELOW
        if compact != self._compact:
            self._compact = compact
            self.refresh_global()
        self._refresh_naming_preview()

    def _label(self, btn: QPushButton, text: str) -> None:
        """Texte des boutons globaux (icône seule quand la fenêtre est étroite)."""
        btn.setText("" if self._compact else text)
        if self._compact:
            btn.setToolTip(text)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._relayout)
        self._schedule_context()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._schedule_context()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() in (e.Type.WindowStateChange, e.Type.ActivationChange):
            self._schedule_context()

    def _schedule_context(self) -> None:
        if hasattr(self, "_context_timer"):
            self._context_timer.start()

    def _update_preview_context(self) -> None:
        """Met en pause / ralentit les aperçus selon ce qui est réellement visible."""
        if self.isMinimized() or not self.isVisible() or self.system.away:
            state = STATE_AWAY
        elif QGuiApplication.applicationState() == Qt.ApplicationState.ApplicationActive:
            state = STATE_ACTIVE
        else:
            state = STATE_BACKGROUND
        self.manager.set_app_state(state)
        for card in self.cards.values():
            visible = (not card.ctrl.inst.preview_hidden and card.isVisible()
                       and not card.preview.visibleRegion().isEmpty())
            card.ctrl.set_preview_visible(visible)

    def _set_preview_hidden(self, inst_id: str, hidden: bool) -> None:
        self.manager.set_preview_hidden(inst_id, hidden)
        self._schedule_context()

    def _set_include(self, inst_id: str, value: bool) -> None:
        for inst in self.manager.instances:
            if inst.id == inst_id:
                inst.include_global = value
        self.manager.save()

    # ------------------------------------------------------------------ #
    # Lancement / fermeture
    # ------------------------------------------------------------------ #
    def launch(self, inst_ids: list[str], import_from: dict | None = None) -> None:
        insts = [i for i in self.manager.instances
                 if i.id in inst_ids and not self.manager.controller(i.id).running]
        if not insts:
            return
        if self.manager.runtime_status() == "outdated" and not self.manager.any_running():
            r = QMessageBox.question(
                self, APP_NAME,
                "Ton OBS a été mis à jour depuis la création des instances.\n\n"
                "Mettre à jour les instances maintenant ? (scènes et réglages conservés)")
            if r == QMessageBox.StandardButton.Yes:
                run_task(self, "Mise à jour d'OBS", self.manager.update_obs,
                         on_done=lambda _r: self.launch(inst_ids, import_from))
                return

        def done(missing_vcams):
            for inst in insts:
                self.manager.controller(inst.id).start()
            if missing_vcams and self.manager.settings.get("vcam_scope") == vcam.SCOPE_USER:
                self.statusBar().showMessage(
                    "Caméra(s) virtuelle(s) non installée(s) : " + ", ".join(map(str, missing_vcams))
                    + " — voir Paramètres.", 10000)
            self.refresh_status()

        names = ", ".join(i.name for i in insts)
        run_task(self, f"Préparation de {names}",
                 lambda p: self.manager.prepare(insts, p, import_from), on_done=done)

    def launch_all(self) -> None:
        self.launch([i.id for i in self.manager.instances])

    def close_all(self) -> None:
        recording = [c.inst.name for c in self.manager.controllers.values() if c.recording or c.streaming]
        if recording:
            r = QMessageBox.question(self, APP_NAME,
                                     "Ces instances enregistrent ou sont en live :\n• " + "\n• ".join(recording)
                                     + "\n\nTout éteindre quand même ?")
            if r != QMessageBox.StandardButton.Yes:
                return
        for c in self.manager.controllers.values():
            if c.running and not c.shutdown_gracefully():
                c.kill()

    # ------------------------------------------------------------------ #
    # Actions globales
    # ------------------------------------------------------------------ #
    def _targets(self):
        return [self.manager.controller(i.id) for i in self.manager.instances
                if i.include_global and self.manager.controller(i.id).connected]

    def toggle_record_all(self) -> None:
        targets = self._targets()
        if any(c.recording for c in targets):
            for c in targets:
                c.stop_record()
        else:
            for c in targets:
                c.start_record()

    def toggle_pause_all(self) -> None:
        recs = [c for c in self._targets() if c.recording]
        blocked = [c.inst.name for c in recs if c.pause_blocked and not c.paused]
        if blocked:
            self.statusBar().showMessage(
                "⚠ Pause impossible pour : " + ", ".join(blocked)
                + " (qualité « Identique au stream ») — clic sur Pause sur la carte pour corriger.", 12000)
        recs = [c for c in recs if not (c.pause_blocked and not c.paused)]
        if recs and all(c.paused for c in recs):
            for c in recs:
                c.resume_record()
        else:
            for c in recs:
                c.pause_record()

    def refresh_global(self) -> None:
        targets = self._targets()
        recording = any(c.recording for c in targets)
        recs = [c for c in targets if c.recording and not (c.pause_blocked and not c.paused)]
        all_paused = bool(recs) and all(c.paused for c in recs)
        self.rec_all_btn.setEnabled(bool(targets))
        self._label(self.rec_all_btn, "Tout arrêter" if recording else "Tout enregistrer")
        self.rec_all_btn.setIcon(icon("stop.svg" if recording else "rec.svg"))
        self._set_prop(self.rec_all_btn, "active", "rec" if recording else "")
        self.pause_all_btn.setEnabled(bool(recs))
        self._label(self.pause_all_btn, "Tout reprendre" if all_paused else "Tout en pause")
        self._label(self.launch_all_btn, "Tout allumer")
        self._label(self.close_all_btn, "Tout éteindre")
        self.pause_all_btn.setIcon(icon("play.svg" if all_paused else "pause.svg"))
        self._set_prop(self.pause_all_btn, "active", "pause" if all_paused else "")
        running = self.manager.any_running()
        self.close_all_btn.setEnabled(running)
        self.launch_all_btn.setEnabled(any(not c.running for c in self.manager.controllers.values()))
        self.preset_open_btn.setEnabled(self.preset_combo.count() > 0)
        self.preset_del_btn.setEnabled(self.preset_combo.count() > 0)

    @staticmethod
    def _set_prop(w: QWidget, name: str, value) -> None:
        if w.property(name) != value:
            w.setProperty(name, value)
            w.style().unpolish(w)
            w.style().polish(w)

    # ------------------------------------------------------------------ #
    # Instances
    # ------------------------------------------------------------------ #
    def new_instance(self) -> None:
        if not self.manager.obs_source() and obsfiles.runtime_signature() is None:
            QMessageBox.warning(self, APP_NAME, "OBS Studio est introuvable. Indique son dossier dans les paramètres.")
            self.open_settings()
            return
        dlg = InstanceDialog(self.manager, parent=self)
        if not dlg.exec():
            return
        inst = dlg.result_definition()
        self.manager.add_instance(inst)
        if dlg.launch.isChecked():
            imp = {inst.id: paths.USER_OBS_CONFIG} if dlg.import_cfg.isChecked() else None
            self.launch([inst.id], imp)
        elif dlg.import_cfg.isChecked():
            run_task(self, "Préparation de l'instance",
                     lambda p: self.manager.prepare([inst], p, {inst.id: paths.USER_OBS_CONFIG}))

    def edit_instance(self, inst_id: str) -> None:
        inst = next(i for i in self.manager.instances if i.id == inst_id)
        dlg = InstanceDialog(self.manager, inst, self)
        if dlg.exec():
            self.manager.update_instance(dlg.result_definition())

    def delete_instance(self, inst_id: str) -> None:
        inst = next(i for i in self.manager.instances if i.id == inst_id)
        ctrl = self.manager.controller(inst_id)
        if ctrl.running:
            QMessageBox.information(self, APP_NAME, f"Éteins d'abord l'instance « {inst.name} ».")
            return
        r = QMessageBox.question(
            self, APP_NAME,
            f"Supprimer l'instance « {inst.name} » ?\n\n"
            f"Ses scènes et réglages sont déplacés dans data\\corbeille (récupérables).\n"
            f"Tes enregistrements vidéo ne sont pas touchés.")
        if r == QMessageBox.StandardButton.Yes:
            self.manager.remove_instance(inst_id)

    # ------------------------------------------------------------------ #
    # Préconfigs
    # ------------------------------------------------------------------ #
    def refresh_presets(self) -> None:
        current = self.preset_combo.currentData() or self.manager.settings.get("current_preset")
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for p in self.manager.list_presets():
            n = len(p.get("instances") or [])
            self.preset_combo.addItem(f"{p.get('name')}  ({n} OBS · {p.get('saved_at', '')})", p["slug"])
        idx = self.preset_combo.findData(current)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        if self.preset_combo.count() == 0:
            self.preset_combo.setPlaceholderText("Aucune préconfig")
        self.preset_combo.blockSignals(False)

    def save_preset(self) -> None:
        if not self.manager.instances:
            QMessageBox.information(self, APP_NAME, "Crée d'abord au moins une instance.")
            return
        presets = {p["slug"]: p for p in self.manager.list_presets()}
        current = presets.get(self.manager.settings.get("current_preset") or "")
        name, ok = QInputDialog.getText(self, "Enregistrer la préconfig",
                                        "Nom de la préconfig (instances, scènes, réglages…) :",
                                        text=current["name"] if current else "")
        name = name.strip()
        if not ok or not name:
            return
        if self.manager.preset_exists(name):
            r = QMessageBox.question(self, APP_NAME, f"La préconfig « {name} » existe déjà. La remplacer ?")
            if r != QMessageBox.StandardButton.Yes:
                return

        def done(slug):
            self.refresh_presets()
            self.preset_combo.setCurrentIndex(self.preset_combo.findData(slug))
            self.statusBar().showMessage(f"Préconfig « {name} » enregistrée.", 6000)

        run_task(self, "Enregistrement de la préconfig", lambda p: self.manager.save_preset(name, p), on_done=done)

    def open_preset(self) -> None:
        slug = self.preset_combo.currentData()
        if not slug:
            return
        meta = next((p for p in self.manager.list_presets() if p["slug"] == slug), None)
        if not meta:
            return
        if self.manager.any_running():
            box = QMessageBox(QMessageBox.Icon.Information, APP_NAME,
                              "Éteins d'abord toutes les instances avant d'ouvrir une préconfig.", parent=self)
            close_btn = box.addButton("Tout éteindre", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is close_btn:
                self.close_all()
            return
        names = "\n• ".join(i["name"] for i in meta.get("instances") or [])
        box = QMessageBox(QMessageBox.Icon.Question, "Ouvrir la préconfig",
                          f"Ouvrir « {meta['name']} » ?\n\n• {names}\n\n"
                          "Les instances actuelles sont remplacées. Elles sont d'abord sauvegardées "
                          "dans la préconfig « Dernière session (auto) ».", parent=self)
        launch_cb = QCheckBox("Allumer les instances après l'ouverture")
        launch_cb.setChecked(True)
        box.setCheckBox(launch_cb)
        ok_btn = box.addButton("Ouvrir", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not ok_btn:
            return
        launch_after = launch_cb.isChecked()

        def done(_r):
            self.manager.rebuild_controllers()
            self.refresh_presets()
            if launch_after:
                self.launch_all()

        run_task(self, f"Ouverture de « {meta['name']} »", lambda p: self.manager.load_preset(slug, p),
                 on_done=done, on_error=lambda m: (self.manager.rebuild_controllers(),
                                                   QMessageBox.critical(self, APP_NAME, m)))

    def delete_preset(self) -> None:
        slug = self.preset_combo.currentData()
        if not slug:
            return
        name = self.preset_combo.currentText().split("  (")[0]
        r = QMessageBox.question(self, APP_NAME, f"Supprimer la préconfig « {name} » ?\n"
                                 "(les instances actuelles ne sont pas touchées)")
        if r == QMessageBox.StandardButton.Yes:
            self.manager.delete_preset(slug)
            self.refresh_presets()

    # ------------------------------------------------------------------ #
    # Paramètres, raccourcis, barre d'état
    # ------------------------------------------------------------------ #
    def open_settings(self) -> None:
        dlg = SettingsDialog(self.manager, self, self)
        dlg.hotkeysChanged.connect(self.apply_hotkeys)
        dlg.exec()
        for card in self.cards.values():   # types d'enregistrement peut-être modifiés
            card.reload_types()
            card.refresh()
        self.refresh_status()

    def apply_hotkeys(self) -> None:
        s = self.manager.settings
        if not s.get("hotkeys_enabled"):
            self.hotkeys.clear()
            self.status_hotkeys.setText("")
            return
        failed = self.hotkeys.set([(s["hotkey_record"], self.toggle_record_all),
                                   (s["hotkey_pause"], self.toggle_pause_all)])
        txt = f"Raccourcis : {s['hotkey_record']} enregistrer · {s['hotkey_pause']} pause"
        if failed:
            txt += f"  (déjà utilisé : {', '.join(failed)})"
        self.status_hotkeys.setText(txt)

    def refresh_status(self) -> None:
        rt = obsfiles.runtime_signature()
        status = self.manager.runtime_status()
        src = self.manager.obs_source()
        if rt:
            txt = f"OBS {rt.get('version')}"
            if status == "outdated":
                txt += "  ·  mise à jour d'OBS disponible pour les instances (Paramètres)"
        elif src:
            txt = f"OBS {paths.file_version(src / paths.OBS_EXE_REL)} détecté"
        else:
            txt = "OBS Studio introuvable"
        self.status_obs.setText(txt)
        insts = self.manager.instances
        ok = sum(1 for i in insts if vcam.is_registered(i.vcam))
        self.status_vcam.setText(f"Caméras virtuelles : {ok}/{len(insts)} installées" if insts else "")

    def watch_vcams(self) -> None:
        """Remet les caméras virtuelles qui ont disparu de Windows : au démarrage, puis chaque minute
        (sinon elles ne revenaient qu'au prochain allumage des instances)."""
        self._vcam_watch = QTimer(self, interval=60_000, timeout=self.repair_vcams)
        self._vcam_watch.start()
        QTimer.singleShot(1500, self.repair_vcams)

    def repair_vcams(self) -> None:
        if self.manager.settings.get("vcam_scope") != vcam.SCOPE_USER or obsfiles.runtime_signature() is None \
                or getattr(self, "_vcam_task", None) is not None:
            return
        colors = {i.vcam: i.color for i in self.manager.instances if not vcam.is_registered(i.vcam)}
        if not colors:
            return

        def done(failed):
            self._vcam_task = None
            if failed and hasattr(self, "_vcam_watch"):
                self._vcam_watch.stop()   # échec (droits, antivirus…) : on ne réessaie pas en boucle
            self.refresh_status()

        task = Task(lambda _p: vcam.install(sorted(colors), vcam.SCOPE_USER, colors), self)
        task.succeeded.connect(done)
        task.failed.connect(lambda _m: done(sorted(colors)))
        task.finished.connect(task.deleteLater)
        self._vcam_task = task
        task.start()

    def quit_for_update(self) -> None:
        """Ferme Multi OBS sans rien demander : les instances continuent de tourner et
        la nouvelle version les reprend au démarrage."""
        self._quitting_for_update = True
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, e: QCloseEvent) -> None:
        running = [c.inst.name for c in self.manager.controllers.values() if c.running]
        if running and not getattr(self, "_quitting_for_update", False):
            choice = self.manager.settings.get("on_close", "ask")
            if choice not in ("keep", "stop"):
                box = QMessageBox(QMessageBox.Icon.Question, APP_NAME,
                                  "Des instances OBS sont encore allumées :\n• " + "\n• ".join(running), parent=self)
                keep = box.addButton("Les laisser tourner", QMessageBox.ButtonRole.AcceptRole)
                close = box.addButton("Tout éteindre", QMessageBox.ButtonRole.DestructiveRole)
                cancel = box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
                remember = QCheckBox("Se souvenir de mon choix (modifiable dans les paramètres)")
                box.setCheckBox(remember)
                box.setDefaultButton(keep)
                box.exec()
                clicked = box.clickedButton()
                if clicked is cancel or clicked is None:
                    e.ignore()
                    return
                choice = "stop" if clicked is close else "keep"
                if remember.isChecked():
                    self.manager.settings["on_close"] = choice
                    self.manager.save()
            if choice == "stop":
                self.close_all()
        self.hotkeys.clear()
        self.manager.shutdown()
        e.accept()
