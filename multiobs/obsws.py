"""Client obs-websocket v5 minimal, intégré à la boucle d'événements Qt.

Deux encodages : JSON (connexion principale, petits messages) et MessagePack
(connexion d'aperçu : les captures arrivent en binaire, sans conversion de texte).
"""
import base64
import hashlib
import json
from typing import Callable

from PySide6.QtCore import QByteArray, QObject, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket, QNetworkRequest
from PySide6.QtWebSockets import QWebSocket, QWebSocketHandshakeOptions

from . import msgpack_lite

EV_GENERAL = 1 << 0
EV_CONFIG = 1 << 1
EV_SCENES = 1 << 2
EV_INPUTS = 1 << 3
EV_OUTPUTS = 1 << 6
EV_INPUT_VOLUME_METERS = 1 << 16
SUBSCRIPTIONS = EV_GENERAL | EV_CONFIG | EV_SCENES | EV_INPUTS | EV_OUTPUTS | EV_INPUT_VOLUME_METERS

Callback = Callable[[bool, dict, dict], None]


def _auth(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


class ObsWs(QObject):
    identified = Signal()
    closed = Signal()
    event = Signal(str, dict)

    def __init__(self, port: int, password: str, parent=None, subscriptions: int = SUBSCRIPTIONS,
                 binary: bool = False):
        super().__init__(parent)
        self.port = port
        self.password = password
        self.subscriptions = subscriptions
        self.binary = binary
        self.ready = False
        self._pending: dict[str, Callback | None] = {}
        self._next = 0
        self.ws = QWebSocket("", parent=self)
        if binary:
            self.ws.binaryMessageReceived.connect(self._on_binary)
        else:
            self.ws.textMessageReceived.connect(self._on_text)
        self.ws.disconnected.connect(self._on_disconnected)

    # ------------------------------------------------------------------ #
    def open(self) -> None:
        if self.ws.state() != QAbstractSocket.SocketState.UnconnectedState:
            return
        url = QUrl(f"ws://127.0.0.1:{self.port}")
        if self.binary:
            opts = QWebSocketHandshakeOptions()
            opts.setSubprotocols(["obswebsocket.msgpack"])
            self.ws.open(QNetworkRequest(url), opts)
        else:
            self.ws.open(url)

    def close(self) -> None:
        self.ws.abort()

    @property
    def connecting(self) -> bool:
        return self.ws.state() != QAbstractSocket.SocketState.UnconnectedState and not self.ready

    def call(self, request_type: str, data: dict | None = None, cb: Callback | None = None) -> None:
        if not self.ready:
            if cb:
                cb(False, {}, {"comment": "non connecté"})
            return
        self._next += 1
        rid = str(self._next)
        self._pending[rid] = cb
        d = {"requestType": request_type, "requestId": rid}
        if data:
            d["requestData"] = data
        self._send(6, d)

    # ------------------------------------------------------------------ #
    def _send(self, op: int, d: dict) -> None:
        msg = {"op": op, "d": d}
        if self.binary:
            self.ws.sendBinaryMessage(QByteArray(msgpack_lite.pack(msg)))
        else:
            self.ws.sendTextMessage(json.dumps(msg))

    def _on_text(self, text: str) -> None:
        try:
            msg = json.loads(text)
        except ValueError:
            return
        self._dispatch(msg)

    def _on_binary(self, data: QByteArray) -> None:
        # Les grosses chaînes (image) restent des memoryview sur ce tampon : elles ne
        # sont valables que pendant ce traitement, qui est synchrone.
        try:
            msg = msgpack_lite.unpack(data)
        except (ValueError, IndexError, TypeError):
            return
        if isinstance(msg, dict):
            self._dispatch(msg)

    def _dispatch(self, msg: dict) -> None:
        op, d = msg.get("op"), msg.get("d") or {}
        if op == 0:  # Hello
            ident = {"rpcVersion": 1, "eventSubscriptions": self.subscriptions}
            auth = d.get("authentication")
            if auth:
                ident["authentication"] = _auth(self.password, auth["salt"], auth["challenge"])
            self._send(1, ident)
        elif op == 2:  # Identified
            self.ready = True
            self.identified.emit()
        elif op == 5:  # Event
            self.event.emit(d.get("eventType", ""), d.get("eventData") or {})
        elif op == 7:  # RequestResponse
            cb = self._pending.pop(d.get("requestId"), None)
            if cb:
                status = d.get("requestStatus") or {}
                cb(bool(status.get("result")), d.get("responseData") or {}, status)

    def _on_disconnected(self) -> None:
        was_ready = self.ready
        self.ready = False
        pending, self._pending = self._pending, {}
        for cb in pending.values():
            if cb:
                cb(False, {}, {"comment": "déconnecté"})
        if was_ready:
            self.closed.emit()
