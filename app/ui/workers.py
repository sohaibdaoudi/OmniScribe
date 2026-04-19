from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class FunctionWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, callback: Callable[[], Any]) -> None:
        super().__init__()
        self.callback = callback

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.callback()
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
