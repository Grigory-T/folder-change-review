# v0.4.0 validation

This release changes the desktop interface. Hashing, state format, comparison
and workbook layout are unchanged from v0.3.1. The
[machine-readable receipt](validation.json) contains generic synthetic results,
source checksums and the EXE checksum. Private paths, inventories and raw
screenshots/logs are not published. Native target: Windows 11 x86-64;
Windows 10 remains untested.

## Desktop behavior

Two numbered cards separate **Create a state** from **Compare saved states**.
The latter works without choosing or opening a live project. Shared label widths
and equal action-button widths align controls. Read-only folder paths support
selection/copy and horizontal scrolling. Short windows scroll the cards while
the output-folder action remains available; headings and explanations adapt to
font size and width.

Each step has an independent status. Its indeterminate indicator is shown only
while that action runs, then stopped, reset and hidden after success or failure.
No progress bar is visible at startup or while idle. The most recent report stays
identified independently of later captures or failed comparisons.

Selections are preserved after comparison and failed captures. Creating a new
state selects the newest pair for convenience. A/B equality disables the report
button, reverse-time selections are explained, and duplicate display labels
remain independently selectable. History availability is visible in the card.
Filesystem/SMB validation runs on the background worker; closing while busy waits
for the operation to finish. Thread-start and folder-opening errors are handled.

## Tests

**37 tests passed on Linux with Xvfb and on Windows source**, with no skips:
26 existing hashing/state/report safeguards plus 11 real Tk workflow/layout tests.
The UI tests cover empty/one-state history, idle/progress lifecycle, capture,
offline comparison, selected-pair preservation, same/reversed selections,
capture/report failures, last-report preservation, background validation,
close-while-busy, thread-start failure, duplicate labels, short-window scrolling,
large fonts and aligned fields/actions. Headless Linux without a display skips
the UI class; use `xvfb-run -a` to exercise it.

The final production EXE also passed **13 source/EXE comparisons**. Snapshot file
records and every XLSX ZIP member match, normalizing only workbook creation and
modification timestamps. Cases cover empty/single input, moves/all statuses,
nested LCA, literal/Unicode names, extensionless files, opaque archives,
exclusions, all-added/deleted, buffer boundaries, timestamp-only changes and
previous-release state compatibility. **Seven failure cases** match exit codes,
preserve output and clean staging.

## Native acceptance

The frozen Windows GUI created three states, changed workers to 32, selected
two older captures explicitly and created a report beside its EXE. The selected
pair remained visible after comparison. Actual default and shortened/scrolled
windows were captured and visually inspected: clear cards, aligned controls,
visible output-folder action and no idle progress bars. Native Excel opened the
six-row GUI report normally and verified pivot totals (Added 2, Deleted 2,
Changed 1, total 6), with unchanged report bytes after closing without saving.
No application TCP connections were observed.

## Packaging and speed

A clean repeat build on the same Windows setup is byte-identical. Embedded
application bytecode matches source; all 390 distinct code filenames are
relative. 1,348 decompressed payloads passed private-token audit. Runtime and
build dependencies are unchanged. The delivery is one windowed EXE bundling
Python, Tcl/Tk, XlsxWriter and applicable licenses.

The scanner and Excel writer are unchanged. The latest separate SMB measurement
is documented at [v0.3.1](https://github.com/Grigory-T/folder-change-review/blob/v0.3.1/docs/validation.md):
5,000 synthetic files / 328 MB, repeated EXE captures 8.57–8.64 seconds at 16
workers and 6.99–7.14 seconds at 32; caches were uncontrolled. These historical
measurements were not rerun or relabeled as v0.4.0 timings. The bounded queue,
local working storage, offline policy and atomic output safeguards remain.

## Repeating checks

Use the README unit-test command (with Xvfb for headless UI tests). On Windows:

```powershell
.\.build-venv\Scripts\python.exe windows_build\inspect_exe.py dist\folder-change-review.exe
.\.venv\Scripts\python.exe windows_build\verify.py --exe C:\Review\folder-change-review.exe --results C:\Review\Parity
```

The native GUI run uses real input in an interactive Windows console. Native
Excel checks use the separately installed test dependency pywin32; it is not
required by the application. Previous versioned test receipts remain immutable
at their release tags.
