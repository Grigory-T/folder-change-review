"""Compressed machine states and portable state history."""
from datetime import datetime
import json
import ntpath
import os
import shutil
import stat
from pathlib import Path
import uuid
import zipfile

from runtime_safety import absolute, extended, portable_output, DATA_DIRECTORY

FORMAT = "folder-change-review.snapshot"
EXTENSION = ".fcrstate"


def path_module(root):
    return ntpath if ntpath.splitdrive(root)[0] or root.startswith("\\\\") else os.path


def write_container(path, snapshot):
    metadata = {key: value for key, value in snapshot.items() if key not in ("files", "read_errors")}
    version = snapshot["version"] if snapshot.get("version") in (3, 4, 5, 6, 7) else 2
    metadata.update({"version": version, "file_count": len(snapshot["files"])})
    if version not in (5, 6, 7):
        metadata["hash_algorithm"] = "sha256"
    module = path_module(snapshot["root"])
    records = [[module.relpath(row["path"], snapshot["root"]), row["size"], row["sha256"]] for row in snapshot["files"]]
    if version in (5, 6, 7):
        records = [record + [row["mtime_ns"]] for record, row in zip(records, snapshot["files"])]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, separators=(",", ":")))
        archive.writestr("files.json", json.dumps(records, ensure_ascii=False, separators=(",", ":")))
        if metadata["version"] in (3, 4, 5, 6, 7):
            errors = [[module.relpath(issue["path"], snapshot["root"]), issue["kind"], issue["errno"],
                       issue["winerror"], issue["message"]] for issue in snapshot["read_errors"]]
            archive.writestr("errors.json", json.dumps(errors, ensure_ascii=False, separators=(",", ":")))


def read_metadata(path):
    portable_output(path)
    info = os.lstat(extended(path))
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("States must be regular files, not links or junctions.")
    with zipfile.ZipFile(extended(path)) as archive:
        info = archive.getinfo("metadata.json")
        if info.file_size > 1_048_576:
            raise ValueError("Invalid state metadata.")
        metadata = json.loads(archive.read(info))
    if not isinstance(metadata, dict) or metadata.get("format") != FORMAT or metadata.get("version") not in (2, 3, 4, 5, 6, 7):
        raise ValueError("Unsupported state format.")
    validate_mode(metadata)
    if not isinstance(metadata.get("root"), str) or not metadata["root"] or type(metadata.get("file_count")) is not int or metadata["file_count"] < 0:
        raise ValueError("Invalid state metadata.")
    if metadata["version"] in (3, 4, 5, 6, 7):
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
            errors = json.loads(archive.read("errors.json")) if metadata["version"] in (3, 4, 5, 6, 7) else []
        except KeyError as error:
            raise ValueError("State is damaged: a required record file is missing.") from error
    if not isinstance(records, list) or not isinstance(errors, list):
        raise ValueError("Invalid state records.")
    if len(records) != metadata["file_count"]:
        raise ValueError("State record count does not match its metadata.")
    files = []
    for record in records:
        if not isinstance(record, list) or len(record) != (4 if metadata["version"] in (5, 6, 7) else 3):
            raise ValueError("Invalid file record in state.")
        relative, size, digest = record[:3]
        if not isinstance(relative, str) or module.isabs(relative) or module.splitdrive(relative)[0] or ".." in relative.replace("\\", "/").split("/"):
            raise ValueError("Invalid relative path in state.")
        files.append({"path": module.join(metadata["root"], relative),
                      "parts": relative.split(module.sep), "size": size, "sha256": digest})
        if metadata["version"] in (5, 6, 7):
            files[-1]["mtime_ns"] = record[3]
    result = {**metadata, "files": files}
    if metadata["version"] in (3, 4, 5, 6, 7):
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


