# v0.5.0 validation

This release continues capture past individual read failures and records coverage
explicitly. Permissions are unchanged. Read failures can never silently become
Added, Deleted or Changed flags. The [machine-readable receipt](validation.json)
contains aggregate results and checksums. Private inventories, paths, screenshots
and raw logs are not published. Target tested: Windows 11 x86-64; Windows 10
remains untested.

## Capture and comparison decisions

| Situation | Capture behavior | Comparison behavior |
|---|---|---|
| Readable, stable file | Store SHA-256 and size | Existing exact full-path/hash rules |
| Locked or unreadable file | Record a file read issue; continue | Known filename is Unknown; change flags blank |
| File disappears or changes during hashing | Record a file read issue; continue | Unknown; any size from the readable side is retained |
| Unreadable subfolder | Record an unavailable subtree; continue elsewhere | Missing files inside that scope are Unknown |
| Directory iteration fails after yielding some items | Preserve readable records and record the incomplete subtree | Readable records remain comparable; unseen members are Unknown |
| Entry metadata cannot be read | Record an unknown item/subtree scope | Cover descendants without inventing a directory as a file row |
| Both captures cannot enumerate a branch | Retain both coverage warnings | No invented filenames; warning remains even if Unknown count is zero |
| Source root unavailable or cannot be enumerated | Abort capture | Existing states remain available |
| Disk full, locked destination, output write failure | Abort and clean staging | Preserve the previous destination |
| Corrupt or unsupported saved state | Reject comparison | Preserve the previous report |
| Office/temp exclusions or links/reparse points | Preserve existing exclusions and skip counters | No file rows for deliberately excluded items |

Unavailable scopes use ancestor lookup, not substring matching or a scan of all
errors per row. A denied `Area` does not hide a real deletion in `Area2`.
Windows UNC paths and reversed complete/partial comparisons are covered.
Each file is attempted once; bounded reads never chase an endlessly growing
file. SMB timeouts remain controlled by Windows.

Format 3 stores errors separately from compact file records. History reads only
small metadata, including the coverage flag and issue count. Earlier complete
states remain readable. An older EXE rejects format 3 rather than ignoring
coverage gaps. No hash, full-path or new flag column is added to the Changes
sheet. Complete reports retain one sheet. Incomplete reports add a warning above
the same data layout and a plain Read issues sheet. Unknown rows have `last=1`
and blank change flags. No native Excel Table, saved pivot or colored body.

## Tests

**58 tests passed on Linux/Xvfb and Windows source, with no skips**:
46 core tests and 12 real Tk workflow/layout tests. New cases exercise read
failures with 1, 16 and 32 workers, partial directory iteration, metadata failures,
vanished files, coverage direction combinations, filename availability, readable
records inside partially enumerated folders, UNC ancestors, neighboring scopes,
format validation, legacy states, disk-full rollback and metadata-only history.
The GUI suite checks incomplete labels/status, the read-issues viewer, Unknown
report totals and return to idle, alongside the previous workflow/layout cases.

**13 source/EXE scenarios** match file records and every workbook ZIP member,
normalizing only creation/modification timestamps. **Seven fatal failure cases**
match exit codes and output preservation. Previous-release states are readable;
the previous EXE rejects current states.

Eight native Windows acceptance assertions pass in a normal, unelevated session:
exclusive file locks at 16/32 workers, complete retry after unlock, denied
subfolder recovery with Unknown, complete retry after restoring the fixture ACL,
denied-root rollback, locked-output rollback, excluded locked Office files and
staging cleanup. Only disposable fixture ACLs are changed and restored.
Source/frozen partial reports match, including their warning and issue worksheet.

## Full Desktop and native Excel

Two normal, non-administrator full Desktop captures each read **83,222 files /
17.293 GB**, with **seven read issues**, 16 excluded files and two skipped links.
Capture wall times were **15.489 s at 16 workers** and **15.506 s at 32**. Controlled
edits produced **83,224 union rows: 2 Added, 2 Deleted, 1 Changed, 83,219 Unchanged**.
No incidental changes were found. Only a new test fixture was edited and removed;
existing Desktop content was read-only. Python/EXE records and workbook members
matched. EXE compare/export took **15.859 s**. These captures used the initial
v0.5.0 candidate; subsequent changes clarified lock messages, validated container
record shapes and refined UI diagnostics. Final EXE checks are listed separately.

The final EXE captured **83,592 files with complete coverage** in an elevated
read-only test. Comparing this inventory against the normal capture identified
**374 restricted known files as Unknown**, with no false deletions. Four additions
in that comparison belong to the earlier controlled fixture, which had been
removed before the elevated capture; they are not access failures.

Native Excel opened the 83,224-row Desktop workbook normally in **1.876 s**.
Pivot sums matched all change flags and total rows; changed-file drill-down passed
in **0.893 s** for pivot creation/checking. Fourteen read-issue rows represent the
seven failures in each capture. No filenames could be established in those seven
branches in either normal capture, so this report has zero Unknown file rows.
The coverage warning and issue sheet still remain visible.

The exact final EXE installed in Downloads also completed a normal Desktop
capture: **83,218 files, seven read issues, 15.580 s at 32 workers**. The controlled
fixture's four remaining files had already been removed. Comparing the final
complete and normal inventories produced **83,592 rows: 83,218 Unchanged and
374 Unknown, with zero Added/Deleted/Changed**. Native Excel opened this report,
verified all 374 Unknown rows have blank change flags, its seven issue rows and
correct pivot sums. Both delivery reports were copied with matching checksums.

The final frozen GUI captured three complete states, selected an older A/B pair,
then captured a genuinely ACL-denied subtree. It displayed incomplete coverage,
opened the read-issues viewer and exported a partial report. Native Excel opened
both normal and partial reports, checked blank change flags for Unknown, and
created a pivot/drill-down for its single Unknown file. Reports were closed
without saving and remained byte-identical. No application TCP connections were
observed. Default, shortened and warning/dialog views were visually inspected.

## SMB and packaging

The final EXE/source SMB test used **5,000 synthetic files / 327,698,890 bytes**.
Repeated captures matched exactly: EXE **9.423–10.167 s at 16 workers** and
**8.216–8.282 s at 32**, including startup. Comparison/export took **2.464 s** for
5,002 rows (2 Added, 2 Deleted, 1 Changed, 4,997 Unchanged). Comparison after removing
the source and rejection of output inside the project passed. The synthetic share
fixture was removed. Timings are observations with uncontrolled caches and
concurrent validation workloads, not a controlled comparison to older releases.

The final single-file EXE is **12,117,305 bytes**. Python 3.13.14, PyInstaller 6.22.0
and XlsxWriter 3.2.9 remain pinned. Embedded application code matches source;
390 distinct code filenames are relative and 1,348 decompressed payloads pass the
private-token audit. Runtime network/subprocess/write safeguards and the bounded
worker queue remain. Clean rebuild and delivery checksum results are recorded in
the receipt. Private test data is excluded from the repository and release.

## Repeating checks

Use the README unit-test command with Xvfb for headless Tk checks. On Windows:

```powershell
.\.build-venv\Scripts\python.exe windows_build\inspect_exe.py dist\folder-change-review.exe
.\.venv\Scripts\python.exe windows_build\verify.py --exe C:\Review\folder-change-review.exe --results C:\Review\Parity
```

Run `tests/windows_failure_acceptance.py` without elevation to exercise real
normal-user ACL denials. Native Excel tests require a separate pywin32 test
installation and an interactive desktop; the application requires neither Excel
nor pywin32 to create its reports.
