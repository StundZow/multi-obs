"""Publie une nouvelle version sur GitHub.

    python release.py 1.1.0

1. met la version dans multiobs/__init__.py
2. construit l'installateur Multi-OBS-Setup.exe, qui contient l'appli (build.py)
3. commit + tag v1.1.0 + push
4. crée la release GitHub (seulement l'installateur) avec les notes de CHANGELOG.md (« ## 1.1.0 »)

Les applis installées la proposent au prochain démarrage, avec ces notes.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(*cmd: str) -> str:
    print(">", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout


def changelog_section(version: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text("utf-8")
    m = re.search(rf"^## \[?{re.escape(version)}\]?.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m or not m.group(1).strip():
        raise SystemExit(f"Ajoute d'abord une section « ## {version} » dans CHANGELOG.md")
    return m.group(1).strip()


def main() -> None:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        raise SystemExit("Usage : python release.py X.Y.Z")
    version = sys.argv[1]
    notes = changelog_section(version)
    init = ROOT / "multiobs" / "__init__.py"
    text = init.read_text("utf-8")
    init.write_text(re.sub(r'APP_VERSION = "[^"]*"', f'APP_VERSION = "{version}"', text), "utf-8")

    subprocess.run([sys.executable, str(ROOT / "build.py")], cwd=ROOT, check=True)

    run("git", "add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
        run("git", "commit", "-m", f"Version {version}")
    run("git", "tag", f"v{version}")
    run("git", "push")
    run("git", "push", "origin", f"v{version}")
    notes_file = ROOT / "build_notes.md"
    notes_file.write_text(notes, "utf-8")
    try:
        run("gh", "release", "create", f"v{version}", str(ROOT / "dist" / "Multi-OBS-Setup.exe"),
            "--title", f"Multi OBS {version}",
            "--notes-file", str(notes_file))
    finally:
        notes_file.unlink(missing_ok=True)
    print(f"Version {version} publiée.")


if __name__ == "__main__":
    main()
