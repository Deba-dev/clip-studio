"""Runs worker processes one at a time and reports their JSON progress lines."""
import json
import os
import sys
from collections import deque

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

BACKGROUND = "captions"     # the one job that yields to everything else


class ProcessGroup:
    """Holds the worker and every process it starts (FFmpeg, the HUD reader) in one Windows job object.

    Closing the app, a crash or a shutdown closes the job's handle, and Windows then ends every process in it, so a
    job never carries on headless. The same group lets the whole tree be paused and resumed together. Off Windows it
    does nothing and pausing is unavailable.
    """
    KILL_ON_CLOSE = 0x2000
    SUSPEND_RESUME = 0x0800
    TERMINATE = 0x0001
    SET_QUOTA = 0x0100

    def __init__(self):
        self.handle = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
            self.k = ctypes.WinDLL("kernel32", use_last_error=True)
            self.nt = ctypes.WinDLL("ntdll")
            self.k.CreateJobObjectW.restype = wintypes.HANDLE
            self.k.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
            self.k.OpenProcess.restype = wintypes.HANDLE
            self.k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            self.k.CloseHandle.argtypes = (wintypes.HANDLE,)
            self.k.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
            self.k.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
            self.k.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
            self.k.QueryInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                         wintypes.DWORD, ctypes.c_void_p)
            self.nt.NtSuspendProcess.argtypes = (wintypes.HANDLE,)
            self.nt.NtResumeProcess.argtypes = (wintypes.HANDLE,)

            class Basic(ctypes.Structure):
                _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                            ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", wintypes.DWORD),
                            ("f", ctypes.c_size_t), ("g", wintypes.DWORD), ("h", wintypes.DWORD)]

            class Counters(ctypes.Structure):
                _fields_ = [("r", ctypes.c_uint64), ("w", ctypes.c_uint64), ("o", ctypes.c_uint64),
                            ("rb", ctypes.c_uint64), ("wb", ctypes.c_uint64), ("ob", ctypes.c_uint64)]

            class Extended(ctypes.Structure):
                _fields_ = [("basic", Basic), ("io", Counters), ("pm", ctypes.c_size_t), ("jm", ctypes.c_size_t),
                            ("ppm", ctypes.c_size_t), ("pjm", ctypes.c_size_t)]

            info = Extended()
            info.basic.LimitFlags = self.KILL_ON_CLOSE
            handle = self.k.CreateJobObjectW(None, None)
            if handle and self.k.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
                self.handle = handle
        except (AttributeError, OSError):
            self.handle = None

    def add(self, pid):
        if not self.handle or not pid:
            return
        proc = self.k.OpenProcess(self.SET_QUOTA | self.TERMINATE, False, pid)
        if proc:
            self.k.AssignProcessToJobObject(self.handle, proc)
            self.k.CloseHandle(proc)

    def pids(self):
        import ctypes
        if not self.handle:
            return []
        size = 512

        class Listing(ctypes.Structure):        # JOBOBJECT_BASIC_PROCESS_ID_LIST: the ids are pointer-sized
            _fields_ = [("assigned", ctypes.c_uint32), ("listed", ctypes.c_uint32), ("ids", ctypes.c_size_t * size)]

        listing = Listing()
        if not self.k.QueryInformationJobObject(self.handle, 3, ctypes.byref(listing), ctypes.sizeof(listing), None):
            return []
        return [int(listing.ids[i]) for i in range(min(listing.listed, size))]

    def can_pause(self):
        return self.handle is not None

    def pause(self, on, extra=()):
        """Freezes (or thaws) every process in the group. Returns True when it could."""
        if not self.handle:
            return False
        call = self.nt.NtSuspendProcess if on else self.nt.NtResumeProcess
        done = False
        for pid in set(self.pids()) | {p for p in extra if p}:
            proc = self.k.OpenProcess(self.SUSPEND_RESUME, False, pid)
            if proc:
                done = call(proc) == 0 or done
                self.k.CloseHandle(proc)
        return done

    def kill(self):
        """Ends the worker and anything it started, including FFmpeg, even while they are paused."""
        if self.handle:
            self.k.TerminateJobObject(self.handle, 1)


def worker_command(job, target):
    if getattr(sys, "frozen", False):
        return sys.executable, ["--worker", job, str(target)]
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "main.py")
    return sys.executable, [main, "--worker", job, str(target)]


class Jobs(QObject):
    progress = Signal(str, float, str)      # stage, 0..1, note
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
        self.cancelled = False
        self.paused = False
        self.group = ProcessGroup()

    def add(self, job, target):
        if (job, target) == self.current or (job, target) in self.queue:
            return
        if job == "export" and self.current and self.current[0] == BACKGROUND and self.proc:
            # Background captions can take an hour. An export never waits for them: it goes first, then they resume
            # from the next clip still waiting.
            self.queue.appendleft(self.current)
            self.queue.appendleft((job, target))
            self._kill()
            return
        if job == BACKGROUND:
            self.queue.append((job, target))
        else:           # anything the user asked for goes ahead of background captions
            spot = next((i for i, (j, _) in enumerate(self.queue) if j == BACKGROUND), len(self.queue))
            self.queue.insert(spot, (job, target))
        self._next()

    def busy(self):
        return self.proc is not None

    def can_pause(self):
        return self.group.can_pause()

    def pause(self, on=True):
        """Freezes the running job where it is, FFmpeg included, so the PC is free until it is resumed."""
        if not self.proc or on == self.paused:
            return self.paused
        if self.group.pause(on, [self.proc.processId()]):
            self.paused = on
        return self.paused

    def _kill(self):
        self.cancelled = True
        self.group.kill()       # the whole tree: a killed worker must not leave a frozen FFmpeg behind
        self.proc.kill()
        self.paused = False

    def cancel(self):
        """Stops the running job and lets the queue carry on."""
        if self.proc:
            self._kill()

    def stop(self):
        """The app is closing: the running job is stopped for good, never picked up again later."""
        self.queue.clear()
        if self.proc:
            self._kill()
            self.proc.waitForFinished(3000)

    def _next(self):
        if self.proc or not self.queue:
            return
        self.current = self.queue.popleft()
        self.final = {}
        self.buffer = b""
        self.cancelled = False
        self.paused = False
        self.proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        if self.db_path:
            env.insert("CLIPSTUDIO_DB", self.db_path)
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(self._failed_start)
        self.proc.started.connect(lambda proc=self.proc: self.group.add(proc.processId()))
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
                self.progress.emit(message["stage"], float(message.get("value", 0)), message.get("note", ""))
            else:
                self.final = message

    def _done(self, *_):
        if self.proc is None:
            return
        self._read()
        if self.cancelled:
            self.final = {"cancelled": True}
        elif not self.final:
            self.final = {"error": "The background worker stopped unexpectedly."}
        job, target = self.current
        self.proc.deleteLater()
        self.proc = None
        self.current = None
        self.paused = False
        self.finished.emit(job, target, self.final)
        if self.queue:
            self._next()
        else:
            self.idle.emit()
