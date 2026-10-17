"""Compressed machine states and managed local state history."""
from datetime import datetime
import json
import hashlib
import ntpath
import os
import shutil
from pathlib import Path
import uuid
import zipfile

from runtime_safety import absolute, extended, local_storage, require_local

FORMAT = "folder-change-review.snapshot"
EXTENSION = ".fcrstate"


def path_module(root):
    return ntpath if ntpath.splitdrive(root)[0] or root.startswith("\\\\") else os.path


def write_container(path, snapshot):
    metadata = {key: value for key, value in snapshot.items() if key not in ("files", "read_errors")}
    metadata.update({"version": snapshot["version"] if snapshot.get("version") in (3, 4) else 2, "file_count": len(snapshot["files"]), "hash_algorithm": "sha256"})
    module = path_module(snapshot["root"])
    records = [[module.relpath(row["path"], snapshot["root"]), row["size"], row["sha256"]] for row in snapshot["files"]]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, separators=(",", ":")))
        archive.writestr("files.json", json.dumps(records, ensure_ascii=False, separators=(",", ":")))
        if metadata["version"] in (3, 4):
            errors = [[module.relpath(issue["path"], snapshot["root"]), issue["kind"], issue["errno"],
                       issue["winerror"], issue["message"]] for issue in snapshot["read_errors"]]
            archive.writestr("errors.json", json.dumps(errors, ensure_ascii=False, separators=(",", ":")))


