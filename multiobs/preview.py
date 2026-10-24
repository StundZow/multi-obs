"""Aperçu vidéo d'une instance, dans son propre thread (priorité basse).

Objectif : le moins de ressources possible, côté OBS comme côté Multi OBS.

- Connexion WebSocket dédiée, en binaire (msgpack) : pas de conversion de texte de
  plusieurs Mo, l'image base64 est lue directement dans le tampon reçu.
- Capture sans compression (BMP), à la taille utile seulement : jamais plus de
  1,5 x la taille réellement affichée (le réglage 1/1, 1/2… est un maximum).
- Réduction de qualité faite ici (lissée) puis image prête à copier pour l'affichage.
- Pause complète quand l'aperçu ne sert à rien : fenêtre réduite, carte hors de
  l'écran, aperçu masqué, session verrouillée, écran éteint.
- Cadence réduite quand Multi OBS est en arrière-plan (réglable).
- Image identique à la précédente (écran figé) : ni décodage ni affichage, et la
  cadence ralentit progressivement jusqu'à 2 i/s, puis repart dès que ça bouge.
- Si OBS perd des images, l'aperçu se ralentit tout seul pour protéger l'enregistrement.
- Pas de file d'attente : on ne redemande pas d'image tant que l'interface n'a pas
  affiché la précédente ; une seule requête à la fois, deux seulement si la latence
  l'exige pour tenir la cadence.
"""
import binascii
import math
import time
import zlib

from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from .obsws import EV_CONFIG, EV_SCENES, ObsWs

SUPERSAMPLE = 1.5                # pixels demandés au maximum par pixel affiché
BMP_LIMIT_BYTES = 24_000_000     # au-delà le message dépasserait la limite d'obs-websocket -> PNG
B64_CHUNK = 256 * 1024           # multiple de 4
STATIC_AFTER = 3                 # images identiques avant de ralentir
STATIC_MAX_INTERVAL_MS = 500
THROTTLE_HOLD_S = 30             # durée du ralentissement après une perte d'images dans OBS
UI_ACK_TIMEOUT_S = 0.5

STATE_ACTIVE = "active"          # Multi OBS au premier plan
STATE_BACKGROUND = "background"  # une autre appli est au premier plan
STATE_AWAY = "away"              # réduit, session verrouillée, écran éteint


def _b64decode_chunked(data) -> bytes:
    """Décodage par morceaux : le GIL est relâché entre deux morceaux, l'interface
    n'est donc jamais bloquée longtemps (une image 1/1 fait ~8 Mo de base64)."""
    parts = []
    for i in range(0, len(data), B64_CHUNK):
        parts.append(binascii.a2b_base64(data[i:i + B64_CHUNK]))
        if i and i % (B64_CHUNK * 8) == 0:
            time.sleep(0)
    return b"".join(parts)


