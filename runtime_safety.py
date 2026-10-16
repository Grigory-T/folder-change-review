"""Local working storage and offline/read-only application safeguards."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import sys
import tempfile

_offline = False
_roots = ()
_open_folder = None


def absolute(path):
    value = os.path.abspath(os.path.expanduser(os.fspath(path)))
    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    return value[4:] if value.startswith("\\\\?\\") else value


def extended(path):
    value = absolute(path)
    if os.name != "nt":
        return value
    return "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value


def inside(path, root):
    candidate = os.path.normcase(absolute(os.path.realpath(extended(path))))
    parent = os.path.normcase(absolute(os.path.realpath(extended(root))))
    try:
        if os.path.commonpath((candidate, parent)) == parent:
            return True
    except ValueError:
        pass
    # Also cover mapped-drive/subst aliases that keep different spellings.
    while True:
        try:
            if os.path.samefile(extended(candidate), extended(parent)):
                return True
        except OSError:
            pass
        previous = candidate
        candidate = os.path.dirname(candidate)
        if previous == candidate:
            return False


def local_storage(path):
    candidate = absolute(os.path.realpath(extended(path)))
    if os.name == "nt":
        import ctypes
        drive, _ = os.path.splitdrive(candidate)
        if drive.startswith("\\\\"):
            return False
        get_type = ctypes.windll.kernel32.GetDriveTypeW
        get_type.argtypes = [ctypes.c_wchar_p]
        get_type.restype = ctypes.c_uint
        return get_type(drive + "\\") in (2, 3, 6)
    network = {"cifs", "smb3", "nfs", "nfs4", "fuse.sshfs", "9p", "afs"}
    best, kind = "", ""
    with open("/proc/self/mountinfo", encoding="utf-8") as stream:
        for line in stream:
            fields, details = line.rstrip().split(" - ", 1)
            mount = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields.split()[4])
            if (candidate == mount or candidate.startswith(mount.rstrip("/") + "/")) and len(mount) > len(best):
                best, kind = mount, details.split()[0]
    return kind not in network


def require_local(path):
    if not local_storage(path):
        raise ValueError("Keep the application, states, reports and temporary files on local storage. SMB project folders are supported.")


def application_directory():
    return Path(absolute(sys.executable if getattr(sys, "frozen", False) else __file__)).parent


def audit(event, args):
    if not _offline:
        return
    if event.startswith("socket.") or event in {"urllib.Request", "http.client.connect", "webbrowser.open", "winreg.ConnectRegistry"}:
        raise PermissionError("Internet and Python network APIs are disabled; SMB filesystem reads remain allowed.")
    if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn"}:
        raise PermissionError("Launching subprocesses is disabled.")
    if event in {"os.startfile", "os.startfile/2"}:
        if _open_folder is None or os.path.normcase(absolute(args[0])) != _open_folder:
            raise PermissionError("Only the local application folder may be opened.")
        return

    def protect(value, dir_fd=None):
        if isinstance(value, int):
            # File-descriptor mutation is not needed by this application.
            raise PermissionError("File-descriptor mutation is disabled.")
        if not isinstance(value, (str, bytes, os.PathLike)):
            return
        value = os.fsdecode(value)
        if dir_fd not in (None, -1) and not os.path.isabs(value):
            value = os.path.join(os.readlink(f"/proc/self/fd/{dir_fd}"), value)
        if any(inside(value, root) for root in _roots):
            raise PermissionError("The project folder is read-only to this application.")
        if not local_storage(value):
            raise PermissionError("Working-file writes must stay on local storage.")
    if event == "open":
        filename, _, flags = args
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            protect(filename)
    elif event in {"os.remove", "os.rmdir"}:
        protect(args[0], args[1])
    elif event == "os.mkdir":
        protect(args[0], args[2])
    elif event in {"os.rename", "os.link"}:
        protect(args[0], args[2]); protect(args[1], args[3])
    elif event == "os.symlink":
        protect(args[1], args[2])
    elif event in {"os.chmod", "os.chown", "os.utime"}:
        protect(args[0], args[-1])
    elif event in {"os.truncate", "os.setxattr", "os.removexattr", "shutil.rmtree"}:
        protect(args[0])


sys.addaudithook(audit)


@contextmanager
def offline_runtime(directory=None):
    global _offline
    if directory is not None:
        require_local(directory)
    if getattr(sys, "frozen", False):
        require_local(sys._MEIPASS)
    previous = _offline
    _offline = True
    try:
        yield
    finally:
        _offline = previous


@contextmanager
def safe_operation(roots, output_directory):
    global _roots
    require_local(output_directory)
    roots = tuple(absolute(root) for root in roots)
    if any(inside(output_directory, root) for root in roots):
        raise ValueError("Save states and reports outside the project folder.")
    if getattr(sys, "frozen", False) and any(inside(sys._MEIPASS, root) for root in roots):
        raise ValueError("The project folder contains the running temporary runtime. Choose a narrower project folder.")
    previous_roots, previous_temp = _roots, tempfile.tempdir
    with offline_runtime():
        _roots = roots
        try:
            with tempfile.TemporaryDirectory(prefix=".folder-change-review-work-", dir=extended(output_directory)) as workspace:
                tempfile.tempdir = workspace
                try:
                    yield
                finally:
                    tempfile.tempdir = previous_temp
        finally:
            _roots = previous_roots


def open_application_folder(directory):
    global _open_folder
    require_local(directory)
    _open_folder = os.path.normcase(absolute(directory))
    try:
        os.startfile(absolute(directory))
    finally:
        _open_folder = None
