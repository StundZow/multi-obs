"""Fenêtres : création / modification d'instance, paramètres."""
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog,
                               QKeySequenceEdit, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from .. import applog, naming, obsfiles, paths, theme, vcam
from ..instance_config import InstanceDef
from .tasks import run_task
from .widgets import SwatchButtonPainter

PREVIEW_FPS_CHOICES = [(0, "Désactivé"), (1, "1 image/s"), (5, "5 images/s"), (10, "10 images/s"),
                       (15, "15 images/s"), (30, "30 images/s"), (60, "60 images/s")]
PREVIEW_QUALITY_CHOICES = [(1, "1/1 — pleine résolution"), (2, "1/2"), (4, "1/4"), (8, "1/8")]
PREVIEW_BACKGROUND_CHOICES = [(-1, "Comme au premier plan"), (5, "5 images/s"), (1, "1 image/s"),
                              (0, "En pause")]


def _base_dialog(dlg: QDialog, title: str) -> QVBoxLayout:
    dlg.setWindowTitle(title)
    dlg.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(12)
    return lay


class ColorPicker(QHBoxLayout):
    def __init__(self, current: str):
        super().__init__()
        self.setSpacing(6)
        self.group = QButtonGroup()
        self.buttons = {}
        self.value = current
        for key in theme.ACCENT_ORDER:
            label, _shades = theme.ACCENTS[key]
            b = QPushButton()
            b.setObjectName("swatch")
            b.setToolTip(label)
            b.setCheckable(True)
            b.setStyleSheet("QPushButton#swatch, QPushButton#swatch:checked, QPushButton#swatch:hover"
                            " { background: transparent; border: none; }")
            b.clicked.connect(lambda _=False, k=key: self.select(k))
            self.group.addButton(b)
            self.buttons[key] = b
            self.addWidget(b)
        self.addStretch(1)
        self.select(current)

    def select(self, key: str) -> None:
        self.value = key
        for k, b in self.buttons.items():
            b.setIcon(SwatchButtonPainter.icon(theme.accent(k, 2), k == key))
            b.setIconSize(QSize(26, 26))
            b.setChecked(k == key)


