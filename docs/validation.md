# v0.3.0 validation

Verified on native Windows 11 x86-64; Windows 10 was not tested.
The [machine-readable receipt](validation.json) contains generic synthetic
results, dependency versions, source checksums and the executable checksum.
No real project inventory, machine name, user profile or network address is published.

## Correctness and stability

- 17 focused tests passed on both Linux and Windows. Coverage includes exact
  full-path unions, same-size content edits, moves, timestamps, archives as files,
  exclusions, literal/Unicode filenames, lowest common ancestor, workbook layout,
  compressed states, metadata-only history, legacy JSON reading, corrupt history,
  bounded queue, serial/16/32-worker record equality and offline comparison.
- Failed captures and reports preserve existing output. A real Windows sharing
  violation aborted capture, preserved the previous state, removed staging files
  and succeeded after the file was unlocked.
- The production GUI created three states, explicitly selected the two older
  captures in the chooser and exported beside its own EXE. Native Excel
  opened the GUI report normally and verified pivot totals. No application TCP
  connections were observed during the GUI check.
- The 5,002-row SMB comparison opened normally in Excel with `CorruptLoad=0`.
  A temporary pivot produced Added=2, Deleted=2, Changed=1 and total files=5,002.
  Changed-file drill-down identified the expected filename. Reports were closed
  without saving; test pivots are not part of the delivered output.
- Native format checks covered the plain data range, headers, numbering, white
  body, numeric 1/blank flags, two-decimal MB formats, extension spelling and
  absence of native Table objects, SHA/full-path columns and frozen panes.

## SMB measurement

The test creates and removes only its own unique synthetic directory on an
existing SMB share. It does not inventory or modify other share contents.
Dataset: 5,000 files, 327,698,890 bytes, 40 areas and seven sections per area;
ordinary PDF/Office/archive filenames, three excluded files and an empty folder.

| Capture | Workers | End-to-end seconds | Scan/hash seconds |
| --- | ---: | ---: | ---: |
| Python | 16 | 7.36 | — |
| EXE, first | 16 | 8.54 | 7.17 |
| EXE, second | 16 | 8.73 | 7.41 |
| EXE, first | 32 | 6.66 | 5.46 |
| EXE, second | 32 | 7.00 | 5.66 |

EXE wall time includes one-file startup/unpacking. All five inventories matched.
A same-length edit, deletion, move and new file produced exactly 2 Added,
2 Deleted, 1 Changed and 4,997 Unchanged. Comparison/export took 1.81 seconds.
Saved-state comparison also succeeded after deleting the synthetic source tree.
An attempted state output inside the project was rejected without creating it.

One compressed state was 239,690 bytes versus 1,367,153 bytes for the equivalent
old JSON representation (about 82.5% smaller). Caches were not cleared. These are
observations from this setup, not a universal network or storage benchmark.
The default stays at 16 workers; 32 is available for shares that benefit.

## Packaging

One windowed PyInstaller EXE bundles CPython, Tcl/Tk, XlsxWriter and applicable
license notices. No Python installation, archive utility or runtime download is
required. Build dependencies and runtime writer are hash-locked. A second
clean build on the same Windows setup produced an identical EXE.
Embedded project bytecode matches source, all 389 distinct Python code filenames
are relative, and 1,347 decompressed payloads were scanned for private build and
validation identifiers. Source history is published from a clean generic root;
private prototype history, inventories, screenshots and raw logs are excluded.

## Repeating checks

Run unit tests using the README commands. On Windows, after building:

```powershell
.\.build-venv\Scripts\python.exe windows_build\inspect_exe.py dist\folder-change-review.exe
.\.venv\Scripts\python.exe tests\windows_acceptance.py --exe C:\Review\folder-change-review.exe --work C:\Review\Validation --share \\server\share
.\.venv\Scripts\python.exe tests\windows_failure_acceptance.py --exe C:\Review\folder-change-review.exe --work C:\Review\Failures
```

The SMB test intentionally writes its own synthetic test files and removes that
unique directory afterward. Application project captures themselves are read-only.
Native Excel validation is in `tests/excel_acceptance.py`; it requires an
interactive Windows session and separately installed pywin32, neither of which
is required by the product.
