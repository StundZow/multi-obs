"use strict";
// Client WebSocket minimal (RFC 6455) : le Node 20 du logiciel Stream Deck n'en a pas sans option,
// et le plugin se passe de toute dépendance. Sert pour le Stream Deck et pour Multi OBS (127.0.0.1).
const crypto = require("crypto");
const net = require("net");
const { EventEmitter } = require("events");

const GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

class WebSocketClient extends EventEmitter {
  constructor(port, host = "127.0.0.1") {
    super();
    this.port = port;
    this.host = host;
    this.socket = null;
    this.open = false;
    this.closed = false;
    this._buf = Buffer.alloc(0);
    this._handshake = true;
    this._fragments = [];
    this._fragOpcode = 0;
  }

  connect(timeoutMs = 3000) {
    const key = crypto.randomBytes(16).toString("base64");
    this._expected = crypto.createHash("sha1").update(key + GUID).digest("base64");
    const s = (this.socket = net.connect({ port: this.port, host: this.host }));
    s.setNoDelay(true);
    s.setTimeout(timeoutMs, () => {
      if (!this.open) this._fail(new Error("délai dépassé"));
    });
    s.on("connect", () => {
      s.write(
        `GET / HTTP/1.1\r\nHost: ${this.host}:${this.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n` +
          `Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`
      );
    });
    s.on("data", (d) => this._onData(d));
    s.on("error", (e) => this._fail(e));
    s.on("close", () => this._finish());
    return this;
  }

  send(text) {
    return this.open && this._frame(0x1, Buffer.from(text, "utf8"));
  }

  close() {
    if (this.open) this._frame(0x8, Buffer.from([0x03, 0xe8]));
    this.open = false;
    if (this.socket) {
      this.socket.end();
      setTimeout(() => this.socket.destroy(), 1000).unref();
    }
  }

  _onData(d) {
    this._buf = this._buf.length ? Buffer.concat([this._buf, d]) : d;
    if (this._handshake) {
      const end = this._buf.indexOf("\r\n\r\n");
      if (end < 0) {
        if (this._buf.length > 16384) this._fail(new Error("réponse invalide"));
        return;
      }
      const head = this._buf.subarray(0, end).toString("latin1");
      this._buf = this._buf.subarray(end + 4);
      const accept = /sec-websocket-accept:\s*(\S+)/i.exec(head);
      if (!/^HTTP\/1\.1 101/.test(head) || !accept || accept[1] !== this._expected) {
        this._fail(new Error("connexion refusée"));
        return;
      }
      this._handshake = false;
      this.open = true;
      this.socket.setTimeout(0);
      this.emit("open");
    }
    this._parse();
  }

  _parse() {
    while (this._buf.length >= 2) {
      const b0 = this._buf[0];
      const b1 = this._buf[1];
      let len = b1 & 0x7f;
      let off = 2;
      if (len === 126) {
        if (this._buf.length < 4) return;
        len = this._buf.readUInt16BE(2);
        off = 4;
      } else if (len === 127) {
        if (this._buf.length < 10) return;
        len = Number(this._buf.readBigUInt64BE(2));
        off = 10;
      }
      let mask = null;
      if (b1 & 0x80) {
        if (this._buf.length < off + 4) return;
        mask = this._buf.subarray(off, off + 4);
        off += 4;
      }
      if (this._buf.length < off + len) return;
      const payload = Buffer.from(this._buf.subarray(off, off + len));
      if (mask) for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i & 3];
      this._buf = this._buf.subarray(off + len);
      const opcode = b0 & 0x0f;
      if (opcode === 0x8) {
        // fermeture : on répond puis on coupe
        this._frame(0x8, payload.subarray(0, 2));
        this.open = false;
        this.socket.end();
        return;
      }
      if (opcode === 0x9) {
        this._frame(0xa, payload);
        continue;
      }
      if (opcode === 0x1 || opcode === 0x2) {
        this._fragOpcode = opcode;
        this._fragments = [payload];
      } else if (opcode === 0x0) {
        this._fragments.push(payload);
      } else {
        continue;
      }
      if (b0 & 0x80) {
        const data = Buffer.concat(this._fragments);
        this._fragments = [];
        if (this._fragOpcode === 0x1) this.emit("message", data.toString("utf8"));
      }
    }
  }

  _frame(opcode, payload) {
    if (!this.socket || this.socket.destroyed || !this.socket.writable) return false;
    const len = payload.length;
    let header;
    if (len < 126) {
      header = Buffer.alloc(2);
      header[1] = 0x80 | len;
    } else if (len < 65536) {
      header = Buffer.alloc(4);
      header[1] = 0x80 | 126;
      header.writeUInt16BE(len, 2);
    } else {
      header = Buffer.alloc(10);
      header[1] = 0x80 | 127;
      header.writeBigUInt64BE(BigInt(len), 2);
    }
    header[0] = 0x80 | opcode;
    const mask = crypto.randomBytes(4);
    const body = Buffer.from(payload);
    for (let i = 0; i < body.length; i++) body[i] ^= mask[i & 3];
    this.socket.write(Buffer.concat([header, mask, body]));
    return true;
  }

  _fail(err) {
    if (this.listenerCount("error")) this.emit("error", err);
    if (this.socket) this.socket.destroy();
  }

  _finish() {
    if (this.closed) return;
    this.closed = true;
    this.open = false;
    this.emit("close");
  }
}

module.exports = { WebSocketClient };
