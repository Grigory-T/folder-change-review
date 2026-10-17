# v0.6.0 validation

The [machine-readable receipt](validation.json) contains aggregate results and
checksums. Private inventories, paths, screenshots and raw logs are excluded from
source and releases. Tested target: Windows 11 x86-64. Windows 10 remains untested.

## Approved changes

- Sizes follow Folder Review: numeric bytes and MiB for A, B and B − A. Bytes
  display `#,##0`; MiB display `#,##0.000`, retaining full numeric precision.
  Known absence is zero for delta; Unknown rows have blank delta. Equal-length
  edits remain Changed through internal SHA-256, independently of size.
- Fixed `folder-change-review.xlsx`, atomic replacement and useful Excel-lock
  messages. Failed saves preserve the previous report and remove staging.
- Main columns width 5, zoom 70%, freeze rows 1–6 at A7 without frozen columns.
  Existing hierarchy/name/status order, LCA title, white body, numeric 1/blank
  flags and `last=1` remain. No native Table, saved pivot or hash column.
- Read issues shows A/B roots once and relative paths. Conversion is lexical:
  offline comparison never resolves or contacts the original source.
- Matching surrounding single/double quotes are removed at user-input boundaries;
  internal filenames retain literal whitespace and quote characters.
- A separate development-only frozen runner executes the entire unit/Tk suite.
  Production excludes its reader and test dependencies.

## Flexible placement and safeguards

The EXE and reports may be inside the inspected project or on SMB. A report-folder
chooser supports another local or SMB destination. States/settings remain local:
`.states` beside a local EXE, or a per-application-folder cache under local user
application data for an SMB EXE. The unpacked runtime and processing workspace
remain local and outside the inspected tree. Comparison only needs saved states.

Only selected outputs and their exact staging paths are write exceptions inside
an inspected tree. Other project content remains read-only to the application.
Output-file symlinks are rejected; directory junction parents and mapped drives
are supported. These are application safeguards, not an OS security sandbox.

Captures and comparisons of legacy states exclude `.states` subtrees,
`*.fcrstate`, the standard tool EXE/report names and legacy timestamped reports,
preventing tool activity from becoming project changes. New states use format 4;
formats 1–3 remain readable. Older EXEs reject format 4 rather than silently
applying incompatible artifact rules. A directory named `scratch.tmp` is still
traversed, and an unreadable such directory still contributes Unknown coverage.

SMB servers must grant Execute permission to launch an EXE from a share. A real
read/write-only data share rejected launch with Windows error 5 before the
application started; SMB project/report operations with a local EXE still passed.
A separate disposable test EXE with Execute permission launched from SMB, used
local history and saved its default report to SMB. Only that fixture's Execute
bits were adjusted; server configuration and unrelated permissions were unchanged.
The application never changes permissions or elevates itself.

## Automated and native checks

**70 tests passed with zero skips on Linux/Xvfb, Windows source and the frozen
Windows runner**: 56 core and 14 real Tk tests. Coverage includes size precision,
positive/negative/zero/Unknown deltas, equal-length edits, artifact exclusions,
legacy states, exact output exceptions, in-project rollback, SMB history routing,
quote handling, operation concurrency and GUI report selection/lock recovery.
Existing bounded hashing, coverage scopes, corruption, disk-full and UI cases pass.

**13 source/production-EXE scenarios** match file records and every workbook ZIP
member, normalizing only workbook timestamps. **Seven fatal failure cases** match
exit codes, output preservation and cleanup. Previous-release states are readable;
the previous EXE rejects current states.

**Ten native recovery assertions** pass in an unelevated Windows session:
exclusive locks at 16/32 workers, complete unlock retry, ACL-denied subtree
Unknown, restored-fixture-ACL retry, denied-root rollback, locked-state rollback,
locked-report rollback, report retry, excluded locked Office files and staging
cleanup. ACL changes affect only disposable fixtures and are restored. Unreadable
files/subtrees never silently become Added/Deleted/Changed; source-root failure
still aborts capture.

Native placement checks pass for EXE/history/report inside a project, repeated
capture exclusion, fixed-name overwrite, real input/output/history paths over
260 characters, a directory-junction report alias and source-offline comparison.
The long-path test launches the EXE from a short path; it does not establish that
Windows can launch an EXE whose own pathname exceeds 260 characters. SMB source/
report parity, local history and rejection of SMB state output also pass.

The production GUI runs inside its inspected project, captures complete and
partial states, selects a nondefault A/B pair, displays read issues and overwrites
the fixed report. Native Excel verifies ordinary and Unknown pivots/drill-down.
No application TCP connections were observed. Idle/progress and footer alignment
were visually inspected.

## Full Desktop and Excel

Two final production-EXE captures, without administrator rights, each read
**83,204 files / 17.228 GB**, with **seven read issues**. Capture timings were
**20.069 s at 16 workers** and **20.198 s at 32**, including loading the resulting
state. Only a new disposable Desktop fixture was edited and removed; existing
Desktop content was read-only.

The union has **83,206 rows: 2 Added, 2 Deleted, 1 Changed and 83,201 Unchanged**,
with **+10 bytes net delta** and no incidental changes. Comparison/export took
**23.096 s**. Both captures could not enumerate the same seven branches: no
filenames can be invented there, so Unknown file rows are zero, while the warning
and 14 A/B read-issue rows remain explicit.

**Seven native Excel reports** opened normally: in-project, long-path, SMB report,
SMB-launched EXE report, complete GUI, partial GUI and full Desktop. Checks cover
plain data, literal text, numeric formats, frozen rows/zoom, flags, Unknown blank
delta and pivot sums of both delta units. The Desktop workbook opened in
**2.311 s**; pivot checks took **0.974 s** and matched all counts and +10 bytes.
Read-only closure preserved report bytes.

Timings are observations with uncontrolled caches and concurrent validation,
not a controlled performance comparison against previous releases. Hash workers
remain default 16 with manual 32; queue size is bounded and reads are bounded by
the initial file size. Windows still controls SMB I/O timeout behavior.

## Packaging and repetition

The production single-file EXE is **12,121,687 bytes**, SHA-256
`5028105a596a64bb392d601419adf9b5c3f016c43de149ed85e4390edadfa1bc`.
Python 3.13.14, PyInstaller 6.22.0 and XlsxWriter 3.2.9 remain pinned. Embedded
application code matches source; 390 code filenames are relative and 1,348
payloads pass the private-token audit. A clean repeat build is byte-identical.
The test EXE is not published or included in production.

Use the README unit command with Xvfb for headless Tk. On Windows build production
with `BUILD-EXE.bat`, then the development runner with `BUILD-TEST-EXE.bat`:

```powershell
.\dist\folder-change-review-tests.exe --results C:\Review\frozen-suite.json
.\.venv\Scripts\python.exe windows_build\verify.py --exe C:\Review\folder-change-review.exe --results C:\Review\Parity
```

Run `tests/windows_failure_acceptance.py` without elevation for real normal-user
ACL denials. `tests/windows_placement_acceptance.py` uses disposable local/share
fixtures; it never changes share permissions. Native Excel checks require a
separate pywin32 test installation and interactive desktop. The tool needs
neither Excel nor pywin32 to create reports.
