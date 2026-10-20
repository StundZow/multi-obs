"""Exécution des opérations longues (copie d'OBS, préconfigs…) hors du thread de l'interface."""
import traceback

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout


class Task(QThread):
    progress = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            result = self.fn(lambda i, t, m: self.progress.emit(i, t, m))
        except Exception as e:  # noqa: BLE001 — remonté à l'utilisateur
            traceback.print_exc()
            self.failed.emit(str(e) or e.__class__.__name__)
            return
        self.succeeded.emit(result)


class ProgressDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight: 600; font-size: 11pt;")
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 0)
        self.msg = QLabel("")
        self.msg.setProperty("muted", True)
        lay.addWidget(self.title)
        lay.addWidget(self.bar)
        lay.addWidget(self.msg)

    def set_progress(self, i: int, total: int, msg: str) -> None:
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(i)
        else:
            self.bar.setRange(0, 0)
        fm = self.msg.fontMetrics()
        self.msg.setText(fm.elidedText(msg, Qt.TextElideMode.ElideMiddle, 420))

    def reject(self):  # pas d'annulation avec Échap
        pass


def run_task(parent, title: str, fn, on_done=None, on_error=None) -> Task:
    """Lance fn(progress) dans un thread ; affiche une fenêtre de progression si ça dure."""
    from PySide6.QtWidgets import QMessageBox

    dlg = ProgressDialog(title, parent)
    task = Task(fn, parent)
    task.progress.connect(dlg.set_progress)
    show_timer = QTimer(parent, singleShot=True, interval=350, timeout=dlg.show)

    def finish():
        show_timer.stop()
        dlg.hide()
        dlg.deleteLater()
        task.deleteLater()

    def ok(result):
        finish()
        if on_done:
            on_done(result)

    def err(message):
        finish()
        if on_error:
            on_error(message)
        else:
            QMessageBox.critical(parent, title, f"Une erreur est survenue :\n\n{message}")

    task.succeeded.connect(ok)
    task.failed.connect(err)
    parent._running_tasks = getattr(parent, "_running_tasks", set())
    parent._running_tasks.add(task)
    task.finished.connect(lambda: parent._running_tasks.discard(task))
    show_timer.start()
    task.start()
    return task
