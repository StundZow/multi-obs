"""Construit les exécutables dans dist/ :

  Multi-OBS.exe        l'application (copiée aussi en « Multi OBS.exe » à la racine)
  Multi-OBS-Setup.exe  l'installateur, qui contient l'application : c'est le seul fichier publié

    python build.py            # les deux
    python build.py app        # l'application seulement
    python build.py installer  # l'installateur seulement
"""
import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
ICON = ROOT / "multiobs" / "assets" / "multiobs.ico"
PLUGIN = ROOT / "streamdeck" / "com.stundzow.multiobs.sdPlugin"   # plugin Stream Deck livré avec l'appli


def make_icon() -> None:
    from PIL import Image
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtWidgets import QApplication

    sys.path.insert(0, str(ROOT))
    from multiobs.__main__ import app_icon

    app = QApplication.instance() or QApplication(sys.argv)
    ic = app_icon()
    images = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        ic.pixmap(size, size).save(buf, "PNG")
        images.append(Image.open(BytesIO(bytes(buf.data()))).convert("RGBA"))
    images[-1].save(ICON, sizes=[im.size for im in images], append_images=images[:-1])
    del app


def pyinstaller(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
                    "--icon", str(ICON), "--distpath", str(DIST), "--workpath", str(ROOT / "build"),
                    "--specpath", str(ROOT / "build"), *args], check=True)


def build_app() -> Path:
    pyinstaller("--name", "Multi-OBS",
                "--add-data", f"{ROOT / 'multiobs' / 'assets'};multiobs/assets",
                "--add-data", f"{PLUGIN};streamdeck/{PLUGIN.name}",
                "--hidden-import", "PySide6.QtSvg",
                str(ROOT / "Multi OBS.pyw"))
    exe = DIST / "Multi-OBS.exe"
    try:
        shutil.copy2(exe, ROOT / "Multi OBS.exe")
    except PermissionError:
        print("Attention : « Multi OBS.exe » est ouvert, copie à la racine ignorée (dist/ est à jour).")
    return exe


def build_installer() -> Path:
    app = DIST / "Multi-OBS.exe"
    if not app.exists():
        raise SystemExit("Construis d'abord l'application (python build.py app).")
    pyinstaller("--name", "Multi-OBS-Setup", "--paths", str(ROOT),
                "--add-data", f"{ICON};.",
                "--add-data", f"{app};payload",
                "--exclude-module", "PySide6", "--exclude-module", "psutil",
                str(ROOT / "installer" / "setup_multiobs.py"))
    return DIST / "Multi-OBS-Setup.exe"


def main() -> None:
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    make_icon()
    DIST.mkdir(exist_ok=True)
    if what in ("all", "app"):
        print("OK :", build_app())
    if what in ("all", "installer"):
        print("OK :", build_installer())
    shutil.rmtree(ROOT / "build", ignore_errors=True)


if __name__ == "__main__":
    main()
