"""Manual folder snapshots and full-path/SHA-256 comparison for Excel."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import ntpath
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import zipfile

from runtime_safety import absolute, application_directory, extended, inside, offline_runtime, require_local, safe_operation
from state_store import read_container, write_container

sys.dont_write_bytecode = True
VERSION = "0.4.0"
SNAPSHOT_FORMAT = "folder-change-review.snapshot"
EXCLUSIONS = ["~*", "Thumbs.db", "*.tmp", "*.temp"]
MAX_DATA_ROWS = 1_048_570  # header row 6, data from row 7
DEFAULT_WORKERS = 16
HASH_BUFFER_SIZE = 256 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ignored(name: str) -> bool:
    name = name.lower()
    return name.startswith("~") or name == "thumbs.db" or name.endswith((".tmp", ".temp"))


@contextmanager
def staged_output(output: str | Path):
    """Replace the final file only after successful completion."""
    target = absolute(output)
    parent = os.path.dirname(target)
    require_local(parent)
    if not os.path.isdir(extended(parent)):
        raise ValueError(f"Output folder does not exist: {parent}")
    descriptor, temporary = tempfile.mkstemp(prefix=".folder-change-review-", dir=extended(parent))
    os.close(descriptor)
    try:
        yield temporary
        os.replace(temporary, extended(target))
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def hash_file(path: str) -> tuple[str, int]:
    error = f"File changed while being hashed. Retry the snapshot: {path}"
    with open(extended(path), "rb") as stream:
        before = os.fstat(stream.fileno())
        digest = hashlib.sha256()
        remaining = before.st_size
        buffer = bytearray(min(HASH_BUFFER_SIZE, remaining))
        view = memoryview(buffer)
        # Never chase a growing file to EOF. Read its initial size, then probe
        # one byte for growth. A short positive read is valid, even over SMB.
        while remaining:
            count = stream.readinto(view[:min(len(view), remaining)])
            if not count:
                raise OSError(error)
            digest.update(view[:count])
            remaining -= count
        grew = bool(stream.read(1))
        after = os.fstat(stream.fileno())
    current = os.stat(extended(path), follow_symlinks=False)
    def identity(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    metadata_changed = before.st_ctime_ns != after.st_ctime_ns
    # On Windows, fstat() can expose change time while stat() exposes creation
    # time as ctime. Compare ctime only through the same API there.
    if os.name != "nt":
        metadata_changed |= after.st_ctime_ns != current.st_ctime_ns
    if grew or metadata_changed or identity(before) != identity(after) or identity(after) != identity(current):
        raise OSError(error)
    return digest.hexdigest(), after.st_size


def scan_files(root: str, stats: dict):
    """Yield files without following links or retaining a separate job list."""
    pending = [(root, ())]
    while pending:
        folder, parts = pending.pop()
        with os.scandir(extended(folder)) as entries:
            for entry in entries:
                path = os.path.join(folder, entry.name)
                properties = entry.stat(follow_symlinks=False)
                reparse = getattr(properties, "st_file_attributes", 0) & 0x400
                if entry.is_symlink() or reparse:
                    stats["skipped_links"] += 1
                    continue
                if stat.S_ISDIR(properties.st_mode):
                    pending.append((path, parts + (entry.name,)))
                elif stat.S_ISREG(properties.st_mode):
                    if ignored(entry.name):
                        stats["excluded_files"] += 1
                        continue
                    yield path, [*parts, entry.name]
                else:
                    raise OSError(f"Unsupported filesystem item: {path}")


def create_snapshot(root: str | Path, output: str | Path, workers: int = DEFAULT_WORKERS, progress=None) -> dict:
    with safe_operation((root,), os.path.dirname(absolute(output))):
        return _create_snapshot(root, output, workers, progress)


def _create_snapshot(root, output, workers, progress):
    root = absolute(root)
    if not 1 <= workers <= 32:
        raise ValueError("Workers must be between 1 and 32.")
    if not os.path.isdir(extended(root)):
        raise ValueError(f"Project folder is unavailable: {root}")
    if inside(output, root):
        raise ValueError("Save snapshots outside the project folder being scanned.")
    started, timer = now(), time.perf_counter()
    stats = {"excluded_files": 0, "skipped_links": 0}
    files = []
    jobs = scan_files(root, stats)
    def record(job, result):
        path, parts = job
        digest, size = result
        files.append({"path": path, "parts": parts, "sha256": digest, "size": size})
        if len(files) % 1000 == 0:
            emit(f"Hashed {len(files):,} files...", progress)
    try:
        if workers == 1:
            for job in jobs:
                record(job, hash_file(job[0]))
        else:
            # Bound both concurrent reads and queued work, even for huge trees.
            with ThreadPoolExecutor(max_workers=workers) as executor:
                pending = {}
                exhausted = False
                try:
                    while pending or not exhausted:
                        while not exhausted and len(pending) < workers * 2:
                            job = next(jobs, None)
                            if job is None:
                                exhausted = True
                            else:
                                pending[executor.submit(hash_file, job[0])] = job
                        if pending:
                            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                            for future in completed:
                                record(pending.pop(future), future.result())
                finally:
                    for future in pending:
                        future.cancel()
    finally:
        jobs.close()
    hash_seconds = time.perf_counter() - timer
    files.sort(key=lambda record: record["path"])
    snapshot = {"format": SNAPSHOT_FORMAT, "version": 2, "hash_algorithm": "sha256", "root": root,
                "started_utc": started, "completed_utc": now(),
                "exclusions": EXCLUSIONS, **stats, "files": files, "file_count": len(files),
                "statistics": {"workers": workers, "bytes": sum(row["size"] for row in files),
                               "scan_hash_seconds": hash_seconds}}
    with staged_output(output) as temporary:
        write_container(temporary, snapshot)
    emit(f"State created: {len(files):,} files; excluded: {stats['excluded_files']:,}; links skipped: {stats['skipped_links']:,}", progress)
    emit(f"Scan/hash: {hash_seconds:.2f}s; total: {time.perf_counter() - timer:.2f}s; workers: {workers}", progress)
    return snapshot


def load_snapshot(path: str | Path) -> dict:
    require_local(path)
    if zipfile.is_zipfile(extended(path)):
        snapshot = read_container(path)
    else:
        # Read compatibility for earlier machine JSON states; new states are compressed.
        with open(extended(path), encoding="utf-8") as stream:
            snapshot = json.load(stream)
    if snapshot.get("format") != SNAPSHOT_FORMAT or snapshot.get("version") not in (1, 2):
        raise ValueError(f"Unsupported snapshot format: {path}")
    seen = set()
    for record in snapshot["files"]:
        full_path, parts, digest, size = (record[key] for key in ("path", "parts", "sha256", "size"))
        if (not isinstance(full_path, str) or not full_path
                or not isinstance(parts, list) or not parts
                or not all(isinstance(part, str) and part for part in parts)
                or not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
                or type(size) is not int or size < 0):
            raise ValueError(f"Invalid file record in snapshot: {path}")
        if full_path in seen:
            raise ValueError(f"Duplicate full path in snapshot: {full_path}")
        seen.add(full_path)
    return snapshot


def compare_snapshots(before: dict, after: dict) -> list[dict]:
    # Exact stored full-path matching. No root checks or move/rename detection.
    old = {record["path"]: record for record in before["files"]}
    new = {record["path"]: record for record in after["files"]}
    rows = []
    for path in sorted(old.keys() | new.keys()):
        a, b = old.get(path), new.get(path)
        if a is None:
            status = "Added"
        elif b is None:
            status = "Deleted"
        elif a["sha256"] != b["sha256"]:
            status = "Changed"
        else:
            status = "Unchanged"
        record = b if b is not None else a
        filename = record["parts"][-1]
        rows.append({"parts": record["parts"], "FullPath": path, "FileName": filename,
                     "Extension": os.path.splitext(filename)[1].lstrip(".").lower(), "Status": status,
                     "Added": 1 if status == "Added" else None,
                     "Deleted": 1 if status == "Deleted" else None,
                     "Changed": 1 if status == "Changed" else None,
                     "SizeA": None if a is None else a["size"],
                     "SizeB": None if b is None else b["size"]})
    return rows


def report_hierarchy(rows: list[dict], root_hint: str = "") -> tuple[str, list[list[str]]]:
    """LCA of union file parents; single-file LCA is its folder, never the file."""
    if not rows:
        return root_hint, []
    paths = [row["FullPath"] for row in rows]
    path_module = ntpath if ntpath.splitdrive(paths[0])[0] or paths[0].startswith("\\\\") else os.path
    try:
        ancestor = path_module.commonpath([path_module.dirname(path) for path in paths])
    except ValueError:
        ancestor = ""  # roots are intentionally not validated
    if ancestor:
        parts = [path_module.relpath(path, ancestor).split(path_module.sep) for path in paths]
    else:
        parts = [list(row["parts"]) for row in rows]
    return ancestor, parts


def write_report(rows: list[dict], output: str | Path, root_hint: str = "") -> None:
    import xlsxwriter

    if len(rows) > MAX_DATA_ROWS:
        raise ValueError(f"Union has {len(rows):,} files; one worksheet allows {MAX_DATA_ROWS:,} data rows.")
    ancestor, paths = report_hierarchy(rows, root_hint)
    depth = max((len(parts) for parts in paths), default=1)
    fields = ["Leaf depth", "Name without extension", "File name", "Extension",
              "Size A (MiB)", "Size B (MiB)", "Status", "Added", "Deleted", "Changed"]
    headers = ["Row number", *[f"Level {index}" for index in range(1, depth + 1)], *fields, "last"]
    if len(headers) + 1 > 16_384:  # column A is blank
        raise ValueError("Folder hierarchy exceeds Excel's column limit.")
    with staged_output(output) as temporary:
        with xlsxwriter.Workbook(temporary, {
            "constant_memory": True, "strings_to_formulas": False,
            "strings_to_urls": False, "strings_to_numbers": False,
            "tmpdir": os.path.dirname(extended(output)),
        }) as workbook:
            workbook.set_calc_mode("auto", 191029)
            workbook.set_size(1484, 843)
            workbook.set_tab_ratio(92.8)
            sheet = workbook.add_worksheet("Changes")
            sheet.hide_gridlines(2)
            sheet.set_zoom(85)
            sheet.set_tab_color("#002060")
            sheet.outline_settings(True, False, False, False)
            sheet.set_default_row(14.5)
            sheet.set_portrait()
            sheet.set_paper(9)
            sheet.set_margins(0.7, 0.75, 0.75, 0.75)
            sheet.set_header("", {"margin": 0.3})
            sheet.set_footer("", {"margin": 0.3})
            font = {"font_name": "Calibri", "font_size": 11, "font_color": "#000000"}
            border = {**font, "border": 1, "border_color": "#000000"}
            body = workbook.add_format(border)
            centered = workbook.add_format({**border, "align": "center", "valign": "vcenter"})
            size_format = workbook.add_format({**border, "num_format": "#,##0.00"})
            title = workbook.add_format({**font, "bold": True})
            header_format = {**border, "bold": True, "align": "center", "valign": "vcenter", "text_wrap": True}
            header = workbook.add_format({**header_format, "bg_color": "#00B0F0"})
            boundary = workbook.add_format({**header_format, "bg_color": "#000000", "font_color": "#FFFFFF"})
            sheet.set_column(0, 0, 5.81640625 - 5 / 7)
            widths = {"Row number": 9, "Name without extension": 20, "File name": 24}
            for column, text in enumerate(headers, 1):
                width = widths.get(text, 5.81640625 if column in (1, len(headers)) else 12.54296875)
                sheet.set_column(column, column, width - 5 / 7)
            # Match the accepted Folder Review layout, including its taller header.
            sheet.set_row(5, 72)
            sheet.write_string(1, 1, f"Table: File changes in folder {ancestor or root_hint}", title)
            for column, text in enumerate(headers, 1):
                sheet.write_number(3, column, column, centered)
            for column, text in enumerate(headers, 1):
                sheet.write_string(5, column, text, boundary if column in (1, len(headers)) else header)
            for index, row in enumerate(rows, 1):
                parts = paths[index - 1]
                values = [index, *parts, *([None] * (depth - len(parts))), len(parts),
                          ntpath.splitext(row["FileName"])[0], row["FileName"], row["Extension"],
                          None if row["SizeA"] is None else row["SizeA"] / (1024 * 1024),
                          None if row["SizeB"] is None else row["SizeB"] / (1024 * 1024),
                          row["Status"], row["Added"], row["Deleted"], row["Changed"], 1]
                for column, value in enumerate(values, 1):
                    label = headers[column - 1]
                    fmt = size_format if label in ("Size A (MiB)", "Size B (MiB)") else centered if label in (
                        "Row number", "last", "Leaf depth", "Extension", "Status", "Added", "Deleted", "Changed"
                    ) else body
                    if isinstance(value, str):
                        result = sheet.write_string(index + 5, column, value, fmt)
                        if result != 0:
                            raise ValueError(f"Text cannot fit in an Excel cell: {row['FullPath']}")
                    elif value is not None:
                        sheet.write_number(index + 5, column, value, fmt)
                    else:
                        sheet.write_blank(index + 5, column, None, fmt)
            sheet.autofilter(5, 1, 5 + len(rows), len(headers))
            sheet.set_selection("B6")


def compare_files(before_path: str | Path, after_path: str | Path, output: str | Path, progress=None) -> Counter:
    target = absolute(output)
    if os.path.splitext(target)[1].lower() != ".xlsx":
        raise ValueError("Comparison output must have an .xlsx extension.")
    if any(os.path.normcase(target) == os.path.normcase(absolute(path)) for path in (before_path, after_path)):
        raise ValueError("Comparison output must not replace a snapshot.")
    started = time.perf_counter()
    before, after = load_snapshot(before_path), load_snapshot(after_path)
    # Comparing saved states must not resolve or contact their original SMB roots.
    for snapshot in (before, after):
        try:
            common = os.path.commonpath((os.path.normcase(target), os.path.normcase(snapshot["root"])))
        except ValueError:  # Different drives cannot overlap.
            continue
        if common == os.path.normcase(snapshot["root"]):
            raise ValueError("Save the Excel report outside the project folder.")
    rows = compare_snapshots(before, after)
    comparison_seconds = time.perf_counter() - started
    writing_started = time.perf_counter()
    emit("Writing the Excel report...", progress)
    with safe_operation((), os.path.dirname(target)):
        write_report(rows, target, after.get("root", before.get("root", "")))
    counts = Counter(row["Status"] for row in rows)
    emit(f"Union: {len(rows):,} files", progress)
    emit(" | ".join(f"{status}: {counts[status]:,}" for status in ("Added", "Deleted", "Changed", "Unchanged")), progress)
    emit(f"Load/compare: {comparison_seconds:.2f}s; Excel: {time.perf_counter() - writing_started:.2f}s; total: {time.perf_counter() - started:.2f}s", progress)
    return counts


def emit(text, progress=None):
    if progress is not None:
        progress(text)
    elif sys.stdout is not None:
        print(text, flush=True)


def _main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    arguments = sys.argv[1:] if argv is None else argv
    try:
        if not arguments:
            from folder_change_review_ui import launch
            launch()
        else:
            parser = argparse.ArgumentParser(description=__doc__)
            parser.add_argument("--version", action="version", version=VERSION)
            commands = parser.add_subparsers(dest="command", required=True)
            snapshot = commands.add_parser("snapshot", help="Create a compressed machine state")
            snapshot.add_argument("--root", required=True)
            snapshot.add_argument("--output", required=True)
            snapshot.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                                  help="Concurrent file hashing (1..32, default: 16)")
            compare = commands.add_parser("compare", help="Compare two snapshots and write plain Excel data")
            compare.add_argument("--before", required=True)
            compare.add_argument("--after", required=True)
            compare.add_argument("--output", required=True)
            args = parser.parse_args(arguments)
            if args.command == "snapshot":
                create_snapshot(args.root, args.output, args.workers)
            else:
                compare_files(args.before, args.after, args.output)
        result = 0
    except KeyboardInterrupt:
        if sys.stderr is not None:
            print("Cancelled.", file=sys.stderr)
        result = 130
    except Exception as error:
        if not arguments and os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(error), "Folder Change Review", 0x10)
        elif sys.stderr is not None:
            print(f"ERROR: {error}", file=sys.stderr)
        result = 1
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        with offline_runtime(application_directory()):
            return _main(argv)
    except Exception as error:
        if not (sys.argv[1:] if argv is None else argv) and os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(error), "Folder Change Review", 0x10)
        elif sys.stderr is not None:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