class PreviewWorker(QObject):
    frame = Signal(QImage)
    fpsMeasured = Signal(float)
    noteChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self.ws: ObsWs | None = None
        self.port = 0
        self.password = ""
        self.active = False            # instance allumée
        self.obs_ready = False
        # Réglages
        self.fps = 0
        self.divisor = 2
        self.background_fps = 5        # -1 : comme au premier plan, 0 : pause
        # Contexte d'affichage
        self.visible = True
        self.app_state = STATE_ACTIVE
        self.target = QSize(0, 0)
        # OBS
        self.scene = ""
        self.base = (1920, 1080)
        self.canvas_fps = 0.0          # inutile de demander plus d'images que la scène n'en produit
        # Pilotage de la cadence
        self.in_flight = 0
        self.seq = 0
        self.last_seq = 0
        self.rtt = 0.0
        self.last_crc = None
        self.static_count = 0
        self.static_interval = 0
        self.throttle_level = 0
        self.throttle_until = 0.0
        self.ui_pending = False        # écrit aussi par le thread de l'interface (simple booléen)
        self.ui_pending_since = 0.0
        self._interval = 0
        self._period = 0.0             # période exacte des demandes (s) et heure de la prochaine
        self._next_due = 0.0
        self._note = ""
        self._frames = 0
        self._fps_since = time.monotonic()
        self._last_meta_fail = 0.0

    # ------------------------------------------------------------------ #
    # Slots (thread de l'aperçu)
    # ------------------------------------------------------------------ #
    @Slot()
    def init(self) -> None:
        self.tick = QTimer(self, timeout=self._tick, singleShot=True)   # relancé à chaque demande
        self.retry = QTimer(self, interval=1500, timeout=self._retry)
        self.meta = QTimer(self, interval=10000, timeout=self._refresh_meta)
        self.recover = QTimer(self, interval=5000, timeout=self._recover)
        self._reschedule()

    @Slot(int, str)
    def activate(self, port: int, password: str) -> None:
        if self.ws and (port, password) != (self.port, self.password):
            self._drop_ws()
        self.port, self.password = port, password
        self.active = True
        if not self.ws:
            self.ws = ObsWs(port, password, self, subscriptions=EV_SCENES | EV_CONFIG, binary=True)
            self.ws.identified.connect(self._on_identified)
            self.ws.closed.connect(self._on_closed)
            self.ws.event.connect(self._on_event)
        self.retry.start()
        self._retry()
        self._reschedule()

    @Slot()
    def deactivate(self) -> None:
        self.active = False
        self.retry.stop()
        self._drop_ws()
        self._reschedule()
        self.frame.emit(QImage())

    @Slot(int, int, int)
    def configure(self, fps: int, divisor: int, background_fps: int) -> None:
        self.fps = fps
        self.divisor = max(1, divisor)
        self.background_fps = background_fps
        self._reschedule()
        if fps <= 0:
            self.frame.emit(QImage())

    @Slot(int, int)
    def set_target(self, w: int, h: int) -> None:
        if w > 0 and h > 0:
            self.target = QSize(w, h)

    @Slot(bool)
    def set_visible(self, visible: bool) -> None:
        if visible != self.visible:
            self.visible = visible
            self._reschedule()

    @Slot(str)
    def set_app_state(self, state: str) -> None:
        if state != self.app_state:
            self.app_state = state
            self._reschedule()

    @Slot()
    def throttle(self) -> None:
        """OBS a perdu des images : on divise la cadence par 2 (jusqu'à /8) pendant 30 s."""
        if self.effective_fps() <= 0:
            return  # l'aperçu ne tourne pas, il n'y est pour rien
        self.throttle_level = min(3, self.throttle_level + 1)
        self.throttle_until = time.monotonic() + THROTTLE_HOLD_S
        self.recover.start()
        self._reschedule()

    @Slot()
    def shutdown(self) -> None:
        self.active = False
        for t in (self.tick, self.retry, self.meta, self.recover):
            t.stop()
        self._drop_ws()

    # ------------------------------------------------------------------ #
    # Cadence
    # ------------------------------------------------------------------ #
    def effective_fps(self) -> float:
        if not self.active or not self.visible or self.fps <= 0 or self.app_state == STATE_AWAY:
            return 0
        fps = float(self.fps)
        if self.canvas_fps > 0:
            fps = min(fps, self.canvas_fps)
        if self.app_state == STATE_BACKGROUND and self.background_fps >= 0:
            fps = min(fps, self.background_fps)
        if fps > 0 and self.throttle_level:
            fps = max(1.0, fps / (2 ** self.throttle_level))
        return fps

    def _reschedule(self) -> None:
        if not hasattr(self, "tick"):
            return
        fps = self.effective_fps()
        if fps <= 0:
            self.tick.stop()
            self.meta.stop()
            self._interval, self._period = 0, 0.0
        else:
            # Période exacte (16,67 ms à 60 i/s) : arrondie à 16 ms, les demandes allaient plus vite
            # qu'OBS et une sur 25 retombait sur l'image déjà reçue (sautée : à-coup de 33 ms).
            period = 1 / fps
            if self.static_interval:
                period = max(period, self.static_interval / 1000)
            interval = max(1, round(period * 1000))
            if period != self._period or not self.tick.isActive():
                # Minuterie précise seulement quand c'est nécessaire (elle réveille plus souvent).
                self.tick.setTimerType(Qt.TimerType.PreciseTimer if interval < 50
                                       else Qt.TimerType.CoarseTimer)
                self._period = period
                self._next_due = time.monotonic() + period
                self.tick.start(interval)
                self._interval = interval
            if not self.meta.isActive():
                self.meta.start()
        self._update_note()

    def _update_note(self) -> None:
        if not self.active or self.fps <= 0:
            note = ""
        elif self.app_state == STATE_AWAY or not self.visible:
            note = "en pause"
        elif self.throttle_level:
            note = "ralenti : OBS chargé"
        elif self.app_state == STATE_BACKGROUND and 0 <= self.background_fps < self.fps:
            note = "arrière-plan" if self.background_fps else "en pause (arrière-plan)"
        elif self.static_interval:
            note = "image fixe"
        else:
            note = ""
        if note != self._note:
            self._note = note
            self.noteChanged.emit(note)

    def _recover(self) -> None:
        if self.throttle_level and time.monotonic() >= self.throttle_until:
            self.throttle_level -= 1
            self.throttle_until = time.monotonic() + 10
            self._reschedule()
        if not self.throttle_level:
            self.recover.stop()

    # ------------------------------------------------------------------ #
    # Connexion
    # ------------------------------------------------------------------ #
    def _drop_ws(self) -> None:
        if self.ws:
            self.ws.close()
            self.ws.deleteLater()
            self.ws = None
        self.obs_ready = False
        self.in_flight = 0
        self.last_crc = None

    def _retry(self) -> None:
        if self.active and self.ws and not self.ws.ready and not self.ws.connecting:
            self.ws.open()

    def _on_identified(self) -> None:
        def cb(ok, d, _s):
            if not self.ws or not self.ws.ready:
                return
            if not ok:  # OBS encore en chargement
                QTimer.singleShot(400, self._on_identified)
                return
            self.obs_ready = True
            self.scene = d.get("sceneName") or d.get("currentProgramSceneName", "")
            self._refresh_meta()
        self.ws.call("GetCurrentProgramScene", cb=cb)

    def _on_closed(self) -> None:
        self.obs_ready = False
        self.in_flight = 0

    def _on_event(self, etype: str, d: dict) -> None:
        if etype == "CurrentProgramSceneChanged":
            self.scene = d.get("sceneName", "")
            self._wake()
        elif etype in ("CurrentProfileChanged", "CurrentSceneCollectionChanged"):
            QTimer.singleShot(500, self._refresh_meta)
            self._wake()

    def _wake(self) -> None:
        """Quelque chose a changé : on sort tout de suite du mode « image fixe »."""
        if self.static_interval:
            self.static_interval = 0
            self.static_count = 0
            self._reschedule()

    def _refresh_meta(self) -> None:
        if not (self.ws and self.ws.ready and self.obs_ready):
            return

        def video(ok, d, _s):
            if ok and d.get("baseWidth"):
                self.base = (d["baseWidth"], d["baseHeight"])
                num, den = d.get("fpsNumerator") or 0, d.get("fpsDenominator") or 1
                canvas = num / den if den else 0.0
                if abs(canvas - self.canvas_fps) > 0.01:
                    self.canvas_fps = canvas
                    self._reschedule()

        def scene(ok, d, _s):
            if ok:
                self.scene = d.get("sceneName") or d.get("currentProgramSceneName", "") or self.scene
        self.ws.call("GetVideoSettings", cb=video)
        self.ws.call("GetCurrentProgramScene", cb=scene)

    # ------------------------------------------------------------------ #
    # Captures
    # ------------------------------------------------------------------ #
    def _request_size(self) -> tuple[int, int]:
        bw, bh = self.base
        w = bw // self.divisor
        if self.target.width() > 0 and self.target.height() > 0:
            # Taille affichée (pixels physiques) x 1,5 : au-delà, rien de plus n'est visible.
            fit = QSize(bw, bh).scaled(self.target, Qt.AspectRatioMode.KeepAspectRatio)
            w = min(w, math.ceil(fit.width() * SUPERSAMPLE))
        w = max(16, min(w, bw))
        return w, max(16, round(w * bh / bw))

    def _tick(self) -> None:
        if not self._period:   # aperçu arrêté entre-temps
            return
        # Prochaine demande à l'heure exacte (période fractionnaire) ; en retard, on repart de maintenant.
        now = time.monotonic()
        self._next_due = max(self._next_due + self._period, now)
        self.tick.start(max(0, round((self._next_due - now) * 1000)))
        if not (self.active and self.ws and self.ws.ready and self.obs_ready and self.scene):
            return
        if self.ui_pending and now - self.ui_pending_since < UI_ACK_TIMEOUT_S:
            return  # l'interface n'a pas encore affiché la précédente : inutile d'en préparer une autre
        max_in_flight = 2 if self.rtt > 0.8 * self._interval / 1000 else 1
        if self.in_flight >= max_in_flight:
            return
        width, height = self._request_size()
        fmt = "bmp" if width * height * 4 < BMP_LIMIT_BYTES else "png"
        self.in_flight += 1
        self.seq += 1
        seq = self.seq
        sent = now

        def cb(ok, d, _s):
            self.in_flight = max(0, self.in_flight - 1)
            rtt = time.monotonic() - sent
            self.rtt = rtt if not self.rtt else self.rtt * 0.8 + rtt * 0.2
            if not ok:
                if time.monotonic() - self._last_meta_fail > 2:  # scène renommée / supprimée ?
                    self._last_meta_fail = time.monotonic()
                    self._refresh_meta()
                return
            if seq > self.last_seq:
                self.last_seq = seq
                self._deliver(d.get("imageData"))

        self.ws.call("GetSourceScreenshot", {"sourceName": self.scene, "imageFormat": fmt,
                                             "imageWidth": width, "imageHeight": height,
                                             "imageCompressionQuality": -1}, cb)

    def _deliver(self, data) -> None:
        if data is None or len(data) == 0:
            return
        if isinstance(data, str):
            data = memoryview(data.encode("ascii"))
        self._count_frame()
        # Même image que la précédente (rien ne bouge à l'écran) : on s'arrête là.
        crc = zlib.crc32(data)
        if crc == self.last_crc:
            self.static_count += 1
            if self.static_count == 1 and not self.static_interval:
                # Image d'OBS déjà reçue : la demande est tombée juste avant la suivante. On décale les
                # demandes d'une demi-image, loin de ce moment, pour ne pas retomber dessus.
                self._next_due += self._period / 2
            if self.static_count >= STATIC_AFTER:
                base = max(1, int(1000 / max(self.effective_fps(), 1)))
                new = min(STATIC_MAX_INTERVAL_MS, max(base * 2, self.static_interval * 2))
                if new != self.static_interval:
                    self.static_interval = new
                    self._reschedule()
            return
        self.last_crc = crc
        if self.static_count or self.static_interval:
            self.static_count = 0
            if self.static_interval:
                self.static_interval = 0
                self._reschedule()

        head = bytes(data[:64])
        comma = head.find(b",")
        img = QImage.fromData(_b64decode_chunked(data[comma + 1:]))
        if img.isNull():
            return
        if self.target.width() > 0:
            fitted = img.size().scaled(self.target, Qt.AspectRatioMode.KeepAspectRatio)
            if fitted != img.size() and fitted.width() > 0:
                img = img.scaled(fitted, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        if img.format() not in (QImage.Format.Format_RGB32, QImage.Format.Format_ARGB32_Premultiplied):
            img = img.convertToFormat(QImage.Format.Format_RGB32)  # format le plus rapide à afficher
        self.ui_pending = True
        self.ui_pending_since = time.monotonic()
        self.frame.emit(img)

    def _count_frame(self) -> None:
        self._frames += 1
        now = time.monotonic()
        if now - self._fps_since >= 2:
            self.fpsMeasured.emit(self._frames / (now - self._fps_since))
            self._frames, self._fps_since = 0, now


class PreviewChannel(QObject):
    """Côté interface : possède le thread et le worker, expose des méthodes simples."""
    frame = Signal(QImage)
    fpsMeasured = Signal(float)
    noteChanged = Signal(str)
    _activate = Signal(int, str)
    _deactivate = Signal()
    _configure = Signal(int, int, int)
    _target = Signal(int, int)
    _visible = Signal(bool)
    _app_state = Signal(str)
    _throttle = Signal()
    _shutdown = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = QThread()
        self.worker = PreviewWorker()
        self.worker.moveToThread(self._thread)
        self._thread.started.connect(self.worker.init)
        self._activate.connect(self.worker.activate)
        self._deactivate.connect(self.worker.deactivate)
        self._configure.connect(self.worker.configure)
        self._target.connect(self.worker.set_target)
        self._visible.connect(self.worker.set_visible)
        self._app_state.connect(self.worker.set_app_state)
        self._throttle.connect(self.worker.throttle)
        self._shutdown.connect(self.worker.shutdown, Qt.ConnectionType.BlockingQueuedConnection)
        self.worker.frame.connect(self._on_frame)
        self.worker.fpsMeasured.connect(self.fpsMeasured)
        self.worker.noteChanged.connect(self.noteChanged)
        # Priorité basse : OBS et l'interface passent avant l'aperçu.
        self._thread.start(QThread.Priority.LowPriority)

    def _on_frame(self, img: QImage) -> None:
        self.worker.ui_pending = False  # l'interface a reçu l'image : la suivante peut être préparée
        self.frame.emit(img)

    def activate(self, port: int, password: str) -> None:
        self._activate.emit(port, password)

    def deactivate(self) -> None:
        self._deactivate.emit()

    def configure(self, fps: int, divisor: int, background_fps: int) -> None:
        self._configure.emit(fps, divisor, background_fps)

    def set_target(self, w: int, h: int) -> None:
        self._target.emit(w, h)

    def set_visible(self, visible: bool) -> None:
        self._visible.emit(visible)

    def set_app_state(self, state: str) -> None:
        self._app_state.emit(state)

    def throttle(self) -> None:
        self._throttle.emit()

    def shutdown(self) -> None:
        if self._thread.isRunning():
            self._shutdown.emit()
            self._thread.quit()
            self._thread.wait(2000)
