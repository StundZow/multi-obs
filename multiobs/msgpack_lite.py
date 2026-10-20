"""MessagePack minimal (sous-protocole « obswebsocket.msgpack » d'obs-websocket).

Sert à la connexion d'aperçu : les captures arrivent en binaire et la grosse chaîne
base64 de l'image est rendue telle quelle (memoryview, sans copie ni décodage).
"""
import struct

BIG_STR = 64 * 1024  # au-delà, une chaîne est rendue en memoryview au lieu de str


def pack(obj) -> bytes:
    out = bytearray()
    _pack(obj, out)
    return bytes(out)


def _pack(o, out: bytearray) -> None:
    if o is None:
        out.append(0xC0)
    elif o is True:
        out.append(0xC3)
    elif o is False:
        out.append(0xC2)
    elif isinstance(o, int):
        if 0 <= o < 0x80:
            out.append(o)
        elif -32 <= o < 0:
            out.append(o & 0xFF)
        elif 0 <= o <= 0xFFFFFFFF:
            out += b"\xce" + struct.pack(">I", o)
        elif -0x80000000 <= o < 0:
            out += b"\xd2" + struct.pack(">i", o)
        else:
            out += b"\xd3" + struct.pack(">q", o)
    elif isinstance(o, float):
        out += b"\xcb" + struct.pack(">d", o)
    elif isinstance(o, str):
        b = o.encode("utf-8")
        n = len(b)
        if n < 32:
            out.append(0xA0 | n)
        elif n < 0x100:
            out += bytes((0xD9, n))
        elif n < 0x10000:
            out += b"\xda" + struct.pack(">H", n)
        else:
            out += b"\xdb" + struct.pack(">I", n)
        out += b
    elif isinstance(o, (bytes, bytearray)):
        n = len(o)
        out += (bytes((0xC4, n)) if n < 0x100 else b"\xc6" + struct.pack(">I", n)) + o
    elif isinstance(o, (list, tuple)):
        n = len(o)
        out += bytes((0x90 | n,)) if n < 16 else b"\xdd" + struct.pack(">I", n)
        for v in o:
            _pack(v, out)
    elif isinstance(o, dict):
        n = len(o)
        out += bytes((0x80 | n,)) if n < 16 else b"\xdf" + struct.pack(">I", n)
        for k, v in o.items():
            _pack(k, out)
            _pack(v, out)
    else:
        raise TypeError(f"msgpack : type non géré {type(o)}")


def unpack(buf) -> object:
    mv = memoryview(buf)
    value, _ = _unpack(mv, 0)
    return value


def _str(mv: memoryview, pos: int, n: int):
    end = pos + n
    if n > BIG_STR:
        return mv[pos:end], end
    return str(mv[pos:end], "utf-8"), end


def _unpack(mv: memoryview, pos: int):
    b = mv[pos]
    pos += 1
    if b < 0x80:
        return b, pos
    if b >= 0xE0:
        return b - 0x100, pos
    if 0xA0 <= b <= 0xBF:
        return _str(mv, pos, b & 0x1F)
    if 0x90 <= b <= 0x9F:
        return _array(mv, pos, b & 0x0F)
    if 0x80 <= b <= 0x8F:
        return _map(mv, pos, b & 0x0F)
    if b == 0xC0:
        return None, pos
    if b == 0xC2:
        return False, pos
    if b == 0xC3:
        return True, pos
    if b in (0xC4, 0xC5, 0xC6):
        size = {0xC4: 1, 0xC5: 2, 0xC6: 4}[b]
        n = int.from_bytes(mv[pos:pos + size], "big")
        pos += size
        return mv[pos:pos + n], pos + n
    if b == 0xCA:
        return struct.unpack_from(">f", mv, pos)[0], pos + 4
    if b == 0xCB:
        return struct.unpack_from(">d", mv, pos)[0], pos + 8
    if 0xCC <= b <= 0xCF:
        size = 1 << (b - 0xCC)
        return int.from_bytes(mv[pos:pos + size], "big"), pos + size
    if 0xD0 <= b <= 0xD3:
        size = 1 << (b - 0xD0)
        return int.from_bytes(mv[pos:pos + size], "big", signed=True), pos + size
    if b in (0xD9, 0xDA, 0xDB):
        size = {0xD9: 1, 0xDA: 2, 0xDB: 4}[b]
        n = int.from_bytes(mv[pos:pos + size], "big")
        return _str(mv, pos + size, n)
    if b in (0xDC, 0xDD):
        size = 2 if b == 0xDC else 4
        return _array(mv, pos + size, int.from_bytes(mv[pos:pos + size], "big"))
    if b in (0xDE, 0xDF):
        size = 2 if b == 0xDE else 4
        return _map(mv, pos + size, int.from_bytes(mv[pos:pos + size], "big"))
    raise ValueError(f"msgpack : octet inattendu {b:#x}")


def _array(mv, pos, n):
    out = []
    for _ in range(n):
        v, pos = _unpack(mv, pos)
        out.append(v)
    return out, pos


def _map(mv, pos, n):
    out = {}
    for _ in range(n):
        k, pos = _unpack(mv, pos)
        v, pos = _unpack(mv, pos)
        out[k if isinstance(k, str) else str(k)] = v
    return out, pos