class InstanceDialog(QDialog):
    def __init__(self, manager, inst: InstanceDef | None = None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.inst = inst
        creating = inst is None
        lay = _base_dialog(self, "Nouvelle instance" if creating else f"Paramètres — {inst.name}")
        self.setMinimumWidth(480)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        default_name = f"Instance {len(manager.instances) + 1}"
        self.name = QLineEdit(inst.name if inst else default_name)
        self.name.selectAll()
        form.addRow("Nom", self.name)

        self.colors = ColorPicker(inst.color if inst else manager.next_color())
        form.addRow("Couleur", self.colors)

        self.vcam = QComboBox()
        free = manager.free_vcams(inst.id if inst else None)
        for n in free:
            self.vcam.addItem(obsfiles.vcam_name(n), n)
        if inst:
            self.vcam.setCurrentIndex(max(0, self.vcam.findData(inst.vcam)))
        form.addRow("Caméra virtuelle", self.vcam)

        self.rec_type = QComboBox()
        for key, label in naming.rec_types(manager.settings):
            self.rec_type.addItem(label, key)
        current_type = inst.rec_type if inst else naming.guess_type(self.name.text(), manager.settings)
        if self.rec_type.findData(current_type) < 0:   # type supprimé depuis : on le garde affiché
            self.rec_type.addItem(current_type, current_type)
        self.rec_type.setCurrentIndex(max(0, self.rec_type.findData(current_type)))
        self.rec_type.setToolTip("Utilisé dans le nom des fichiers : NOM-TYPE-VIDÉO-DATE")
        form.addRow("Type d'enregistrement", self.rec_type)
        if not inst:
            self.name.textEdited.connect(lambda t: self.rec_type.setCurrentIndex(
                max(0, self.rec_type.findData(naming.guess_type(t, manager.settings)))))
        lay.addLayout(form)

        self.minimized = QCheckBox("Ouvrir la fenêtre OBS réduite (on la pilote depuis Multi OBS)")
        self.minimized.setChecked(inst.start_minimized if inst else True)
        lay.addWidget(self.minimized)

        self.import_cfg = None
        self.launch = None
        if creating:
            has_obs_cfg = (paths.USER_OBS_CONFIG / "user.ini").exists()
            self.import_cfg = QCheckBox("Partir de mes scènes et réglages OBS actuels")
            self.import_cfg.setToolTip(f"Copie depuis {paths.USER_OBS_CONFIG}\n"
                                       "(ton OBS habituel n'est pas modifié)")
            self.import_cfg.setChecked(has_obs_cfg)
            self.import_cfg.setEnabled(has_obs_cfg)
            lay.addWidget(self.import_cfg)
            self.launch = QCheckBox("Allumer l'instance maintenant")
            self.launch.setChecked(True)
            lay.addWidget(self.launch)
        else:
            hint = QLabel("Les changements de nom, de couleur et de caméra s'appliquent au prochain lancement de l'instance.")
            hint.setWordWrap(True)
            hint.setProperty("muted", True)
            lay.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Créer" if creating else "Enregistrer")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("role", "primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept(self):
        if not self.name.text().strip():
            self.name.setFocus()
            return
        if self.vcam.currentData() is None:
            QMessageBox.warning(self, "Multi OBS", "Plus aucune caméra virtuelle libre (9 maximum).")
            return
        self.accept()

    def result_definition(self) -> InstanceDef:
        name = self.name.text().strip()
        if self.inst:
            from dataclasses import replace
            return replace(self.inst, name=name, color=self.colors.value,
                           vcam=self.vcam.currentData(), start_minimized=self.minimized.isChecked(),
                           rec_type=self.rec_type.currentData())
        d = self.manager.new_definition(name, self.colors.value, self.vcam.currentData())
        d.start_minimized = self.minimized.isChecked()
        d.rec_type = self.rec_type.currentData()
        d.needs_default_audio = not self.import_cfg.isChecked()
        return d


class SettingsDialog(QDialog):
    hotkeysChanged = Signal()

    def __init__(self, manager, main, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.main = main
        lay = _base_dialog(self, "Paramètres de Multi OBS")
        self.setMinimumWidth(620)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        def page(title: str) -> QVBoxLayout:
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(12, 14, 12, 12)
            v.setSpacing(12)
            tabs.addTab(w, title)
            return v

        general, recs, preview, vcams, keys = (page("Général"), page("Enregistrements"), page("Aperçu"),
                                               page("Caméras virtuelles"), page("Raccourcis"))

        # ---- Général : OBS, fenêtre, mises à jour
        g = QGroupBox("OBS Studio")
        gl = QVBoxLayout(g)
        row = QHBoxLayout()
        self.src = QLineEdit(str(manager.obs_source() or ""))
        self.src.setPlaceholderText("Dossier d'installation d'OBS Studio")
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.src, 1)
        row.addWidget(browse)
        gl.addLayout(row)
        self.version = QLabel()
        self.version.setProperty("muted", True)
        self.version.setWordWrap(True)
        gl.addWidget(self.version)
        self.update_btn = QPushButton("Mettre à jour les instances avec cet OBS")
        self.update_btn.setToolTip("À faire après avoir mis à jour ton OBS habituel.\n"
                                   "Les scènes et réglages des instances sont conservés.")
        self.update_btn.clicked.connect(self._update_obs)
        gl.addWidget(self.update_btn, 0, Qt.AlignmentFlag.AlignLeft)
        general.addWidget(g)

        g = QGroupBox("Fenêtre")
        form = QFormLayout(g)
        form.setVerticalSpacing(10)
        self.on_close = QComboBox()
        for v, label in (("ask", "Demander"), ("keep", "Laisser tourner les instances"), ("stop", "Tout éteindre")):
            self.on_close.addItem(label, v)
        self.on_close.setCurrentIndex(max(0, self.on_close.findData(manager.settings.get("on_close", "ask"))))
        form.addRow("À la fermeture de Multi OBS", self.on_close)
        self.taskbar_rename = QCheckBox("Barre des tâches : « OBS Blue — Caméra » avec le logo OBS à la couleur de l'instance")
        self.taskbar_rename.setChecked(bool(manager.settings.get("taskbar_rename", True)))
        form.addRow(self.taskbar_rename)
        general.addWidget(g)

        from .. import APP_VERSION
        g = QGroupBox("Mises à jour")
        row = QHBoxLayout(g)
        self.check_updates = QCheckBox(f"Vérifier au démarrage (version actuelle : {APP_VERSION})")
        self.check_updates.setChecked(bool(manager.settings.get("check_updates", True)))
        row.addWidget(self.check_updates, 1)
        b = QPushButton("Vérifier maintenant")
        b.clicked.connect(lambda: getattr(main, "updater", None) and main.updater.check_now())
        row.addWidget(b)
        general.addWidget(g)
        general.addStretch(1)

        # ---- Enregistrements : nom des fichiers, conversion, types
        g = QGroupBox("Fichiers")
        gl = QVBoxLayout(g)
        form = QFormLayout()
        self.template = QLineEdit(manager.settings.get("filename_template") or naming.DEFAULT_TEMPLATE)
        self.template.setToolTip("{user} = ton nom, {type} = le type de l'instance (cam, ecran, live…), "
                                 "{video} = nom de la vidéo,\n"
                                 "{date} = date du jour, {time} = heure de début (évite d'écraser une prise)")
        self.template.textChanged.connect(self._refresh_template_preview)
        form.addRow("Modèle de nom", self.template)
        self.template_preview = QLabel()
        self.template_preview.setProperty("muted", True)
        form.addRow("", self.template_preview)
        gl.addLayout(form)
        self.auto_remux = QCheckBox("Convertir automatiquement les MKV en MP4 à la fin de l'enregistrement")
        self.auto_remux.setChecked(bool(manager.settings.get("auto_remux", True)))
        self.auto_remux.setToolTip("Conversion sans perte faite par OBS (quelques secondes). Le MKV reste "
                                   "un enregistrement sûr en cas de plantage pendant le rec.")
        gl.addWidget(self.auto_remux)
        self.trash_mkv = QCheckBox("Mettre le MKV à la corbeille une fois le MP4 prêt")
        self.trash_mkv.setChecked(bool(manager.settings.get("trash_mkv_after_remux", False)))
        self.trash_mkv.setToolTip("Seulement si le MP4 est complet (taille vérifiée). Le MKV reste récupérable "
                                  "dans la corbeille Windows.")
        gl.addWidget(self.trash_mkv)
        self.auto_remux.toggled.connect(self.trash_mkv.setEnabled)
        self.trash_mkv.setEnabled(self.auto_remux.isChecked())
        recs.addWidget(g)

        g = QGroupBox("Types d'enregistrement")
        gl = QHBoxLayout(g)
        self.types_list = QListWidget()
        self.types_list.setMinimumHeight(130)
        self.types_list.setToolTip("Chaque instance a un type (menu sur sa carte), utilisé dans le nom des fichiers.")
        for key, label in naming.rec_types(manager.settings):
            self._add_type_item(label, key)
        gl.addWidget(self.types_list, 1)
        col = QVBoxLayout()
        for text, slot in (("Ajouter…", self._type_add), ("Renommer…", self._type_rename),
                           ("Supprimer", self._type_remove), ("Par défaut", self._type_reset)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            col.addWidget(b)
        col.addStretch(1)
        gl.addLayout(col)
        recs.addWidget(g)
        recs.addStretch(1)

        # ---- Aperçu
        g = QGroupBox("Aperçus des instances")
        form = QFormLayout(g)
        form.setVerticalSpacing(10)
        self.fps = QComboBox()
        for v, label in PREVIEW_FPS_CHOICES:
            self.fps.addItem(label, v)
        self.fps.setCurrentIndex(max(0, self.fps.findData(int(manager.settings["preview_fps"]))))
        self.fps.currentIndexChanged.connect(lambda: manager.set_preview(fps=self.fps.currentData()))
        form.addRow("Rafraîchissement", self.fps)
        self.quality = QComboBox()
        for v, label in PREVIEW_QUALITY_CHOICES:
            self.quality.addItem(label, v)
        self.quality.setCurrentIndex(max(0, self.quality.findData(int(manager.settings.get("preview_divisor", 4)))))
        self.quality.currentIndexChanged.connect(lambda: manager.set_preview(divisor=self.quality.currentData()))
        form.addRow("Qualité", self.quality)
        self.bg_fps = QComboBox()
        for v, label in PREVIEW_BACKGROUND_CHOICES:
            self.bg_fps.addItem(label, v)
        self.bg_fps.setCurrentIndex(max(0, self.bg_fps.findData(
            int(manager.settings.get("preview_background_fps", -1)))))
        self.bg_fps.currentIndexChanged.connect(lambda: manager.set_preview(background_fps=self.bg_fps.currentData()))
        self.bg_fps.setToolTip("Quand une autre appli est au premier plan. Fenêtre réduite, session "
                               "verrouillée ou écran éteint : les aperçus sont toujours en pause.")
        form.addRow("Quand Multi OBS est en arrière-plan", self.bg_fps)
        perf = QLabel("Aperçu sans compression, jamais plus de pixels que l'écran n'en affiche. "
                      "Pause automatique quand il ne sert à rien, et ralenti tout seul si OBS perd des "
                      "images. En 1/1 sur un grand aperçu, compte une dizaine d'images/s par instance.")
        perf.setWordWrap(True)
        perf.setProperty("muted", True)
        form.addRow(perf)
        preview.addWidget(g)
        preview.addStretch(1)

        # ---- Caméras virtuelles
        g = QGroupBox("Caméras virtuelles")
        gl = QVBoxLayout(g)
        self.vcam_status = QLabel()
        self.vcam_status.setWordWrap(True)
        gl.addWidget(self.vcam_status)
        info = QLabel("Chaque instance a sa propre caméra « OBS Virtual Camera N », utilisable dans "
                      "Discord, Zoom, le navigateur… ou dans une autre instance (source « Périphérique "
                      "de capture vidéo »). Pense à redémarrer Discord après une première installation.")
        info.setWordWrap(True)
        info.setProperty("muted", True)
        gl.addWidget(info)
        row = QHBoxLayout()
        b = QPushButton("Installer / réparer")
        b.clicked.connect(self._install_vcams)
        row.addWidget(b)
        b = QPushButton("Désinstaller")
        b.clicked.connect(self._uninstall_vcams)
        row.addWidget(b)
        row.addStretch(1)
        gl.addLayout(row)
        vcams.addWidget(g)
        vcams.addStretch(1)

        # ---- Raccourcis
        g = QGroupBox("Raccourcis clavier globaux")
        form = QFormLayout(g)
        form.setVerticalSpacing(10)
        self.hk_enabled = QCheckBox("Activer (ils marchent même si Multi OBS n'est pas au premier plan)")
        self.hk_enabled.setChecked(bool(manager.settings["hotkeys_enabled"]))
        form.addRow(self.hk_enabled)
        self.hk_record = QKeySequenceEdit(QKeySequence(manager.settings["hotkey_record"]))
        self.hk_pause = QKeySequenceEdit(QKeySequence(manager.settings["hotkey_pause"]))
        for w in (self.hk_record, self.hk_pause):
            w.setMaximumSequenceLength(1)
        form.addRow("Tout enregistrer / arrêter", self.hk_record)
        form.addRow("Tout mettre en pause / reprendre", self.hk_pause)
        hint = QLabel("Ils agissent sur les instances liées (Link). Pratique aussi avec un Stream Deck "
                      "(action « Raccourci clavier »).")
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        form.addRow(hint)
        keys.addWidget(g)
        keys.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Fermer")
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._refresh()

    # Types d'enregistrement ---------------------------------------------- #
    def _add_type_item(self, label: str, key: str | None) -> None:
        it = QListWidgetItem(label)
        it.setData(Qt.ItemDataRole.UserRole, key)
        self.types_list.addItem(it)

    def _type_keys(self, skip=None) -> set:
        return {naming.type_key(self.types_list.item(i).text()) for i in range(self.types_list.count())
                if self.types_list.item(i) is not skip}

    def _type_add(self):
        label, ok = QInputDialog.getText(self, "Nouveau type", "Nom du type (ex. Podcast, Face cam…) :")
        label = naming.clean(label)
        if not ok or not label:
            return
        if naming.type_key(label) in self._type_keys():
            QMessageBox.information(self, "Multi OBS", f"Le type « {label} » existe déjà.")
            return
        self._add_type_item(label, None)

    def _type_rename(self):
        it = self.types_list.currentItem()
        if not it:
            return
        label, ok = QInputDialog.getText(self, "Renommer le type", "Nouveau nom :", text=it.text())
        label = naming.clean(label)
        if not ok or not label:
            return
        if naming.type_key(label) in self._type_keys(skip=it):
            QMessageBox.information(self, "Multi OBS", f"Le type « {label} » existe déjà.")
            return
        it.setText(label)

    def _type_remove(self):
        it = self.types_list.currentItem()
        if not it:
            return
        if self.types_list.count() <= 1:
            QMessageBox.information(self, "Multi OBS", "Il faut garder au moins un type.")
            return
        self.types_list.takeItem(self.types_list.row(it))

    def _type_reset(self):
        self.types_list.clear()
        for key, label in naming.DEFAULT_REC_TYPES:
            self._add_type_item(label, key)

    def _save_types(self) -> None:
        types, seen, renamed = [], set(), {}
        for i in range(self.types_list.count()):
            it = self.types_list.item(i)
            label = it.text().strip()
            key = naming.type_key(label)
            if not label or key in seen:
                continue
            seen.add(key)
            types.append([key, label])
            old = it.data(Qt.ItemDataRole.UserRole)
            if old and old != key:
                renamed[old] = key
        self.manager.settings["rec_types"] = types or [list(t) for t in naming.DEFAULT_REC_TYPES]
        for inst in self.manager.instances:   # type renommé : les instances suivent
            if inst.rec_type in renamed:
                inst.rec_type = renamed[inst.rec_type]

    def _refresh_template_preview(self):
        s = self.manager.settings
        ex = naming.preview(self.template.text(), s.get("creator", "") or "Nom", "cam",
                            s.get("video_name", "") or "Vidéo")
        self.template_preview.setText(f"output : {ex}.mp4")

    def _refresh(self):
        self._refresh_template_preview()
        src = Path(self.src.text()) if self.src.text() else None
        src_ver = paths.file_version(src / paths.OBS_EXE_REL) if src else ""
        rt = obsfiles.runtime_signature()
        rt_ver = rt.get("version") if rt else None
        status = self.manager.runtime_status()
        txt = f"OBS installé : {src_ver or 'introuvable'}   ·   Copie utilisée par Multi OBS : {rt_ver or 'pas encore créée'}"
        if status == "outdated":
            txt += "\nTon OBS a été mis à jour : clique sur « Mettre à jour les instances »."
        self.version.setText(txt)
        running = self.manager.any_running()
        self.update_btn.setEnabled(bool(src_ver) and not running)
        if running:
            self.update_btn.setToolTip("Éteins d'abord toutes les instances.")
        lines = []
        for inst in self.manager.instances:
            scope = vcam.registered_scope(inst.vcam)
            ok = vcam.is_registered(inst.vcam)
            state = "installée ✓" if ok else ("à réparer" if scope else "non installée")
            lines.append(f"{obsfiles.vcam_name(inst.vcam)} ({inst.name}) : {state}")
        self.vcam_status.setText("\n".join(lines) or "Aucune instance pour l'instant.")

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier d'OBS Studio", self.src.text())
        if d:
            if not (Path(d) / paths.OBS_EXE_REL).exists():
                QMessageBox.warning(self, "Multi OBS", "Ce dossier ne contient pas bin\\64bit\\obs64.exe.")
                return
            self.src.setText(d)
            self.manager.settings["obs_source"] = d
            self.manager.save()
            self._refresh()

    def _update_obs(self):
        if self.manager.any_running():
            QMessageBox.information(self, "Multi OBS", "Éteins d'abord toutes les instances.")
            return
        run_task(self, "Mise à jour d'OBS", self.manager.update_obs,
                 on_done=lambda _r: (self._refresh(), QMessageBox.information(
                     self, "Multi OBS", "Les instances utilisent maintenant la nouvelle version d'OBS.")))

    def _install_vcams(self):
        indices = sorted({i.vcam for i in self.manager.instances})
        if not indices:
            return
        if obsfiles.runtime_signature() is None:
            QMessageBox.information(self, "Multi OBS", "Lance d'abord une instance une fois.")
            return

        def done(failed):
            self._refresh()
            if failed:
                QMessageBox.warning(self, "Multi OBS", "Échec pour : " + ", ".join(map(str, failed)))
            else:
                QMessageBox.information(self, "Multi OBS", "Caméras virtuelles installées.\n"
                                        "Redémarre les instances et les applis (Discord…) qui doivent les voir.")
        # De nouveau gérées par Multi OBS : réinstallées à l'allumage et si elles disparaissent.
        self.manager.settings["vcam_scope"] = vcam.SCOPE_USER
        self.manager.save()
        applog.log(f"Paramètres : « Installer / réparer » les caméras virtuelles {indices}")
        watch = getattr(self.main, "_vcam_watch", None)
        if watch is not None:
            watch.start(60_000)
        colors = {i.vcam: i.color for i in self.manager.instances}
        run_task(self, "Caméras virtuelles", lambda _p: vcam.install(indices, vcam.SCOPE_USER, colors),
                 on_done=done)

    def _uninstall_vcams(self):
        r = QMessageBox.question(self, "Multi OBS", "Désinstaller toutes les caméras virtuelles de Multi OBS ?\n"
                                 "(la caméra « OBS Virtual Camera » d'OBS n'est pas touchée)\n\n"
                                 "Elles ne reviendront qu'avec « Installer / réparer ».")
        if r == QMessageBox.StandardButton.Yes:
            self.manager.settings["vcam_scope"] = "none"   # sinon réinstallées au prochain allumage
            self.manager.save()
            applog.log("Paramètres : « Désinstaller » les caméras virtuelles")
            vcam.uninstall(list(range(1, obsfiles.MAX_VCAM + 1)))
            self._refresh()

    def done(self, r):
        s = self.manager.settings
        s["hotkeys_enabled"] = self.hk_enabled.isChecked()
        s["hotkey_record"] = self.hk_record.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        s["hotkey_pause"] = self.hk_pause.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        s["auto_remux"] = self.auto_remux.isChecked()
        s["taskbar_rename"] = self.taskbar_rename.isChecked()
        s["on_close"] = self.on_close.currentData()
        s["check_updates"] = self.check_updates.isChecked()
        s["trash_mkv_after_remux"] = self.trash_mkv.isChecked()
        self._save_types()
        self.manager.set_naming(template=self.template.text().strip())  # enregistre + applique
        self.hotkeysChanged.emit()
        super().done(r)