def validate_mode(snapshot):
    if snapshot.get("version") in (6, 7):
        root = snapshot.get("root")
        if not isinstance(root, str) or not root:
            raise ValueError("Invalid state root.")
        module = path_module(root)
        paths = snapshot.get("excluded_tool_paths")
        if (not isinstance(paths, list) or len(paths) > (7 if snapshot.get("version") == 7 else 5) or any(not isinstance(path, str)
                or not path or module.isabs(path) or module.splitdrive(path)[0]
                or any(part in ("", ".", "..") for part in path.replace("\\", "/").split("/"))
                or module.basename(path) not in ("states", "work", "runtime", ".states", "settings.json", DATA_DIRECTORY, "_internal")
                for path in paths)):
            raise ValueError("Invalid portable-data exclusions.")
    if snapshot.get("version") in (5, 6, 7):
        algorithms = {"quick": "none", "sampled": "sha256-sample-v1", "full": "sha256"}
        mode = snapshot.get("review_mode")
        if mode not in algorithms or snapshot.get("hash_algorithm") != algorithms[mode]:
            raise ValueError("Invalid state review mode or fingerprint algorithm.")
    elif snapshot.get("review_mode", "full") != "full" or snapshot.get("hash_algorithm", "sha256") != "sha256":
        raise ValueError("Legacy states require full SHA-256 fingerprints.")


def validate_coverage(snapshot):
    validate_mode(snapshot)
    if snapshot.get("version") not in (3, 4, 5, 6, 7):
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
        self.data = self.directory / DATA_DIRECTORY
        self.states = self.data / "states"
        self.legacy_states = self.directory / ".states"
        self.legacy_folders = (self.directory / "states", self.legacy_states)
        self.legacy_checked = False

    def ensure(self):
        from runtime_safety import ensure_managed_directory
        ensure_managed_directory(self.states, self.directory)

    def new_state_path(self):
        self.ensure()
        return self.states / ("state-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8] + EXTENSION)

    def new_report_path(self):
        return self.directory / "folder-change-review.xlsx"

    def list_states(self):
        items, errors = [], []
        seen = set()
        for folder in (self.states, *self.legacy_folders):
            if folder is None:
                continue
            try:
                if folder == self.states:
                    parent = os.lstat(extended(self.data))
                    if not stat.S_ISDIR(parent.st_mode) or getattr(parent, "st_file_attributes", 0) & 0x400:
                        errors.append("Portable data must be a real directory, not a link.")
                        continue
                info = os.lstat(extended(folder))
                if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    errors.append(f"{folder.name}: Portable history must be a real directory, not a link.")
                    continue
            except FileNotFoundError:
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
        for path in (self.data/"settings.json", self.directory/"settings.json", self.legacy_states/"settings.json"):
            try:
                parent = os.lstat(extended(path.parent))
                if not stat.S_ISDIR(parent.st_mode) or getattr(parent, "st_file_attributes", 0) & 0x400:
                    continue
                info = os.lstat(extended(path))
                if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    continue
                with open(extended(path), encoding="utf-8") as stream:
                    value = json.load(stream)
                if isinstance(value, dict):
                    value.pop("report_directory", None)
                    relative = value.pop("project_relative", None)
                    if isinstance(relative, str) and not os.path.isabs(relative) and ".." not in Path(relative).parts:
                        value["project"] = str(self.directory/relative)
                    return value
            except (OSError, ValueError):
                pass
        return {}

    def copy_legacy_states(self):
        """Background, read-only import; startup still reads small metadata only."""
        if self.legacy_checked or self.legacy_states is None:
            return
        from folder_change_review import staged_output
        for legacy in self.legacy_folders:
            folder = Path(extended(legacy))
            try:
                info = os.lstat(folder)
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                continue
            for source in folder.glob("*" + EXTENSION):
                target = self.states / source.name
                info = os.lstat(source)
                if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400 or Path(extended(target)).exists():
                    continue
                try:
                    with staged_output(target) as temporary:
                        shutil.copyfile(source, temporary)
                except OSError:
                    # An unreadable original remains visible for diagnostics.
                    continue
        self.legacy_checked = True

    def save_settings(self, value):
        from folder_change_review import staged_output
        self.ensure()
        self.copy_legacy_states()
        value = dict(value)
        value.pop("report_directory", None)
        value.pop("project_relative", None)
        if value.get("project"):
            try:
                relative = Path(absolute(value["project"])).relative_to(self.directory)
            except ValueError:
                pass
            else:
                value.pop("project")
                value["project_relative"] = str(relative)
        with staged_output(self.data / "settings.json") as temporary:
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
