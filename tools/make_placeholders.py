"""Génère les images « caméra virtuelle inactive » aux couleurs des instances.

    python tools/make_placeholders.py

Part de l'image d'OBS (placeholder.png) : les aplats bleus prennent la teinte de chaque
couleur d'instance (même luminosité), le logo et l'icône restent neutres.
Résultat : multiobs/assets/placeholders/<couleur>.png (embarqué dans l'appli).
"""
import colorsys
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from multiobs import paths, theme  # noqa: E402

OUT = ROOT / "multiobs" / "assets" / "placeholders"


def source() -> Path:
    for base in (paths.RUNTIME, paths.find_obs_install()):
        if base:
            p = Path(base) / "data" / "obs-plugins" / "win-dshow" / "placeholder.png"
            if p.exists():
                return p
    raise SystemExit("placeholder.png d'OBS introuvable")


def recolor(rgb: np.ndarray, hex_color: str) -> np.ndarray:
    """Remplace la teinte des pixels colorés (HSV), garde saturation et luminosité."""
    target_h = colorsys.rgb_to_hsv(*(int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)))[0]
    f = rgb.astype(np.float32) / 255
    mx, mn = f.max(axis=2), f.min(axis=2)
    v = mx
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    # Teinte cible pour les pixels saturés ; le logo et l'icône (gris) ne bougent pas.
    weight = np.clip((s - 0.12) / 0.15, 0, 1)
    h6 = target_h * 6
    i = np.floor(h6)
    frac = h6 - i
    p, q, t = v * (1 - s), v * (1 - s * frac), v * (1 - s * (1 - frac))
    i = int(i) % 6
    channels = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]
    new = np.stack(channels, axis=2)
    out = f * (1 - weight[..., None]) + new * weight[..., None]
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rgb = np.array(Image.open(source()).convert("RGB"))
    for key in theme.ACCENTS:
        Image.fromarray(recolor(rgb, theme.accent(key, 2))).save(OUT / f"{key}.png", optimize=True)
        print("ok", key)


if __name__ == "__main__":
    main()