def read_metadata(path):
    require_local(path)
    with zipfile.ZipFile(extended(path)) as archive:
        info = archive.getinfo("metadata.json")
        if info.file_size > 1_048_576:
            raise ValueError("Invalid state metadata.")
        metadata = json.loads(archive.read(info))
    if not isinstance(metadata, dict) or metadata.get("format") != FORMAT or metadata.get("version") not in (2, 3, 4) or metadata.get("hash_algorithm") != "sha256":
        raise ValueError("Unsupported state format.")
    if not isinstance(metadata.get("root"), str) or not metadata["root"] or type(metadata.get("file_count")) is not int or metadata["file_count"] < 0:
        raise ValueError("Invalid state metadata.")
    if metadata["version"] in (3, 4):
        count = metadata.get("read_error_count")
        if type(count) is not int or count < 0 or type(metadata.get("complete")) is not bool or metadata["complete"] != (count == 0):
            raise ValueError("Invalid state coverage metadata.")
    try:
        datetime.fromisoformat(metadata["completed_utc"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Invalid state capture time.") from error
    return metadata


def read_container(path):
    metadata = read_metadata(path)
    module = path_module(metadata["root"])
    with zipfile.ZipFile(extended(path)) as archive:
        try:
            records = json.loads(archive.read("files.json"))
            errors = json.loads(archive.read("errors.json")) if metadata["version"] in (3, 4) else []
        except KeyError as error:
            raise ValueError("State is damaged: a required record file is missing.") from error
    if not isinstance(records, list) or not isinstance(errors, list):
        raise ValueError("Invalid state records.")
    if len(records) != metadata["file_count"]:
        raise ValueError("State record count does not match its metadata.")
    files = []
    for record in records:
        if not isinstance(record, list) or len(record) != 3:
            raise ValueError("Invalid file record in state.")
        relative, size, digest = record
        if not isinstance(relative, str) or module.isabs(relative) or module.splitdrive(relative)[0] or ".." in relative.replace("\\", "/").split("/"):
            raise ValueError("Invalid relative path in state.")
        files.append({"path": module.join(metadata["root"], relative),
                      "parts": relative.split(module.sep), "size": size, "sha256": digest})
    result = {**metadata, "files": files}
    if metadata["version"] in (3, 4):
        result["read_errors"] = []
        for record in errors:
            if not isinstance(record, list) or len(record) != 5:
                raise ValueError("Invalid read issue record in state.")
            relative, kind, code, winerror, message = record
            if not isinstance(relative, str) or module.isabs(relative) or module.splitdrive(relative)[0] or ".." in relative.replace("\\", "/").split("/"):
                raise ValueError("Invalid read issue path in state.")
            result["read_errors"].append({"path": module.join(metadata["root"], relative), "parts": relative.split(module.sep),
                                          "kind": kind, "errno": code, "winerror": winerror, "message": message})
        validate_coverage(result)
    return result


def validate_coverage(snapshot):
    if snapshot.get("version") not in (3, 4):
        # Older readers must never silently accept partial-state coverage.
        if snapshot.get("read_errors") or snapshot.get("complete") is False:
            raise ValueError("Partial states require format version 3 or later.")
        return
    errors = snapshot.get("read_errors")
    if (not isinstance(errors, list) or type(snapshot.get("read_error_count")) is not int
            or len(errors) != snapshot["read_error_count"] or type(snapshot.get("complete")) is not bool
            or snapshot["complete"] != (not errors)):
        raise ValueError("Invalid state coverage metadata.")
    module = path_module(snapshot["root"])
    for issue in errors:
        if not isinstance(issue, dict):
            raise ValueError("Invalid read issue in state.")
        parts = issue.get("parts")
        if (not isinstance(parts, list) or not parts or not all(isinstance(part, str) and part not in ("", ".", "..")
                and not any(char in part for char in (module.sep, module.altsep) if char) for part in parts)
                or issue.get("path") != module.join(snapshot["root"], *parts)
                or issue.get("kind") not in ("file", "directory", "unknown")
                or not isinstance(issue.get("message"), str)
                or any(issue.get(key) is not None and type(issue[key]) is not int for key in ("errno", "winerror"))):
            raise ValueError("Invalid read issue in state.")


class StateHistory:
    def __init__(self, directory):
        self.directory = Path(absolute(directory))
        cache = Path(os.environ.get("LOCALAPPDATA", Path.home()/".local"/"share")) / "FolderChangeReview" / "histories"
        key = hashlib.sha256(os.path.normcase(str(self.directory)).encode("utf-8")).hexdigest()[:24]
        self.states = cache / key / ".states"
        self.legacy_states = self.directory / ".states" if local_storage(self.directory) else None
        self.legacy_checked = False
        require_local(self.states)

    def ensure(self):
        Path(extended(self.states)).mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            import ctypes
            get = ctypes.windll.kernel32.GetFileAttributesW
            get.argtypes = [ctypes.c_wchar_p]; get.restype = ctypes.c_uint
            put = ctypes.windll.kernel32.SetFileAttributesW
            put.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
            attributes = get(extended(self.states))
            if attributes != 0xFFFFFFFF:
                put(extended(self.states), attributes | 2)

    def new_state_path(self):
        self.ensure()
        return self.states / ("state-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8] + EXTENSION)

    def new_report_path(self):
        return self.directory / "folder-change-review.xlsx"

    def list_states(self):
        items, errors = [], []
        seen = set()
        for folder in (self.states, self.legacy_states):
            if folder is None or not Path(extended(folder)).is_dir():
                continue
            for path in Path(extended(folder)).glob("*" + EXTENSION):
                path = Path(absolute(path))
                if path.name in seen:
                    continue
                try:
                    metadata = read_metadata(path)
                    items.append({"path": path, "metadata": metadata})
                    seen.add(path.name)
                except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
                    errors.append(f"{path.name}: {error}")
        items.sort(key=lambda item: (item["metadata"]["completed_utc"], item["path"].name), reverse=True)
        return items, errors

    def settings(self):
        for folder in (self.states, self.legacy_states):
            if folder is None:
                continue
            try:
                with open(extended(folder / "settings.json"), encoding="utf-8") as stream:
                    value = json.load(stream)
                if isinstance(value, dict):
                    return value
            except (OSError, ValueError):
                pass
        return {}

    def copy_legacy_states(self):
        """Background, read-only import; startup still reads small metadata only."""
        if self.legacy_checked or self.legacy_states is None:
            return
        from folder_change_review import staged_output
        folder = Path(extended(self.legacy_states))
        if folder.is_dir() and not folder.is_symlink():
            for source in folder.glob("*" + EXTENSION):
                target = self.states / source.name
                if source.is_symlink() or Path(extended(target)).exists():
                    continue
                try:
                    with staged_output(target) as temporary:
                        shutil.copyfile(source, temporary)
                except OSError:
                    # Keep unreadable legacy entries visible in the read-only
                    # history rather than losing them or aborting a new capture.
                    continue
        self.legacy_checked = True

    def save_settings(self, value):
        from folder_change_review import staged_output
        self.ensure()
        self.copy_legacy_states()
        with staged_output(self.states / "settings.json") as temporary:
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
