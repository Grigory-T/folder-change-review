# Folder Change Review

A standalone Windows x86-64 tool for reviewing changes in a project folder.
Capture states manually, choose two capture times, and create plain Excel data
for your own pivot table. Local folders, SMB shares and mapped drives are supported.

## Windows EXE

Download `folder-change-review.exe` from [Releases](https://github.com/Grigory-T/folder-change-review/releases/latest).
No Python or installation is required.

1. Put the EXE in a writable folder. It may be inside the project or on an SMB share that allows EXE execution.
2. Double-click it, choose the project folder, leave **Quick review** selected and click **Create state**.
3. At another time, create another state of the same folder.
4. In **Compare saved states**, choose **Before (A)** and **After (B)**, then click **Create Excel report**.
5. **`folder-change-review.xlsx`** appears beside the EXE. Use **Choose report folder…** for another local or SMB destination. **Open report folder** opens the selected folder. A successful comparison atomically replaces the previous report.

The window has two independent numbered blocks: **Create a state** and
**Compare saved states**. You can compare existing captures without creating a
new state or having the project folder online. Each block has its own status;
progress appears only while that action is running and disappears afterward.
The selected A/B pair stays selected after comparison. Identical selections
disable the report button; a reverse-time selection is explained before running.

Aligned controls and scrolling cards support smaller windows and larger fonts.
The report-folder control stays visible. Long folder paths remain selectable
and can be scrolled horizontally for inspection.

Capture dates, file counts and review modes identify states in the chooser. State files and
settings are managed automatically under local `%LOCALAPPDATA%\FolderChangeReview\histories`, separately for each application-folder spelling, for both local and SMB EXEs. New states are always outside the inspected project. Legacy `.states` history beside a local EXE remains readable and is copied into the local cache during the next capture/report; originals remain untouched.
Keep that folder to retain history. States are compressed technical files, not
workbooks, and need no manual handling. They are not encrypted: keep your working
folder somewhere appropriate for the project data.

The default is **Quick review** with **16 read workers**. Folder enumeration is
parallel, with at most one pending folder job per worker. It reuses file metadata
returned by directory enumeration, without opening each file for content checks.
Try **32** workers for an SMB share; more workers do not guarantee faster results.
Content-reading modes bound their file queue to twice the worker count.
The interface stays responsive; progress is hidden while idle. Allow a running
operation to finish before closing.

Choose a review mode before creating a state:

| Mode | What is compared at the same path | Content read per file |
|---|---|---:|
| **Quick review (default)** | Size and modification time | None |
| **Sampled contents** | Size and SHA-256 of first, middle and last 64 KiB | At most 192 KiB |
| **Full contents** | Size and SHA-256 of complete contents | Entire file |

Quick review prioritizes speed. A timestamp-only change counts as Changed, and
an edit that preserves both size and modification time can be missed. Sampled
contents ignores timestamp-only changes but can miss edits outside its samples;
small files up to 192 KiB are sampled completely. Full contents retains the
strongest content comparison and its extra SMB reads. Neither approximate mode
claims to prove byte equality. No fingerprint is exported to Excel.

Use the **same mode for both states**. Different modes cannot be compared; the
chooser explains this and disables the report button. Existing states are
recognized as Full contents. Create two new Quick review states to use the fast
workflow; an old Full contents state cannot serve as a Quick review baseline.

## Comparison rules

Use the same root path spelling for both snapshots. Full paths are compared
exactly, including case and extension. No same-root validation or rename/move
detection is performed. A move is a deletion plus an addition. Same-path change
detection follows the selected mode above. Unchanged means that the selected
checks match, subject to that mode's stated limitations.

States store compressed relative paths, sizes, modification times and the selected
mode. Content modes also store internal fingerprints. ZIP/RAR/7z files are ordinary files, never expanded.
Case-insensitive filename exclusions: `~*`, `Thumbs.db`, `*.tmp`, `*.temp`.
Empty directories are irrelevant. Links, junctions and other reparse points
are skipped and their count is reported.

Unreadable subfolders and interrupted directory enumeration produce **read issues**.
Content modes also record read failures, locks and detected mutations. Quick review
does not test whether file contents can be opened; metadata-readable files are included. Capture continues and saves
readable files with explicit incomplete coverage. The UI shows the issue count
and a **Read issues…** button; state choices also identify incomplete captures.
No permissions are changed and administrator access is not required for normal
operation. A completely unavailable or unreadable root still fails capture.

Comparison uses **Unknown** when either state cannot establish a file's status.
Unknown rows have blank Added/Deleted/Changed flags, retain any known size, and
still have `last=1`. An unreadable folder never becomes a fake file row. If both
states cannot enumerate a folder, its filenames may be unknown to both: the
warning remains even if there are zero Unknown rows. Do not treat `last` as a
complete project file count when coverage is incomplete.

Reports with read issues contain a warning above the main data and a plain
**Read issues** worksheet with the affected state, path and OS reason. Reports
with complete coverage retain the existing single-sheet layout. Actual additions
and deletions outside unavailable scopes are still classified normally.

Output errors (including disk full, a locked report or unwritable storage) abort
and preserve the previous destination. Files are hashed up to their initial size
plus one growth probe; short reads accumulate, while growth, truncation or
observed metadata/identity changes become read issues. Each file is attempted
once: capture never keeps retrying a changing or locked file. A live scan is not
an atomic point-in-time filesystem snapshot. Network I/O timeouts are controlled
by Windows and the SMB connection.

New states use format version 5 with explicit mode/algorithm identifiers and a
separate read-issue inventory. Formats 1–4 remain readable as Full contents states.
Older EXEs reject version 5 rather than misinterpreting approximate fingerprints.

Comparison reads only saved states; the original project need not be online.
No same-root check is performed. Choose two states of the same project using
the same root path spelling.

## Local execution

The application makes no web requests, telemetry calls, update checks or runtime
downloads. Python socket/HTTP APIs and subprocess launches are blocked during
execution. SMB is accessed through ordinary Windows filesystem reads.
The EXE may be stored inside the project or on SMB; its process still runs on
the Windows machine and its unpacked runtime stays local. The SMB server must
grant Execute permission to launch an EXE directly from a share. Read/write-only
data shares can still hold projects and reports while the EXE runs locally.

States and processing workspaces stay local. Both local and SMB EXEs use the local machine cache. Keep a consistent
application path spelling to use the same cached history. Capture workspace selection avoids the inspected tree; comparison uses local
processing storage independently of the report folder and never resolves saved source roots. The one-file runtime unpacks under local user
application data before Python starts.

Only the selected Excel report and its atomic-save staging file are write
exceptions inside a project. State output inside the project is rejected. Other existing project files remain read-only to the
application. Saving a report may change its project directory timestamp; history uses the local machine cache. Output file
symlinks are rejected; mapped drives and junction parents are supported.

Reserved tool artifacts are omitted from captures and from comparisons of older
states: `.states` subtrees, `*.fcrstate`, `folder-change-review.exe`,
`folder-change-review.xlsx` and legacy `folder-changes-YYYYMMDD-HHMMSS-xxxxxx.xlsx`
reports. This prevents report/state updates from appearing as project changes.
These application checks are not an OS security sandbox.

## Excel

One sheet, `Changes`, follows the [Folder Review](https://github.com/Grigory-T/folder-review) flat-table layout:
title at B2, column numbering at row 4, review mode and limitations at B5, headers at row 6, data from row 7,
`Row number` first and `last` last. Headers are blue with black boundary headers.
The bordered body is white with no status colors. Calibri 11, 70% zoom, column widths of 5 character units,
rows 1–6 frozen at A7 without frozen columns, no merged cells, no Excel Table object and no saved pivot.
Header height is 72 points, matching Folder Review; ordinary row height is 14.5.
Column numbering and `Row number` are numeric, as in Folder Review. Columns
run from hierarchy/depth through adjacent names, extension, Size A/B/delta, Status
and Added/Deleted/Changed flags, ending with `last`. Headers and the title are
English; filenames and paths retain their original text.

The full union includes Added, Deleted, Changed, Unchanged and, when coverage is incomplete, Unknown files. Flags
`Added`, `Deleted`, `Changed` use numeric 1 or an empty cell, never zero.
`last=1` counts all file rows. No Leaf flag or SHA column is exported: content fingerprints, when enabled,
remain in machine snapshots solely for change detection. Extensions have no dot.
Each size has a numeric bytes column (`#,##0`) and a MiB column (`#,##0.000`):
**A bytes/MiB → B bytes/MiB → delta bytes/MiB**. MiB means bytes / 1,048,576.
Underlying precision is retained; displayed MiB uses three decimals as in Folder
Review. Missing A/B values are blank. Delta is B − A, treating only known absence
as zero: additions are positive, deletions negative, unchanged and equal-length
edits have zero delta. Unknown rows have blank delta. Never infer Changed from
size alone: the selected mode also checks modification time or contents.

The Read issues sheet shows each state's root once and relative issue paths.
Path conversion is lexical and never contacts the original project. Formula-like
filenames and diagnostic messages remain literal text.

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
For real Tk workflow/layout tests on headless Linux, prefix this command with
`xvfb-run -a`; UI tests skip if a display is unavailable.
openpyxl is a test reader only.

On Windows x86-64, `BUILD-EXE.bat` verifies and extracts the exact pinned
Python 3.13.16 archive, then installs hash-locked PyInstaller 6.22.3 wheels.
It needs neither a global Python nor uv and builds the windowed EXE in `dist`.
Building may download dependencies; the finished EXE does not.
See [audit and reproducible build instructions](docs/build.md),
[runtime/data boundaries](SECURITY.md) and [third-party notices](THIRD-PARTY-NOTICES.md).
The unused XML parser and development reader are excluded from production.

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
timings. Add `--mode sampled` or `--mode full` to either snapshot command for
content checks; the default is `--mode quick`. The normal desktop workflow manages all filenames automatically.

See [performance analysis and measurements](docs/performance.md) and
[validation](docs/validation.md) for release checks and measured results.

## Additional Windows validation

`BUILD-TEST-EXE.bat` builds a separate, development-only frozen runner after
`BUILD-EXE.bat`. It executes the complete core/Tk suite and rejects skipped tests:

```powershell
.\dist\folder-change-review-tests.exe --results C:\Review\frozen-suite.json
```

The test runner and its reader/test dependencies are not included in the
production EXE or release. `tests/windows_placement_acceptance.py` exercises
in-project placement, long input/output paths, junction aliases, fixed-name
replacement and SMB reporting using only disposable fixtures. A share that
denies EXE execution is reported separately; its permissions are not changed by
the harness. Run `tests/windows_failure_acceptance.py` without elevation for real
normal-user ACL/lock acceptance.
