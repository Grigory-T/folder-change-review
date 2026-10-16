# v0.3.1 validation

Verified on native Windows 11 x86-64. The [machine-readable receipt](validation.json)
contains generic synthetic results, dependency versions, source checksums and
executable checksum. No real inventory, machine name, user profile or network
address is published. Windows 10 was not tested.

## Scope

Three changes: bounded SHA-256 reads with mutation detection, English workbook
headers/title, and column order matching Folder Review's hierarchy → names →
extension → sizes → status/change flags → last. Existing SHA-256 states remain
compatible. No hash column, file-type groups or archive inspection was added.

## Focused tests

All **26 tests passed on Linux and Windows source**. In addition to existing
union, exclusion, archive-as-file, LCA, literal text, compressed state, history,
queue and output-preservation coverage, regression cases verify:

- Stable zero-byte, one-byte and hash-buffer-boundary files match independent SHA-256.
- Short positive reads are valid and are accumulated correctly.
- Continuously growing streams stop after initial size plus one probe byte,
  even when metadata appears unchanged. Growth from zero length is detected.
- Premature EOF, read errors, same-length metadata changes and path identity
  changes reject the capture. Previous state bytes and staging cleanup are checked.
- Windows can expose different `ctime` meanings in `fstat()` and path `stat()`.
  The implementation compares change time through the same API on Windows,
  avoiding false mutation errors for stable rewritten files.
- Exact English column order, title/LCA, nested levels, multi-suffix Unicode
  names, all four statuses, correctly aligned before/after sizes, numeric zero
  versus missing sizes, unrounded underlying precision and 1/blank flags.

The growing/short/truncated stream tests use deterministic controlled readers,
not scheduler-sensitive races. Read bounds are asserted directly. OS metadata
is controlled separately so the EOF/growth checks cannot pass only because a
later stat happened to notice a change.

## Production EXE differential checks

The validation method follows Folder Review's source/frozen comparisons:
**13 scenarios** match every XLSX ZIP member, including cells, types, styles,
layout and filters. Only workbook creation/modification timestamps are normalized.
Snapshot file records also match. Cases cover empty/single input, all statuses
and moves, nested LCA, Unicode/formula-like/OOXML-escape-like filenames,
extensionless/dotfiles, opaque archives, exclusions, all-added/all-deleted,
buffer boundaries, timestamp-only changes and previous v0.3.0 EXE states.

**Seven failure cases** match source/EXE exit codes: unavailable input, output
inside input, invalid worker counts at both ends, corrupt/missing states and
wrong report extension. Existing report bytes survive; staging is cleaned.
A real Windows exclusive file lock also aborts, preserves the previous state
and succeeds after unlocking.

## Native GUI and Excel

The production GUI created three states, switched to 32 workers, selected two
older states explicitly and exported beside the EXE. No application TCP
connections were observed. Native Excel opened the GUI report and verified
pivot totals; its actual rendered header/body layout was inspected.

Five further native Excel cases cover empty, single unchanged, all statuses,
Unicode/literal text and nested LCA. A seventh check covers the 5,002-row SMB
report. Workbooks open normally with `CorruptLoad=0`, no Table objects or formulas,
English headers in exact order, white body, numeric 1/blank flags, MiB formatting,
no SHA/full-path column and no frozen panes. Literal filenames, including
`literal_x000D_.txt` and a Unicode/emoji filename, retain their exact Excel text.
Temporary pivots verify sums and changed-file drill-down and are discarded.
For a category whose source flags are all blank, Excel may display a blank
zero total; validation explicitly distinguishes that from a nonzero mismatch.
Reports are closed without saving, and their byte checksums remain unchanged.

## SMB stability and speed

A unique synthetic subfolder on an existing SMB share contains **5,000 files /
327,698,890 bytes**, three excluded files and an empty folder. Only that owned
fixture is created/removed; existing share data and server configuration are
untouched. Runtime, states and reports stay local.

| Delivery/run | Workers | End-to-end seconds | Scan/hash seconds |
| --- | ---: | ---: | ---: |
| Python | 16 | 7.47 | — |
| EXE first | 16 | 8.64 | 7.41 |
| EXE second | 16 | 8.57 | 7.34 |
| EXE first | 32 | 7.14 | 5.93 |
| EXE second | 32 | 6.99 | 5.74 |

All five inventories match. Controlled changes produce **2 Added, 2 Deleted,
1 Changed, 4,997 Unchanged** in **5,002 union rows**. Compare/export took
**1.74 seconds**. A compressed state was **239,686 bytes** versus **1,367,153
bytes** for old JSON. Comparison succeeds after the synthetic source is removed;
inside-project output is rejected without creating a file.

Observed timings remain comparable to v0.3.0. Caches were not cleared and these
are setup-specific measurements, not a universal performance guarantee. EXE
wall times include one-file startup/unpacking. Default workers remain 16, with 32
available; pending jobs remain bounded to twice the worker count.

## Packaging and repeating checks

One windowed PyInstaller EXE bundles Python, Tcl/Tk, XlsxWriter and applicable
license notices. Runtime/build dependencies are unchanged and hash-locked.
A second clean build on the same Windows setup produced a byte-identical EXE.
Embedded application bytecode matches source, all 389 distinct Python code
filenames are relative, and 1,347 decompressed payloads passed private-token audit.
Private inventories, screenshots, host identifiers and raw logs stay unpublished.

Run unit tests using the README commands. After building on Windows:

```powershell
.\.build-venv\Scripts\python.exe windows_build\inspect_exe.py dist\folder-change-review.exe
.\.venv\Scripts\python.exe windows_build\verify.py --exe C:\Review\folder-change-review.exe --results C:\Review\Parity
.\.venv\Scripts\python.exe tests\windows_acceptance.py --exe C:\Review\folder-change-review.exe --work C:\Review\Validation --share \\server\share
.\.venv\Scripts\python.exe tests\windows_failure_acceptance.py --exe C:\Review\folder-change-review.exe --work C:\Review\Failures
```

`verify.py --previous-exe ...` also checks previous-release state compatibility.
The SMB validator deliberately writes/removes only its unique synthetic directory;
application captures themselves are read-only. `tests/excel_acceptance.py` needs
an interactive Windows session and separately installed pywin32, which is not a
product dependency.
