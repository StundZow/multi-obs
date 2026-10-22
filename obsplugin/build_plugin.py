"""Compile le module OBS multiobs-sync.dll (alignement des enregistrements à l'image près).

La DLL compilée est rangée dans obsplugin/bin/ et livrée telle quelle avec Multi OBS : il ne faut
la recompiler que si multiobs-sync.c change. Il faut Visual Studio (outils C++ « MSVC ») et git.

    python obsplugin/build_plugin.py [dossier bin/64bit d'OBS]

Par défaut, les bibliothèques d'import viennent de la copie d'OBS de Multi OBS (data/runtime).
Les en-têtes d'OBS sont pris sur GitHub, à la version OBS_TAG.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEPS = HERE / ".deps"
OBS_TAG = "32.1.2"
OBS_SRC = DEPS / f"obs-studio-{OBS_TAG}"
OUT = HERE / "bin" / "multiobs-sync.dll"
OBSCONFIG = """#pragma once
#define OBS_DATA_PATH "../../data"
#define OBS_PLUGIN_PATH "../../obs-plugins/64bit"
#define OBS_PLUGIN_DESTINATION "obs-plugins/64bit"
#define OBS_RELEASE_CANDIDATE 0
#define OBS_BETA 0
"""


def vcvars() -> Path:
    vswhere = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    if vswhere.exists():
        out = subprocess.run([str(vswhere), "-all", "-products", "*", "-requires",
                              "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                             capture_output=True, text=True).stdout.splitlines()
        for base in out:
            bat = Path(base) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
            if bat.exists():
                return bat
    raise SystemExit("Visual Studio (outils C++ MSVC) introuvable.")


def msvc(bat: Path, command: str, cwd: Path) -> str:
    """Lance une commande dans l'environnement de MSVC ; renvoie sa sortie."""
    run = subprocess.run(f'cmd /d /c "call "{bat}" >nul && {command}"', cwd=cwd, capture_output=True,
                         text=True, encoding="mbcs", errors="replace", shell=False)
    if run.returncode:
        raise SystemExit(f"Échec : {command}\n{run.stdout}\n{run.stderr}")
    return run.stdout


def headers() -> None:
    if (OBS_SRC / "libobs" / "obs-module.h").exists():
        return
    shutil.rmtree(OBS_SRC, ignore_errors=True)
    DEPS.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", OBS_TAG, "--filter=blob:none", "--sparse",
                    "https://github.com/obsproject/obs-studio", str(OBS_SRC)], check=True)
    subprocess.run(["git", "-C", str(OBS_SRC), "sparse-checkout", "set", "libobs", "frontend/api"], check=True)


def import_lib(bat: Path, dll: Path) -> Path:
    """Bibliothèque d'import construite à partir des exports de la DLL d'OBS."""
    out = msvc(bat, f'dumpbin /nologo /exports "{dll}"', DEPS)
    names = re.findall(r"^\s+\d+\s+[0-9A-F]+\s+[0-9A-F]{8}\s+(\S+)", out, re.MULTILINE)
    if not names:
        raise SystemExit(f"Aucun export lu dans {dll}")
    lib = DEPS / (dll.stem + ".lib")
    (DEPS / (dll.stem + ".def")).write_text(f"LIBRARY {dll.name}\nEXPORTS\n" + "\n".join(names) + "\n", "ascii")
    msvc(bat, f'lib /nologo /machine:x64 /def:"{dll.stem}.def" /out:"{lib.name}"', DEPS)
    return lib


def main() -> None:
    obs_bin = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "runtime" / "bin" / "64bit"
    if not (obs_bin / "obs.dll").exists():
        raise SystemExit(f"obs.dll introuvable dans {obs_bin}")
    bat = vcvars()
    headers()
    (DEPS / "obsconfig.h").write_text(OBSCONFIG, "ascii")
    libs = [import_lib(bat, obs_bin / "obs.dll"), import_lib(bat, obs_bin / "obs-frontend-api.dll")]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    includes = " ".join(f'/I"{p}"' for p in (DEPS, OBS_SRC / "libobs", OBS_SRC / "frontend" / "api", HERE))
    msvc(bat, f'cl /nologo /O2 /LD /MD /W3 /utf-8 /DUNICODE /D_UNICODE {includes} "{HERE / "multiobs-sync.c"}" '
              + " ".join(f'"{lib}"' for lib in libs)
              + f' /Fo"{DEPS}\\\\" /Fe"{OUT}" /link /NOLOGO', DEPS)
    for leftover in (OUT.with_suffix(".lib"), OUT.with_suffix(".exp")):
        leftover.unlink(missing_ok=True)
    print("OK :", OUT, OUT.stat().st_size, "octets")


if __name__ == "__main__":
    main()
