"""Compressed machine states and managed local state history."""
from datetime import datetime
import json
import ntpath
import os
from pathlib import Path
import uuid
import zipfile

from runtime_safety import absolute, extended, require_local

FORMAT = "folder-change-review.snapshot"
EXTENSION = ".fcrstate"


def path_module(root):
    return ntpath if ntpath.splitdrive(root)[0] or root.startswith("\\\\") else os.path


def write_container(path, snapshot):
    metadata = {key: value for key, value in snapshot.items() if key != "files"}
    metadata.update({"version": 2, "file_count": len(snapshot["files"]), "hash_algorithm": "sha256"})
    module = path_module(snapshot["root"])
    records = [[module.relpath(row["path"], snapshot["root"]), row["size"], row["sha256"]] for row in snapshot["files"]]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, separators=(",", ":")))
        archive.writestr("files.json", json.dumps(records, ensure_ascii=False, separators=(",", ":")))


def read_metadata(path):
    require_local(path)
    with zipfile.ZipFile(extended(path)) as archive:
        info = archive.getinfo("metadata.json")
        if info.file_size > 1_048_576:
            raise ValueError("Invalid state metadata.")
        metadata = json.loads(archive.read(info))
    if not isinstance(metadata, dict) or metadata.get("format") != FORMAT or metadata.get("version") != 2 or metadata.get("hash_algorithm") != "sha256":
        raise ValueError("Unsupported state format.")
    if not isinstance(metadata.get("root"), str) or not metadata["root"] or type(metadata.get("file_count")) is not int or metadata["file_count"] < 0:
        raise ValueError("Invalid state metadata.")
    try:
        datetime.fromisoformat(metadata["completed_utc"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Invalid state capture time.") from error
    return metadata


def read_container(path):
    metadata = read_metadata(path)
    module = path_module(metadata["root"])
    with zipfile.ZipFile(extended(path)) as archive:
        records = json.loads(archive.read("files.json"))
    if len(records) != metadata["file_count"]:
        raise ValueError("State record count does not match its metadata.")
    files = []
    for relative, size, digest in records:
        if not isinstance(relative, str) or module.isabs(relative) or module.splitdrive(relative)[0] or ".." in relative.replace("\\", "/").split("/"):
            raise ValueError("Invalid relative path in state.")
        files.append({"path": module.join(metadata["root"], relative),
                      "parts": relative.split(module.sep), "size": size, "sha256": digest})
    return {**metadata, "files": files}


class StateHistory:
    def __init__(self, directory):
        self.directory = Path(absolute(directory))
        require_local(self.directory)
        self.states = self.directory / ".states"

    def ensure(self):
        self.states.mkdir(exist_ok=True)
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
        return self.directory / ("folder-changes-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6] + ".xlsx")

    def list_states(self):
        items, errors = [], []
        if self.states.exists():
            for path in self.states.glob("*" + EXTENSION):
                try:
                    metadata = read_metadata(path)
                    items.append({"path": path, "metadata": metadata})
                except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
                    errors.append(f"{path.name}: {error}")
        items.sort(key=lambda item: (item["metadata"]["completed_utc"], item["path"].name), reverse=True)
        return items, errors

    def settings(self):
        try:
            with open(extended(self.states / "settings.json"), encoding="utf-8") as stream:
                value = json.load(stream)
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_settings(self, value):
        from folder_change_review import staged_output
        self.ensure()
        with staged_output(self.states / "settings.json") as temporary:
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
