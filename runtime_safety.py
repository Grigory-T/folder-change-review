"""Local working storage and offline/read-only application safeguards."""
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import threading

_offline = False
_roots = ()
_open_folder = None
_output_paths = set()
_operation_lock = threading.Lock()
_directory = None
DATA_DIRECTORY = "folder-change-review-data"
MANAGED_DIRECTORIES = (DATA_DIRECTORY, "_internal", "states", "work", "runtime", ".states")


def pasted_path(value):
    value = os.fspath(value).strip()
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value


def path_key(path):
    return os.path.normcase(absolute(path))


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
    # Kept as a compatibility helper for development harnesses. SMB storage is
    # now supported for the complete portable folder, including its runtime.
    return not absolute(path).startswith("\\\\")


def application_directory():
    return _directory or Path(absolute(sys.executable if getattr(sys, "frozen", False) else __file__)).parent


@contextmanager
def portable_directory(directory):
    global _directory
    previous = _directory
    _directory = Path(absolute(directory))
    try:
        yield _directory
    finally:
        _directory = previous


def ensure_managed_directory(path, directory=None):
    base = Path(absolute(directory or application_directory()))
    candidate = Path(absolute(path))
    relative = candidate.relative_to(base)
    current = base
    for part in relative.parts:
        current /= part
        try:
            info = os.lstat(extended(current))
        except FileNotFoundError:
            try:
                os.mkdir(extended(current))
            except FileExistsError:
                pass
            info = os.lstat(extended(current))
        import stat
        if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Portable data folders must be real directories, not links or junctions.")
    return candidate



def data_directory():
    return application_directory()/DATA_DIRECTORY


def configure_portable_storage():
    try:
        work = ensure_managed_directory(data_directory()/"work")
    except OSError as error:
        raise OSError("Cannot write portable data beside the EXE. Place the tool in a writable folder.") from error
    os.environ["TMP"] = os.environ["TEMP"] = str(work)
    tempfile.tempdir = str(work)
    return work


def portable_output(path):
    if inside(path, application_directory()/"_internal"):
        raise ValueError("The bundled _internal runtime is read-only; keep outputs in the tool data folder.")
    if not inside(path, application_directory()):
        raise ValueError("All states and reports must stay inside the folder containing the EXE.")


def owned_path(path):
    candidate, base = path_key(path), path_key(application_directory())
    if candidate == os.path.join(base, "settings.json"):
        return True
    for name in MANAGED_DIRECTORIES:
        if name == "_internal":
            continue
        parent = os.path.join(base, name)
        if candidate == parent or candidate.startswith(parent + os.sep):
            return True
    return False


def audit(event, args):
    if not _offline:
        return
    if event.startswith("socket.") or event in {"urllib.Request", "http.client.connect", "webbrowser.open", "winreg.ConnectRegistry"}:
        raise PermissionError("Internet and Python network APIs are disabled; SMB filesystem reads remain allowed.")
    if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn"}:
        raise PermissionError("Launching subprocesses is disabled.")
    if event in {"os.startfile", "os.startfile/2"}:
        if _open_folder is None or os.path.normcase(absolute(args[0])) != _open_folder:
            raise PermissionError("Only the explicitly requested report folder may be opened.")
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
        if path_key(value) in _output_paths:
            if os.path.islink(extended(value)):
                raise PermissionError("Output writes must not follow symbolic links.")
            return
        if owned_path(value):
            # Realpath confinement also rejects a replaced directory alias.
            if not inside(value, application_directory()):
                raise PermissionError("Portable storage must remain beside the EXE.")
            return
        if any(inside(value, root) for root in _roots):
            raise PermissionError("The project folder is read-only to this application.")
        if not inside(value, application_directory()):
            raise PermissionError("Working files must stay inside the portable tool folder.")
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
    previous = _offline
    with portable_directory(directory or application_directory()):
        _offline = True
        try:
            yield
        finally:
            _offline = previous


@contextmanager
def safe_operation(roots, output_directory):
    if not _operation_lock.acquire(blocking=False):
        raise RuntimeError("Concurrent operations in one process are not supported.")
    try:
        with _safe_operation(roots, output_directory):
            yield
    finally:
        _operation_lock.release()


@contextmanager
def _safe_operation(roots, output_directory):
    global _roots
    roots = tuple(absolute(root) for root in roots)
    if _roots:
        raise RuntimeError("Concurrent operations in one process are not supported.")
    previous_roots, previous_temp = _roots, tempfile.tempdir
    with offline_runtime():
        _roots = roots
        try:
            parent = ensure_managed_directory(data_directory()/"work")
            with tempfile.TemporaryDirectory(prefix="operation-", dir=extended(parent)) as workspace:
                tempfile.tempdir = workspace
                try:
                    yield
                finally:
                    tempfile.tempdir = previous_temp
        finally:
            _roots = previous_roots


def open_application_folder(directory):
    global _open_folder
    _open_folder = os.path.normcase(absolute(directory))
    try:
        os.startfile(absolute(directory))
    finally:
        _open_folder = None


@contextmanager
def output_writes(paths):
    """Exact write exceptions for a selected output and its atomic staging file."""
    keys = {path_key(path) for path in paths}
    previous = _output_paths.copy()
    _output_paths.update(keys)
    try:
        yield
    finally:
        _output_paths.clear()
        _output_paths.update(previous)
