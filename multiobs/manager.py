"""État global de Multi OBS : instances, réglages, préconfigs."""
import json
import re
import secrets
import shutil
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import naming, obsfiles, paths, theme, vcam
from .controller import InstanceController
from .instance_config import InstanceDef, copy_tree_tolerant, ensure_config

BASE_PORT = 4461
AUTOSAVE_SLUG = "_derniere_session"

DEFAULT_SETTINGS = {
    "obs_source": "",
    "preview_fps": 30,
    "preview_divisor": 2,
    "preview_background_fps": 5,
    "taskbar_rename": True,
    "check_updates": True,
    "skipped_version": "",
    "hotkeys_enabled": True,
    "hotkey_record": "Ctrl+Alt+R",
    "hotkey_pause": "Ctrl+Alt+P",
    "vcam_scope": vcam.SCOPE_USER,
    "current_preset": "",
    "creator": "",
    "video_name": "",
    "filename_template": naming.DEFAULT_TEMPLATE,
    "auto_remux": True,
    "trash_mkv_after_remux": False,
}


def _slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    return s or "preconfig"


class Manager(QObject):
    instancesChanged = Signal()

    def __init__(self):
        super().__init__()
        paths.DATA.mkdir(parents=True, exist_ok=True)
        self.settings = dict(DEFAULT_SETTINGS)
        self.instances: list[InstanceDef] = []
        self._load()
        self.controllers: dict[str, InstanceController] = {}
        for inst in self.instances:
            self._make_controller(inst)

    # ------------------------------------------------------------------ #
    # Persistance
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        try:
            data = json.loads(paths.STATE_FILE.read_text("utf-8"))
        except (OSError, ValueError):
            return
        self.settings.update(data.get("settings") or {})
        self.instances = [InstanceDef.from_dict(d) for d in data.get("instances") or []]

    def save(self) -> None:
        data = {"settings": self.settings, "instances": [i.to_dict() for i in self.instances]}
        tmp = paths.STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
        tmp.replace(paths.STATE_FILE)

    def _make_controller(self, inst: InstanceDef) -> InstanceController:
        c = InstanceController(inst, int(self.settings["preview_fps"]),
                               int(self.settings.get("preview_divisor", 2)),
                               int(self.settings.get("preview_background_fps", 5)), self)
        c.settings = self.settings
        c.defaultAudioAdded.connect(self._on_default_audio_added)
        c.obsReady.connect(lambda inst_id: self.apply_naming(inst_id))
        self.controllers[inst.id] = c
        return c

    def _on_default_audio_added(self, inst_id: str) -> None:
        for inst in self.instances:
            if inst.id == inst_id:
                inst.needs_default_audio = False
        self.save()

    # ------------------------------------------------------------------ #
    # Nom des enregistrements
    # ------------------------------------------------------------------ #
    def filename_format(self, inst: InstanceDef) -> str:
        # Deux instances du même type enregistreraient sous le même nom : on les distingue.
        same_type = sum(1 for i in self.instances if i.rec_type == inst.rec_type)
        suffix = inst.name if same_type > 1 else ""
        return naming.obs_format(self.settings.get("filename_template"), self.settings.get("creator", ""),
                                 inst.rec_type, self.settings.get("video_name", ""), suffix)

    def filename_preview(self, inst: InstanceDef) -> str:
        same_type = sum(1 for i in self.instances if i.rec_type == inst.rec_type)
        return naming.preview(self.settings.get("filename_template"), self.settings.get("creator", ""),
                              inst.rec_type, self.settings.get("video_name", ""),
                              inst.name if same_type > 1 else "")

    def set_naming(self, creator: str | None = None, video: str | None = None,
                   template: str | None = None) -> None:
        if creator is not None:
            self.settings["creator"] = creator
        if video is not None:
            self.settings["video_name"] = video
        if template is not None:
            self.settings["filename_template"] = template or naming.DEFAULT_TEMPLATE
        self.save()
        self.apply_naming()

    def set_rec_type(self, inst_id: str, rec_type: str) -> None:
        for inst in self.instances:
            if inst.id == inst_id:
                inst.rec_type = rec_type
        self.save()
        self.apply_naming()  # les doublons de type changent aussi le nom des autres

    def apply_naming(self, only_id: str | None = None) -> None:
        """Envoie le nom des fichiers et la conversion MP4 aux instances (en direct si ouvertes)."""
        auto_remux = bool(self.settings.get("auto_remux", True))
        for inst in self.instances:
            if only_id and inst.id != only_id:
                continue
            fmt = self.filename_format(inst)
            c = self.controllers.get(inst.id)
            if c and c.connected:
                for cat, name, value in (("Output", "FilenameFormatting", fmt),
                                         ("Video", "AutoRemux", "true" if auto_remux else "false")):
                    c.ws.call("SetProfileParameter", {"parameterCategory": cat, "parameterName": name,
                                                      "parameterValue": value})
            elif c and not c.running and inst.config_dir.exists():
                from .instance_config import apply_profile_output
                apply_profile_output(inst.config_dir, fmt, auto_remux)

    # ------------------------------------------------------------------ #
    # OBS source / copie de référence
    # ------------------------------------------------------------------ #
    def obs_source(self) -> Path | None:
        s = self.settings.get("obs_source")
        if s and (Path(s) / paths.OBS_EXE_REL).exists():
            return Path(s)
        return paths.find_obs_install()

    def runtime_status(self) -> str:
        return obsfiles.runtime_status(self.obs_source())

    def any_running(self) -> bool:
        return any(c.running for c in self.controllers.values())

    # ------------------------------------------------------------------ #
    # Instances
    # ------------------------------------------------------------------ #
    def controller(self, inst_id: str) -> InstanceController:
        return self.controllers[inst_id]

    def free_vcams(self, exclude_id: str | None = None) -> list[int]:
        used = {i.vcam for i in self.instances if i.id != exclude_id}
        return [n for n in range(1, obsfiles.MAX_VCAM + 1) if n not in used]

    def next_color(self) -> str:
        used = {i.color for i in self.instances}
        for c in theme.ACCENT_ORDER:
            if c not in used:
                return c
        return theme.ACCENT_ORDER[len(self.instances) % len(theme.ACCENT_ORDER)]

    def new_definition(self, name: str, color: str, vcam_index: int) -> InstanceDef:
        ids = {i.id for i in self.instances}
        if paths.INSTANCES.exists():
            ids |= {p.name for p in paths.INSTANCES.iterdir()}
        n = 1
        while f"inst{n}" in ids:
            n += 1
        ports = {i.port for i in self.instances}
        port = BASE_PORT
        while port in ports:
            port += 1
        return InstanceDef(id=f"inst{n}", name=name, color=color, vcam=vcam_index,
                           port=port, password=secrets.token_urlsafe(18))

    def add_instance(self, inst: InstanceDef) -> InstanceController:
        self.instances.append(inst)
        self.save()
        c = self._make_controller(inst)
        self.instancesChanged.emit()
        return c

    def update_instance(self, inst: InstanceDef) -> None:
        for idx, old in enumerate(self.instances):
            if old.id == inst.id:
                self.instances[idx] = inst
        self.save()
        self.controllers[inst.id].update_definition(inst)
        if inst.config_dir.exists():
            ensure_config(inst, None, self.filename_format(inst), bool(self.settings.get("auto_remux", True)))
        self.instancesChanged.emit()

    def remove_instance(self, inst_id: str) -> None:
        inst = next(i for i in self.instances if i.id == inst_id)
        c = self.controllers.pop(inst_id)
        c.shutdown()
        c.deleteLater()
        if inst.config_dir.exists():
            paths.TRASH.mkdir(parents=True, exist_ok=True)
            dest = paths.TRASH / f"{inst.name}_{time.strftime('%Y%m%d_%H%M%S')}"
            shutil.move(str(inst.config_dir), str(dest))
        shutil.rmtree(inst.dir, ignore_errors=True)
        self.instances = [i for i in self.instances if i.id != inst_id]
        self.save()
        self.instancesChanged.emit()

    def move_instance(self, inst_id: str, delta: int) -> None:
        idx = next(k for k, i in enumerate(self.instances) if i.id == inst_id)
        new = max(0, min(len(self.instances) - 1, idx + delta))
        if new != idx:
            self.instances.insert(new, self.instances.pop(idx))
            self.save()
            self.instancesChanged.emit()

    # ------------------------------------------------------------------ #
    # Préparation (exécuté dans un thread de travail)
    # ------------------------------------------------------------------ #
    def prepare(self, insts: list[InstanceDef], progress, import_from: dict | None = None,
                force_runtime: bool = False) -> list[int]:
        """Copie OBS si besoin, construit les installations, écrit les configs.

        Renvoie les numéros de caméras virtuelles qui n'ont pas pu être installées.
        """
        src = self.obs_source()
        status = obsfiles.runtime_status(src)
        if status == "missing" or force_runtime:
            if not src:
                raise RuntimeError("OBS Studio est introuvable. Indique son dossier dans les paramètres.")
            obsfiles.sync_runtime(src, progress)
        for inst in insts:
            if not obsfiles.tree_is_current(inst.dir, inst.vcam):
                obsfiles.build_tree(inst.dir, inst.vcam, progress)
            ensure_config(inst, (import_from or {}).get(inst.id), self.filename_format(inst),
                          bool(self.settings.get("auto_remux", True)))
        missing = [i.vcam for i in insts if not vcam.is_registered(i.vcam)]
        if missing and self.settings.get("vcam_scope") == vcam.SCOPE_USER:
            progress(0, 0, "Installation des caméras virtuelles…")
            return vcam.install(sorted(set(missing)), vcam.SCOPE_USER)
        return sorted(set(missing))

    def update_obs(self, progress) -> None:
        """Recopie OBS (après une mise à jour) et reconstruit toutes les instances."""
        src = self.obs_source()
        if not src:
            raise RuntimeError("OBS Studio est introuvable.")
        obsfiles.sync_runtime(src, progress)
        for inst in self.instances:
            obsfiles.build_tree(inst.dir, inst.vcam, progress)
            ensure_config(inst, None, self.filename_format(inst), bool(self.settings.get("auto_remux", True)))
        regs = [i.vcam for i in self.instances if vcam.registered_scope(i.vcam)]
        for n in regs:
            obsfiles.build_vcam_modules(n)

    # ------------------------------------------------------------------ #
    # Préconfigs
    # ------------------------------------------------------------------ #
    def list_presets(self) -> list[dict]:
        out = []
        if not paths.PRESETS.exists():
            return out
        for d in sorted(paths.PRESETS.iterdir()):
            try:
                meta = json.loads((d / "preset.json").read_text("utf-8"))
            except (OSError, ValueError):
                continue
            meta["slug"] = d.name
            out.append(meta)
        out.sort(key=lambda m: (m["slug"] == AUTOSAVE_SLUG, m.get("name", "").lower()))
        return out

    def preset_exists(self, name: str) -> bool:
        return (paths.PRESETS / _slugify(name)).exists()

    def save_preset(self, name: str, progress=None, slug: str | None = None) -> str:
        slug = slug or _slugify(name)
        target = paths.PRESETS / slug
        tmp = paths.PRESETS / (slug + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        (tmp / "configs").mkdir(parents=True)
        for k, inst in enumerate(self.instances):
            if progress:
                progress(k, len(self.instances), f"Sauvegarde de « {inst.name} »…")
            if inst.config_dir.exists():
                copy_tree_tolerant(inst.config_dir, tmp / "configs" / inst.id / "obs-studio")
        meta = {
            "name": name,
            "saved_at": time.strftime("%Y-%m-%d %H:%M"),
            "instances": [i.to_dict() for i in self.instances],
            "naming": {"creator": self.settings.get("creator", ""),
                       "filename_template": self.settings.get("filename_template", naming.DEFAULT_TEMPLATE)},
        }
        (tmp / "preset.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), "utf-8")
        shutil.rmtree(target, ignore_errors=True)
        tmp.rename(target)
        if slug != AUTOSAVE_SLUG:
            self.settings["current_preset"] = slug
            self.save()
        return slug

    def load_preset(self, slug: str, progress) -> None:
        """Remplace les instances actuelles par celles de la préconfig (tout doit être fermé)."""
        src = paths.PRESETS / slug
        meta = json.loads((src / "preset.json").read_text("utf-8"))
        if self.instances and slug != AUTOSAVE_SLUG:
            self.save_preset("Dernière session (auto)", progress, slug=AUTOSAVE_SLUG)
        new_defs = [InstanceDef.from_dict(d) for d in meta.get("instances") or []]
        new_ids = {i.id for i in new_defs}
        for inst in self.instances:
            if inst.id not in new_ids:
                shutil.rmtree(inst.dir, ignore_errors=True)
        for k, inst in enumerate(new_defs):
            progress(k, len(new_defs), f"Restauration de « {inst.name} »…")
            shutil.rmtree(inst.config_dir, ignore_errors=True)
            saved = src / "configs" / inst.id / "obs-studio"
            if saved.exists():
                shutil.copytree(saved, inst.config_dir)
        self.instances = new_defs
        for k, v in (meta.get("naming") or {}).items():
            self.settings[k] = v
        if slug != AUTOSAVE_SLUG:
            self.settings["current_preset"] = slug
        self.save()

    def rebuild_controllers(self) -> None:
        """À appeler dans le thread de l'interface après load_preset."""
        for c in self.controllers.values():
            c.shutdown()
            c.deleteLater()
        self.controllers = {}
        for inst in self.instances:
            self._make_controller(inst)
        self.instancesChanged.emit()

    def delete_preset(self, slug: str) -> None:
        shutil.rmtree(paths.PRESETS / slug, ignore_errors=True)
        if self.settings.get("current_preset") == slug:
            self.settings["current_preset"] = ""
            self.save()

    def set_preview(self, fps: int | None = None, divisor: int | None = None,
                    background_fps: int | None = None) -> None:
        if fps is not None:
            self.settings["preview_fps"] = fps
        if divisor is not None:
            self.settings["preview_divisor"] = divisor
        if background_fps is not None:
            self.settings["preview_background_fps"] = background_fps
        self.save()
        for c in self.controllers.values():
            c.set_preview(int(self.settings["preview_fps"]), int(self.settings["preview_divisor"]),
                          int(self.settings["preview_background_fps"]))

    def set_app_state(self, state: str) -> None:
        """Premier plan / arrière-plan / absent (réduit, verrouillé, écran éteint)."""
        for c in self.controllers.values():
            c.set_preview_state(state)

    def set_preview_hidden(self, inst_id: str, hidden: bool) -> None:
        for inst in self.instances:
            if inst.id == inst_id:
                inst.preview_hidden = hidden
        self.save()

    def shutdown(self) -> None:
        for c in self.controllers.values():
            c.shutdown()
