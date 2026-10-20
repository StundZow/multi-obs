"""Pilotage d'une instance : processus OBS, connexion WebSocket, état, aperçu et audio."""
import math
import os
import shutil
import subprocess
import time
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage

from . import taskbar, winapi
from .instance_config import InstanceDef, record_directory
from .obsws import ObsWs
from .preview import PreviewChannel

LAUNCH_ARGS = ["--portable", "--multi", "--disable-updater",
               "--disable-shutdown-check", "--disable-missing-files-check"]
SILENCE_DB = -50.0
SILENCE_SECONDS = 10
METER_FLOOR_DB = -60.0
LOW_DISK_BYTES = 10 * 1024 ** 3


def _db(mul: float) -> float:
    return 20 * math.log10(mul) if mul > 0 else -math.inf


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


class InstanceController(QObject):
    changed = Signal()
    preview = Signal(QImage)
    meters = Signal()
    defaultAudioAdded = Signal(str)
    actionFailed = Signal(str)
    obsReady = Signal(str)
    previewFps = Signal(float)

    def __init__(self, inst: InstanceDef, preview_fps: int = 30, preview_divisor: int = 2,
                 preview_background_fps: int = 5, parent=None):
        super().__init__(parent)
        self.inst = inst
        self.proc: psutil.Process | None = None
        self.ws: ObsWs | None = None
        self.record_dir = ""
        self.disk_free = 0
        self.disk_total = 0
        self._disk_tick = 0
        self._rate_samples: list[tuple[float, int]] = []
        self._failure = ""
        self._failure_until = 0.0
        self.obs_dialogs: list[str] = []
        self.pause_blocked = False     # OBS désactive la pause avec ce réglage de sortie
        self._close_after_stop = False
        self.settings: dict = {}
        self._remux_watch: list[dict] = []
        self._remux_timer = QTimer(self, interval=3000, timeout=self._check_remux)
        self.actionFailed.connect(self._remember_failure)
        self._reset_state()
        self._refresh_disk()

        self._poll = QTimer(self, interval=1000, timeout=self._tick)
        self._poll.start()
        self._launch_timer = QTimer(self, interval=250, timeout=self._watch_window)
        self._launch_started = 0.0
        self._want_minimize = False
        self.preview_channel = PreviewChannel(self)
        self.preview_channel.frame.connect(self.preview)
        self.preview_channel.fpsMeasured.connect(self.previewFps)
        self.preview_fps_measured = 0.0
        self.preview_note = ""
        self.previewFps.connect(lambda v: setattr(self, "preview_fps_measured", v))
        self.preview_channel.noteChanged.connect(self._on_preview_note)
        self.preview_channel.configure(preview_fps, preview_divisor, preview_background_fps)
        self.taskbar = taskbar.TaskbarDecor()
        self._hwnd = None
        self._make_ws()
        self._adopt_running()

    # ------------------------------------------------------------------ #
    # État
    # ------------------------------------------------------------------ #
    def _reset_state(self) -> None:
        self.obs_version = ""
        self.scene = ""
        self.recording = False
        self.paused = False
        self.streaming = False
        self.vcam_on = False
        self.rec_time = ""
        self.rec_bytes = 0
        self.rec_path = ""
        self.stream_time = ""
        self.fps = 0.0
        self.cpu = 0.0
        self.memory = 0.0
        self.render_skipped = 0
        self.output_skipped = 0
        self._stats_seen = False
        self.levels: dict[str, list[tuple[float, float]]] = {}
        self.meter_order: list[str] = []
        self.mutes: dict[str, bool] = {}
        self._mute_pending: set[str] = set()
        self._last_sound = time.monotonic()
        self._drop_warning_until = 0.0
        self._drop_warning = ""
        self.closing = False
        self.obs_ready = False

    @property
    def running(self) -> bool:
        return self.proc is not None

    @property
    def connected(self) -> bool:
        return bool(self.ws and self.ws.ready and self.obs_ready)

    @property
    def status(self) -> str:
        if not self.running:
            return "stopped"
        if not self.connected:
            return "starting"
        return "ready"

    def _remember_failure(self, message: str) -> None:
        self._failure = message.split(" : ", 1)[-1]
        self._failure_until = time.monotonic() + 15
        self.changed.emit()

    def bytes_per_second(self) -> float:
        s = self._rate_samples
        if not self.recording or self.paused or len(s) < 3 or s[-1][0] - s[0][0] < 4:
            return 0.0
        return max(0.0, (s[-1][1] - s[0][1]) / (s[-1][0] - s[0][0]))

    def warnings(self) -> list[str]:
        out = []
        if not self.connected:
            return out
        now = time.monotonic()
        if self.obs_dialogs:
            out.append(f"OBS attend une réponse : « {self.obs_dialogs[0]} » — clique « Voir OBS »")
        if self.pause_blocked and self.recording:
            out.append("Pause impossible avec la qualité « Identique au stream » (clic sur Pause pour corriger)")
        if now < self._failure_until:
            out.append(self._failure)
        if self.disk_total and self.disk_free < LOW_DISK_BYTES and (self.recording or self.streaming):
            out.append("Disque presque plein")
        if now < self._drop_warning_until and self._drop_warning:
            out.append(self._drop_warning)
        active = (self.recording and not self.paused) or self.streaming
        if active:
            if not self.meter_order:
                out.append("Aucune source audio")
            elif all(self.mutes.get(n, False) for n in self.meter_order):
                out.append("Toutes les sources audio sont coupées")
            elif now - self._last_sound > SILENCE_SECONDS:
                out.append(f"Pas de son depuis {int(now - self._last_sound)} s")
        return out

    # ------------------------------------------------------------------ #
    # Processus
    # ------------------------------------------------------------------ #
    def _adopt_running(self) -> None:
        exe = str(self.inst.exe)
        for p in psutil.process_iter(["name", "exe"]):
            try:
                if p.info["name"] and p.info["name"].lower() == "obs64.exe" and p.info["exe"] \
                        and _same_path(p.info["exe"], exe):
                    self.proc = p
                    self.ws.open()
                    self.preview_channel.activate(self.inst.port, self.inst.password)
                    return
            except (psutil.Error, OSError):
                continue

    def start(self) -> None:
        if self.running:
            return
        exe = self.inst.exe
        p = subprocess.Popen([str(exe), *LAUNCH_ARGS], cwd=str(exe.parent), close_fds=True,
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        self.proc = psutil.Process(p.pid)
        self._reset_state()
        self._want_minimize = self.inst.start_minimized
        self._launch_started = time.monotonic()
        self._launch_timer.start()
        self.preview_channel.activate(self.inst.port, self.inst.password)
        self.changed.emit()

    def shutdown_gracefully(self) -> bool:
        """Éteint l'instance. Si elle enregistre : arrête d'abord le rec et laisse OBS finir la
        conversion MP4 avant de le fermer (sinon le fichier reste en MKV)."""
        if not self.proc:
            return True
        if self.recording and self.connected:
            self.closing = True
            self._close_after_stop = True
            self.stop_record()
            # Filet de sécurité : si l'arrêt n'aboutit pas, on ferme quand même.
            QTimer.singleShot(45000, lambda: self._close_after_stop and self.request_close())
            self.changed.emit()
            return True
        return self.request_close()

    def _close_when_converted(self, mkv_path: str) -> None:
        mp4 = Path(mkv_path).with_suffix(".mp4") if mkv_path.lower().endswith(".mkv") else None
        if not (mp4 and self.settings.get("auto_remux", True)):
            QTimer.singleShot(300, self.request_close)
            return
        state = {"since": time.monotonic(), "size": -1, "stable": 0}

        def check():
            try:
                size = mp4.stat().st_size
            except OSError:
                size = -1
            state["stable"] = state["stable"] + 1 if size > 0 and size == state["size"] else 0
            state["size"] = size
            if state["stable"] >= 2 or time.monotonic() - state["since"] > 30:
                timer.stop()
                self.request_close()
        timer = QTimer(self, interval=500, timeout=check)
        timer.start()

    def request_close(self) -> bool:
        """Demande à OBS de se fermer (comme le bouton X). False si aucune fenêtre trouvée."""
        if not self.proc:
            return True
        hwnd = winapi.main_window(self.proc.pid, visible_only=False)
        if not hwnd:
            return False
        self.closing = True
        winapi.request_close(hwnd)
        self.changed.emit()
        return True

    def kill(self) -> None:
        if self.proc:
            try:
                self.proc.kill()
            except psutil.Error:
                pass

    def show_window(self) -> bool:
        if not self.proc:
            return False
        hwnd = winapi.main_window(self.proc.pid)
        if hwnd:
            winapi.bring_to_front(hwnd)
            return True
        return False

    def minimize_window(self) -> None:
        if self.proc:
            hwnd = winapi.main_window(self.proc.pid)
            if hwnd:
                winapi.minimize(hwnd)

    def _watch_window(self) -> None:
        if not self.proc or time.monotonic() - self._launch_started > 60:
            self._launch_timer.stop()
            return
        hwnd = winapi.main_window(self.proc.pid)
        if hwnd:
            if self._want_minimize:
                winapi.minimize(hwnd)
            self._launch_timer.stop()

    def _on_exit(self) -> None:
        self.proc = None
        self._close_after_stop = False
        self._hwnd = None
        self.taskbar.hwnd = None
        self.record_dir = ""
        self._rate_samples.clear()
        self._launch_timer.stop()
        if self.ws:
            self.ws.close()
        self.preview_channel.deactivate()
        self._reset_state()
        self.preview.emit(QImage())
        self.meters.emit()
        self.changed.emit()

    # ------------------------------------------------------------------ #
    # WebSocket
    # ------------------------------------------------------------------ #
    def _make_ws(self) -> None:
        if self.ws:
            self.ws.close()
            self.ws.deleteLater()
        self.ws = ObsWs(self.inst.port, self.inst.password, self)
        self.ws.identified.connect(self._on_identified)
        self.ws.closed.connect(self._on_ws_closed)
        self.ws.event.connect(self._on_event)

    def update_definition(self, inst: InstanceDef) -> None:
        reconnect = (inst.port, inst.password) != (self.inst.port, self.inst.password)
        self.inst = inst
        if reconnect:
            self._make_ws()
            if self.running:
                self.preview_channel.activate(inst.port, inst.password)
        self.changed.emit()

    def set_preview(self, fps: int, divisor: int, background_fps: int) -> None:
        self.preview_channel.configure(fps, divisor, background_fps)

    def set_preview_visible(self, visible: bool) -> None:
        self.preview_channel.set_visible(visible)

    def set_preview_state(self, state: str) -> None:
        self.preview_channel.set_app_state(state)

    def _on_preview_note(self, note: str) -> None:
        self.preview_note = note
        self.changed.emit()

    def set_preview_target(self, w: int, h: int) -> None:
        self.preview_channel.set_target(w, h)

    def shutdown(self) -> None:
        """Arrête le thread d'aperçu et remet l'icône d'origine de la fenêtre OBS."""
        try:
            self.taskbar.restore()
        except Exception:
            pass
        self.preview_channel.shutdown()

    def _decorate_window(self) -> None:
        """Titre « OBS Blue — Caméra » et logo OBS coloré dans la barre des tâches."""
        if not self.proc:
            return
        if not self.settings.get("taskbar_rename", True):
            if self.taskbar.hwnd:
                self.taskbar.restore()
            return
        try:
            if not (self._hwnd and taskbar.user32.IsWindow(self._hwnd)):
                self._hwnd = winapi.main_window(self.proc.pid)
            if self._hwnd:
                self.taskbar.apply(self._hwnd, self.inst.name, self.inst.color)
        except Exception:
            self._hwnd = None

    def _refresh_disk(self) -> None:
        folder = self.record_dir or str(record_directory(self.inst))
        target = Path(folder)
        while not target.exists() and target.parent != target:
            target = target.parent
        try:
            usage = shutil.disk_usage(target)
            self.disk_free, self.disk_total = usage.free, usage.total
        except OSError:
            self.disk_free = self.disk_total = 0
        self.disk_path = folder

    def _refresh_record_dir(self) -> None:
        def cb(ok, d, _s):
            if ok and d.get("recordDirectory"):
                self.record_dir = d["recordDirectory"]
                self._refresh_disk()
        self.ws.call("GetRecordDirectory", cb=cb)

    def _tick(self) -> None:
        self._disk_tick += 1
        if self._disk_tick % 5 == 0:
            self._refresh_disk()
        if self.connected and self._disk_tick % 15 == 0:
            self._refresh_record_dir()
            self._check_pause_support()   # l'utilisateur a pu changer ses réglages dans OBS
        if self.proc:
            try:
                alive = self.proc.is_running() and self.proc.status() != psutil.STATUS_ZOMBIE
            except psutil.Error:
                alive = False
            if not alive:
                self._on_exit()
                return
            if not self.ws.ready and not self.ws.connecting:
                self.ws.open()
        if self.connected:
            self.ws.call("GetStats", cb=self._on_stats)
            self.ws.call("GetRecordStatus", cb=self._on_record_status)
            self.ws.call("GetStreamStatus", cb=self._on_stream_status)
            self._decorate_window()
        if self.proc and self._disk_tick % 2 == 0:
            try:
                self.obs_dialogs = winapi.pending_dialogs(self.proc.pid)
            except Exception:
                self.obs_dialogs = []
        elif not self.proc:
            self.obs_dialogs = []
        self.changed.emit()

    def _on_identified(self) -> None:
        # Le WebSocket répond avant qu'OBS ait fini de charger (erreur 207) : on attend.
        def cb(ok, d, status):
            if not self.ws.ready:
                return
            if not ok:
                QTimer.singleShot(400, self._on_identified)
                return
            self.obs_ready = True
            self.scene = d.get("sceneName") or d.get("currentProgramSceneName", "")
            self._on_obs_ready()
        self.ws.call("GetCurrentProgramScene", cb=cb)

    def _on_obs_ready(self) -> None:
        self._refresh_record_dir()
        self._check_pause_support()
        self.obsReady.emit(self.inst.id)
        self.ws.call("GetVersion", cb=lambda ok, d, s: setattr(self, "obs_version", d.get("obsVersion", "")))
        if self.inst.needs_default_audio and self.scene:
            self._add_default_audio()
        self.ws.call("GetVirtualCamStatus", cb=self._on_vcam_status)
        self.ws.call("GetRecordStatus", cb=self._on_record_status)
        self.ws.call("GetStreamStatus", cb=self._on_stream_status)
        self.changed.emit()

    def _add_default_audio(self) -> None:
        # Une instance vierge n'a aucune source audio (pas d'assistant de premier lancement).
        for name, kind in (("Audio du bureau", "wasapi_output_capture"), ("Mic/Aux", "wasapi_input_capture")):
            self.ws.call("CreateInput", {"sceneName": self.scene, "inputName": name, "inputKind": kind,
                                         "inputSettings": {"device_id": "default"}})
        self.defaultAudioAdded.emit(self.inst.id)

    def _on_ws_closed(self) -> None:
        self.obs_ready = False
        self.levels.clear()
        self.meter_order.clear()
        self.meters.emit()
        self.changed.emit()

    def _refresh_scene(self) -> None:
        def cb(ok, d, _s):
            if ok:
                self.scene = d.get("sceneName") or d.get("currentProgramSceneName", "")
                self.changed.emit()
        self.ws.call("GetCurrentProgramScene", cb=cb)

    def _on_stats(self, ok: bool, d: dict, _s: dict) -> None:
        if not ok:
            return
        self.fps = d.get("activeFps", 0.0)
        self.cpu = d.get("cpuUsage", 0.0)
        self.memory = d.get("memoryUsage", 0.0)
        rs, os_ = d.get("renderSkippedFrames", 0) or 0, d.get("outputSkippedFrames", 0) or 0
        dropped = False
        if self._stats_seen and rs > self.render_skipped:
            self._drop_warning = f"Images perdues au rendu (+{rs - self.render_skipped})"
            self._drop_warning_until = time.monotonic() + 8
            dropped = True
        if self._stats_seen and os_ > self.output_skipped:
            self._drop_warning = f"Images perdues à l'encodage (+{os_ - self.output_skipped})"
            self._drop_warning_until = time.monotonic() + 8
            dropped = True
        if dropped:
            # OBS est chargé : l'aperçu se fait discret pour protéger l'enregistrement.
            self.preview_channel.throttle()
        self.render_skipped, self.output_skipped = rs, os_
        self._stats_seen = True

    def _on_record_status(self, ok: bool, d: dict, _s: dict) -> None:
        if ok:
            self.recording = d.get("outputActive", False)
            self.paused = d.get("outputPaused", False)
            self.rec_time = (d.get("outputTimecode") or "")[:8]
            self.rec_bytes = d.get("outputBytes", 0)
            if self.recording and not self.paused:
                self._rate_samples.append((time.monotonic(), self.rec_bytes))
                self._rate_samples = self._rate_samples[-12:]
            else:
                self._rate_samples.clear()

    def _on_stream_status(self, ok: bool, d: dict, _s: dict) -> None:
        if ok:
            self.streaming = d.get("outputActive", False)
            self.stream_time = (d.get("outputTimecode") or "")[:8]

    def _on_vcam_status(self, ok: bool, d: dict, _s: dict) -> None:
        if ok:
            self.vcam_on = d.get("outputActive", False)
            self.changed.emit()

    def _on_event(self, etype: str, d: dict) -> None:
        if not self.obs_ready:
            return
        if etype == "InputVolumeMeters":
            self._on_meters(d.get("inputs") or [])
            return
        if etype == "RecordStateChanged":
            state = d.get("outputState", "")
            # obs-websocket annonce « outputActive: false » pendant une PAUSE : l'enregistrement
            # continue pourtant. On se fie donc à l'état, pas à ce booléen.
            if state.endswith("PAUSED"):
                self.recording, self.paused = True, True
            elif state.endswith(("RESUMED", "STARTED")):
                self.recording, self.paused = True, False
            elif state.endswith("STOPPED"):
                self.recording, self.paused = False, False
            if not self.recording:
                self.rec_time = ""
            if state.endswith("STARTED") and d.get("outputPath"):
                self.rec_path = d["outputPath"]
            if state.endswith("STOPPED"):
                self.rec_path = ""
                self._watch_remux(d.get("outputPath") or "")
                if self._close_after_stop:
                    self._close_after_stop = False
                    self._close_when_converted(d.get("outputPath") or "")
        elif etype == "StreamStateChanged":
            self.streaming = d.get("outputActive", False)
        elif etype == "VirtualcamStateChanged":
            self.vcam_on = d.get("outputActive", False)
        elif etype == "CurrentProgramSceneChanged":
            self.scene = d.get("sceneName", "")
        elif etype in ("CurrentSceneCollectionChanged", "CurrentProfileChanged", "SceneNameChanged"):
            self._refresh_scene()
            self._refresh_record_dir()
            self._check_pause_support()
            self.mutes.clear()
        elif etype == "InputMuteStateChanged":
            self.mutes[d.get("inputName", "")] = d.get("inputMuted", False)
            self.meters.emit()
        elif etype == "InputNameChanged":
            old, new = d.get("oldInputName"), d.get("inputName")
            if old in self.mutes:
                self.mutes[new] = self.mutes.pop(old)
        elif etype == "InputRemoved":
            self.mutes.pop(d.get("inputName", ""), None)
        elif etype == "ExitStarted":
            self.closing = True
        self.changed.emit()

    def _watch_remux(self, path: str) -> None:
        """OBS convertit le MKV en MP4 à l'arrêt ; on met le MKV à la corbeille une fois le MP4 complet."""
        if not path.lower().endswith(".mkv"):
            return
        if not (self.settings.get("auto_remux") and self.settings.get("trash_mkv_after_remux")):
            return
        mkv = Path(path)
        self._remux_watch.append({"mkv": mkv, "mp4": mkv.with_suffix(".mp4"), "since": time.monotonic(),
                                  "size": -1, "stable": 0})
        self._remux_timer.start()

    def _check_remux(self) -> None:
        keep = []
        for w in self._remux_watch:
            if time.monotonic() - w["since"] > 3600 or not w["mkv"].exists():
                continue
            try:
                size = w["mp4"].stat().st_size
                mkv_size = w["mkv"].stat().st_size
            except OSError:
                keep.append(w)
                continue
            w["stable"] = w["stable"] + 1 if size == w["size"] and size > 0 else 0
            w["size"] = size
            # MP4 qui ne grossit plus depuis ~6 s et de taille cohérente : conversion terminée.
            if w["stable"] >= 2 and size >= 0.9 * mkv_size:
                winapi.send_to_recycle_bin(str(w["mkv"]))
            else:
                keep.append(w)
        self._remux_watch = keep
        if not keep:
            self._remux_timer.stop()

    def _on_meters(self, inputs: list) -> None:
        order = []
        levels = {}
        now = time.monotonic()
        for inp in inputs:
            name = inp.get("inputName", "")
            chans = []
            for ch in inp.get("inputLevelsMul") or []:
                if len(ch) >= 2:
                    chans.append((_db(ch[0]), _db(ch[1])))
            if not chans:
                continue
            order.append(name)
            levels[name] = chans
            if name not in self.mutes and name not in self._mute_pending:
                self._request_mute(name)
            if not self.mutes.get(name, False) and max(p for _, p in chans) > SILENCE_DB:
                self._last_sound = now
        self.meter_order, self.levels = order, levels
        self.meters.emit()

    def _request_mute(self, name: str) -> None:
        self._mute_pending.add(name)

        def cb(ok, d, _s):
            self._mute_pending.discard(name)
            if ok:
                self.mutes[name] = d.get("inputMuted", False)
        self.ws.call("GetInputMute", {"inputName": name}, cb)

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _report(self, what: str):
        def cb(ok, _d, status):
            if not ok and self.connected:
                self.actionFailed.emit(f"{self.inst.name} : {what} impossible ({status.get('comment') or 'erreur OBS'})")
            QTimer.singleShot(150, lambda: self.connected and self.ws.call("GetRecordStatus", cb=self._on_record_status))
        return cb

    def start_record(self, attempt: int = 0):
        if not (self.connected and not self.recording):
            return

        def started(ok, d, status):
            # Juste après un arrêt, OBS finalise encore le fichier précédent et refuse : on réessaie.
            if not ok and attempt < 4 and self.connected and not self.recording:
                QTimer.singleShot(600, lambda: self.start_record(attempt + 1))
                return
            self._report("démarrer l'enregistrement")(ok, d, status)

        def cb(ok, d, _s):
            # Dossier absent (disque débranché…) : OBS ouvrirait une fenêtre d'erreur cachée
            # derrière sa fenêtre réduite. On prévient ici à la place.
            folder = (d.get("recordDirectory") or "") if ok else ""
            if folder and not Path(folder).is_dir():
                self.actionFailed.emit(f"{self.inst.name} : dossier d'enregistrement introuvable "
                                       f"({folder}). Change-le dans OBS > Paramètres > Sortie.")
                return
            if self.connected and not self.recording:
                self.ws.call("StartRecord", cb=started)
        self.ws.call("GetRecordDirectory", cb=cb)

    def stop_record(self):
        if self.connected and self.recording:
            self.ws.call("StopRecord", cb=self._report("arrêter l'enregistrement"))

    def pause_record(self):
        if self.connected and self.recording and not self.paused:
            report = self._report("mettre en pause")

            def cb(ok, d, status):
                report(ok, d, status)
                if ok:
                    QTimer.singleShot(800, self._check_paused)
            self.ws.call("PauseRecord", cb=cb)

    def _check_paused(self):
        # OBS répond « OK » même quand il ne met pas en pause : on vérifie.
        def cb(ok, d, _s):
            if ok and d.get("outputActive") and not d.get("outputPaused"):
                if self.pause_blocked:
                    msg = (f"{self.inst.name} : pause impossible avec la qualité « Identique au stream » "
                           "— clic sur Pause sur la carte pour corriger.")
                else:
                    msg = f"{self.inst.name} : OBS n'a pas mis l'enregistrement en pause."
                self.actionFailed.emit(msg)
        if self.connected:
            self.ws.call("GetRecordStatus", cb=cb)

    def _param(self, category: str, name: str, cb) -> None:
        def done(ok, d, _s):
            cb((d.get("parameterValue") or d.get("defaultParameterValue") or "") if ok else None)
        self.ws.call("GetProfileParameter", {"parameterCategory": category, "parameterName": name}, done)

    def _check_pause_support(self) -> None:
        """OBS n'autorise pas la pause quand l'enregistrement réutilise l'encodeur du stream :
        mode simple « Identique au stream », ou mode avancé « Utiliser l'encodeur du stream »."""
        if not self.connected:
            return

        def set_blocked(blocked: bool) -> None:
            if blocked != self.pause_blocked:
                self.pause_blocked = blocked
                self.changed.emit()

        def mode(value):
            if value is None:
                return
            if value.lower() == "advanced":
                self._param("AdvOut", "RecType", lambda rt: (
                    self._param("AdvOut", "FFOutputToFile", lambda f: set_blocked((f or "").lower() == "true"))
                    if (rt or "").lower() == "ffmpeg" else
                    self._param("AdvOut", "RecEncoder", lambda enc: set_blocked((enc or "none").lower() == "none"))))
            else:
                self._param("SimpleOutput", "RecQuality", lambda q: set_blocked((q or "Stream") == "Stream"))
        self._param("Output", "Mode", mode)

    def fix_pause(self) -> bool:
        """Mode simple : qualité « Haute qualité, taille moyenne » (encodeur du stream conservé).
        Prend effet au prochain enregistrement. False si la correction n'est pas automatique."""
        if not self.connected:
            return False

        def apply(mode):
            if (mode or "Simple").lower() == "advanced":
                return

            def with_encoder(stream_enc):
                def rec_encoder(ok, d, _s):
                    # Encodeur d'enregistrement jamais choisi : OBS prendrait x264 (processeur).
                    # On reprend celui du stream (souvent NVENC).
                    explicit = d.get("parameterValue") if ok else None
                    if not explicit and stream_enc:
                        self._set_param("SimpleOutput", "RecEncoder", stream_enc)
                    self._set_param("SimpleOutput", "RecQuality", "Small")
                    QTimer.singleShot(300, self._check_pause_support)
                self.ws.call("GetProfileParameter", {"parameterCategory": "SimpleOutput",
                                                     "parameterName": "RecEncoder"}, rec_encoder)
            self._param("SimpleOutput", "StreamEncoder", with_encoder)
        self._param("Output", "Mode", apply)
        return True

    def _set_param(self, category: str, name: str, value: str) -> None:
        self.ws.call("SetProfileParameter", {"parameterCategory": category, "parameterName": name,
                                             "parameterValue": value})

    def resume_record(self):
        if self.connected and self.recording and self.paused:
            self.ws.call("ResumeRecord", cb=self._report("reprendre"))

    def toggle_record(self):
        self.stop_record() if self.recording else self.start_record()

    def toggle_pause(self):
        self.resume_record() if self.paused else self.pause_record()

    def toggle_stream(self):
        if self.connected:
            self.ws.call("ToggleStream", cb=self._report("live"))

    def toggle_vcam(self):
        if self.connected:
            self.ws.call("ToggleVirtualCam", cb=lambda ok, d, s: self._on_vcam_status(ok, d, s))

    def toggle_mute(self, name: str):
        if self.connected:
            self.ws.call("ToggleInputMute", {"inputName": name})

    def open_record_folder(self):
        def cb(ok, d, _s):
            if ok and d.get("recordDirectory"):
                os.startfile(d["recordDirectory"])
        if self.connected:
            self.ws.call("GetRecordDirectory", cb=cb)
