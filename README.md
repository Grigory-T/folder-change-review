# Folder Change Review

A standalone Windows x86-64 tool for reviewing changes in a project folder.
Capture states manually, choose two capture times, and create plain Excel data
for your own pivot table. Local folders, SMB shares and mapped drives are supported.

## Windows EXE

Download `folder-change-review.exe` from [Releases](https://github.com/Grigory-T/folder-change-review/releases/latest).
No Python or installation is required.

1. Put the EXE in a separate **local** folder outside the project.
2. Double-click it, choose the project folder and click **Create state**.
3. At another time, create another state of the same folder.
4. Choose **Earlier state (A)** and **Later state (B)** from the lists, then click **Compare states**.
5. The `.xlsx` report appears beside the EXE. **Open report folder** opens that folder.

Capture dates and file counts identify states in the chooser. State files and
settings are managed automatically in a hidden `.states` folder beside the EXE.
Keep that folder to retain history. States are compressed technical files, not
workbooks, and need no manual handling. They are not encrypted: keep your working
folder somewhere appropriate for the project data.

The default is **16 hashing workers**; choose **32** for a network share if it
helps. The pending queue is bounded to twice the worker count. More workers do
not guarantee faster results: server, network and disk capacity determine speed.
Every included file is fully read on every capture. The interface remains
responsive while a capture or comparison runs. Allow it to finish before closing.

## Comparison rules

Use the same root path spelling for both snapshots. Full paths are compared
exactly, including case and extension. No same-root validation or rename/move
detection is performed. A move is a deletion plus an addition. Matching paths
with different SHA-256 hashes are Changed. Matching hashes are Unchanged,
including when only filesystem timestamps differ.

States store compressed relative paths, sizes and internal SHA-256 digests. Each included
file is read fully. ZIP/RAR/7z files are ordinary files, never expanded.
Case-insensitive filename exclusions: `~*`, `Thumbs.db`, `*.tmp`, `*.temp`.
Empty directories are irrelevant. Links, junctions and other reparse points
are skipped and their count is reported. Other read/enumeration failures abort
the snapshot, preserving an existing output. Basic file-change detection during
hashing reads only the initial file size plus a one-byte growth probe, and
rejects premature EOF or observed size, modification-time, change-time and
identity changes. A continuously growing file is not read indefinitely. A live
scan is not an atomic point-in-time filesystem snapshot.

Comparison reads only saved states; the original project need not be online.
No same-root check is performed. Choose two states of the same project using
the same root path spelling.

## Local execution

The application makes no web requests, telemetry calls, update checks or runtime
downloads. Python socket/HTTP APIs and subprocess launches are blocked during
execution. SMB is accessed through ordinary Windows filesystem reads.
The application folder, states, reports and temporary working files must be on
local storage. Running the EXE from a share is rejected. The selected project
is read-only to the application. The single-file runtime unpacks under the local
user application-data directory before Python starts. These application checks
are not an OS security sandbox.

## Excel

One sheet, `Changes`, follows the [Folder Review](https://github.com/Grigory-T/folder-review) flat-table layout:
title at B2, column numbering at row 4, headers at row 6, data from row 7,
`Row number` first and `last` last. Headers are blue with black boundary headers.
The bordered body is white with no status colors. Calibri 11, 85% zoom, no
frozen panes, no merged cells, no Excel Table object and no saved pivot.
Header height is 72 points, matching Folder Review; ordinary row height is 14.5.
Column numbering and `Row number` are numeric, as in Folder Review. Columns
run from hierarchy/depth through adjacent names, extension, Size A/B, Status
and Added/Deleted/Changed flags, ending with `last`. Headers and the title are
English; filenames and paths retain their original text.

The full union includes Added, Deleted, Changed and Unchanged files. Flags
`Added`, `Deleted`, `Changed` use numeric 1 or an empty cell, never zero.
`last=1` counts all file rows. No Leaf flag or SHA column is exported: hashes
remain in machine snapshots solely for change detection. Extensions have no dot.
`Size A (MiB)`/`Size B (MiB)` contain numeric sizes divided by 1,048,576,
displayed with two decimal places; absent files have blank sizes. Underlying
precision is retained for accurate sums. Format pivot size values to two
decimal places if Excel does not inherit that number format.

Select the filtered range starting at B6 and choose Insert > PivotTable.
Use `Level 1`, `Level 2`, etc. as Rows and sums of `Added`, `Deleted`,
`Changed` as Values. Sum `last` for total files. Filter on `Status` or
`Extension` as needed. With 1/blank flags, Excel may show a blank total when
a change category has no files; this means zero.

The report computes the lowest common ancestor of all union file directories,
including deleted branches. That full directory appears once in the title;
hierarchy columns contain only the remaining path components, including the
filename at its depth. Single-file comparisons use the file's parent directory.
No full-path column is repeated. Reconstruct a path from the title's directory
plus the row's nonempty hierarchy levels. This presentation does not change
the exact full-path comparison key. Empty reports use the snapshot root title.

XlsxWriter constant-memory is the sole production writer. Strings remain
literal text. Outputs are replaced only after successful creation. The union
must fit in one worksheet (1,048,570 file rows beneath row 6); oversize output
fails instead of truncating. File lists and the union are held in memory.

## Source and build

The supported delivery is a single PyInstaller EXE for Windows x86-64.
XlsxWriter 3.2.9 is the sole production writer. Archive utilities are not bundled.
The desktop UI uses the bundled Python/Tcl/Tk runtime.

For development, install [uv](https://docs.astral.sh/uv/) and run `SETUP.bat`
once; this setup step may access the internet. `RUN.bat` subsequently runs the
prepared local Python environment without downloading anything.
On other platforms: `uv sync --frozen --group test`, then
`uv run --offline --group test python -B -m unittest discover -s tests -v`.
openpyxl is a test reader only.

On Windows x86-64, `BUILD-EXE.bat` prepares Python 3.13.14 and hash-locked
PyInstaller 6.22.0 build dependencies. It builds the windowed EXE in `dist`.
Building may download dependencies; the finished EXE does not.

For scripted local testing, the same EXE also accepts:

```powershell
$p = Start-Process .\folder-change-review.exe -ArgumentList 'snapshot --root C:\Projects\Example --output C:\Review\A.fcrstate --workers 16' -Wait -PassThru
$p.ExitCode
# Later:
Start-Process .\folder-change-review.exe -ArgumentList 'snapshot --root C:\Projects\Example --output C:\Review\B.fcrstate --workers 32' -Wait
Start-Process .\folder-change-review.exe -ArgumentList 'compare --before C:\Review\A.fcrstate --after C:\Review\B.fcrstate --output C:\Review\changes.xlsx' -Wait
```

The windowed EXE has no console output; script callers must wait for it and check
its exit code (0 success, 1 error). The source CLI prints detailed errors and
timings. The normal desktop workflow manages all filenames automatically.

See [validation](docs/validation.md) for release checks and measured results.
