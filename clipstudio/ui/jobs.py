"""Runs worker processes one at a time and reports their JSON progress lines."""
import json
import os
import sys
from collections import deque

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal


def worker_command(job, target):
    if getattr(sys, "frozen", False):
        return sys.executable, ["--worker", job, str(target)]
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "main.py")
    return sys.executable, [main, "--worker", job, str(target)]


class Jobs(QObject):
    progress = Signal(str, float)           # stage, 0..1
    finished = Signal(str, int, dict)       # job, target, final message
    idle = Signal()

    def __init__(self, db_path=None):
        super().__init__()
        self.queue = deque()
        self.proc = None
        self.current = None
        self.final = {}
        self.buffer = b""
        self.db_path = db_path

    def add(self, job, target):
        if (job, target) == self.current or (job, target) in self.queue:
            return
        self.queue.append((job, target))
        self._next()

    def busy(self):
        return self.proc is not None

    def stop(self):
        self.queue.clear()
        if self.proc:
            self.proc.kill()
            self.proc.waitForFinished(3000)

    def _next(self):
        if self.proc or not self.queue:
            return
        self.current = self.queue.popleft()
        self.final = {}
        self.buffer = b""
        self.proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        if self.db_path:
            env.insert("CLIPSTUDIO_DB", self.db_path)
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(self._failed_start)
        program, args = worker_command(*self.current)
        self.proc.start(program, args)

    def _failed_start(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.final = {"error": "The background worker could not start."}
            self._done()

    def _read(self):
        self.buffer += bytes(self.proc.readAllStandardOutput())
        *lines, self.buffer = self.buffer.split(b"\n")
        for line in lines:
            try:
                message = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue            # libraries may print their own lines
            if "stage" in message:
                self.progress.emit(message["stage"], float(message.get("value", 0)))
            else:
                self.final = message

    def _done(self, *_):
        if self.proc is None:
            return
        self._read()
        if not self.final:
            self.final = {"error": "The background worker stopped unexpectedly."}
        job, target = self.current
        self.proc.deleteLater()
        self.proc = None
        self.current = None
        self.finished.emit(job, target, self.final)
        if self.queue:
            self._next()
        else:
            self.idle.emit()
