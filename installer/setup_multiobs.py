"""Installateur de Multi OBS : télécharge la dernière version publiée sur GitHub.

Installation par utilisateur, sans droits administrateur :
  %LOCALAPPDATA%\\Programs\\Multi OBS (modifiable), raccourcis menu Démarrer / bureau,
  entrée « Applications installées » pour la désinstallation.

Options en ligne de commande (tests, déploiement) :
  --silent  --dir <dossier>  --no-desktop  --no-shortcuts  --no-register  --no-launch
"""
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from multiobs import GITHUB_REPO, github, installinfo  # noqa: E402

BG, BASE, INPUT, TEXT, MUTED, ACCENT, ACCENT_HI = (
    "#1D1F26", "#272A33", "#3C404D", "#FFFFFF", "#969696", "#284CB8", "#476BD7")


def install(target_dir: Path, desktop: bool, shortcuts: bool, register: bool,
            status=lambda text: None, progress=lambda done, total: None) -> Path:
    status("Recherche de la dernière version…")
    release = github.latest_release(GITHUB_REPO)
    asset = github.find_asset(release, github.APP_ASSET)
    if not asset:
        raise github.GitHubError(f"La version {release.get('tag_name')} ne contient pas {github.APP_ASSET}.")
    version = (release.get("tag_name") or "").lstrip("v")
    target_dir.mkdir(parents=True, exist_ok=True)
    exe = target_dir / installinfo.EXE_NAME
    old = exe.with_name("Multi OBS.old.exe")
    if exe.exists():
        try:
            old.unlink(missing_ok=True)
            exe.rename(old)
        except OSError:
            raise RuntimeError("Multi OBS est ouvert : ferme-le, puis relance l'installation.")
    status(f"Téléchargement de Multi OBS {version}…")
    try:
        github.download_asset(asset, exe, progress, private=bool(release.get("_token_used")))
    except Exception:
        if old.exists() and not exe.exists():
            old.rename(exe)
        raise
    old.unlink(missing_ok=True)
    if shortcuts:
        status("Création des raccourcis…")
        installinfo.create_shortcuts(exe, desktop)
    if register:
        installinfo.register(target_dir, version)
    status(f"Multi OBS {version} est installé.")
    return exe


class SetupWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Installation de Multi OBS")
        root.configure(bg=BG)
        root.resizable(False, False)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=INPUT, font=("Segoe UI", 10))
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Title.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("TCheckbutton", background=BG, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("TButton", background=INPUT, foreground=TEXT, borderwidth=0, padding=(14, 6))
        style.map("TButton", background=[("active", "#464B59"), ("disabled", BASE)],
                  foreground=[("disabled", MUTED)])
        style.configure("Accent.TButton", background=ACCENT)
        style.map("Accent.TButton", background=[("active", ACCENT_HI), ("disabled", BASE)])
        style.configure("TEntry", fieldbackground=INPUT, foreground=TEXT, insertcolor=TEXT, borderwidth=0)
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=INPUT, borderwidth=0)

        frm = ttk.Frame(root, padding=22, style="TFrame")
        style.configure("TFrame", background=BG)
        frm.grid(sticky="nsew")
        ttk.Label(frm, text="Multi OBS", style="Title.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frm, text="Plusieurs OBS indépendants, pilotés depuis une seule fenêtre.\n"
                            "La dernière version est téléchargée depuis GitHub.",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 16))
        ttk.Label(frm, text="Dossier d'installation").grid(row=2, column=0, columnspan=3, sticky="w")
        self.dir_var = tk.StringVar(value=str(installinfo.default_install_dir()))
        ttk.Entry(frm, textvariable=self.dir_var, width=52).grid(row=3, column=0, columnspan=2, sticky="we",
                                                                  pady=(4, 10), ipady=4)
        ttk.Button(frm, text="Changer…", command=self.browse).grid(row=3, column=2, padx=(8, 0), pady=(4, 10))
        self.desktop = tk.BooleanVar(value=True)
        self.launch = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text="Raccourci sur le bureau", variable=self.desktop).grid(
            row=4, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(frm, text="Lancer Multi OBS à la fin", variable=self.launch).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(2, 14))
        self.bar = ttk.Progressbar(frm, length=440, mode="determinate")
        self.bar.grid(row=6, column=0, columnspan=3, sticky="we")
        self.status = ttk.Label(frm, text="Prêt à installer.", style="Muted.TLabel")
        self.status.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 14))
        self.cancel_btn = ttk.Button(frm, text="Fermer", command=root.destroy)
        self.cancel_btn.grid(row=8, column=1, sticky="e", padx=(0, 8))
        self.go_btn = ttk.Button(frm, text="Installer", style="Accent.TButton", command=self.start)
        self.go_btn.grid(row=8, column=2, sticky="e")
        frm.columnconfigure(0, weight=1)

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            p = Path(d)
            self.dir_var.set(str(p if p.name.lower() == "multi obs" else p / "Multi OBS"))

    def set_status(self, text):
        self.root.after(0, lambda: self.status.configure(text=text))

    def set_progress(self, done, total):
        def upd():
            if total:
                self.bar.configure(mode="determinate", maximum=total, value=done)
        self.root.after(0, upd)

    def start(self):
        self.go_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        target = Path(self.dir_var.get())
        desktop, launch = self.desktop.get(), self.launch.get()

        def work():
            try:
                exe = install(target, desktop, True, True, self.set_status, self.set_progress)
            except Exception as e:  # message clair pour l'utilisateur
                self.set_status(f"Échec : {e}")
                self.root.after(0, lambda: (self.go_btn.configure(state="normal", text="Réessayer"),
                                            self.cancel_btn.configure(state="normal")))
                return
            if launch:
                subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)
                self.root.after(1200, self.root.destroy)
            else:
                self.root.after(0, lambda: (self.cancel_btn.configure(state="normal", text="Terminer"),
                                            self.go_btn.grid_remove()))
        threading.Thread(target=work, daemon=True).start()


def main():
    args = sys.argv[1:]
    if "--silent" in args:
        target = installinfo.default_install_dir()
        if "--dir" in args:
            target = Path(args[args.index("--dir") + 1])
        try:
            exe = install(target, "--no-desktop" not in args, "--no-shortcuts" not in args,
                          "--no-register" not in args, print)
        except Exception as e:
            print(f"ERREUR : {e}")
            return 1
        if "--no-launch" not in args:
            subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)
        return 0
    root = tk.Tk()
    try:
        root.iconbitmap(default=os.path.join(getattr(sys, "_MEIPASS", str(ROOT)), "multiobs.ico"))
    except tk.TclError:
        pass
    SetupWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
