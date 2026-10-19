# v0.9.0 validation

Validated on 2026-10-19 on Windows 11 x86-64 with pinned Python 3.13.16,
PyInstaller 6.22.3 and XlsxWriter 3.2.9. Linux uses Python 3.14.7/Xvfb.
Machine-readable [results](validation.json), [components](components.json) and
[security checks](security-audit.json) accompany the release.

## Portable storage

- States, settings, processing files, unpacked runtime and the fixed report are
  all inside the portable tool folder. The report-folder chooser is removed.
- Native launches from an unrelated CWD with TEMP/TMP/APPDATA/LOCALAPPDATA set
  to an empty outside sentinel leave that sentinel empty. Live GUI extraction
  is observed under `runtime`; normal exit clears it. Operations clear `work`.
- The complete portable folder also passes native placement on a disposable SMB
  share, including launching its EXE and extracting the runtime on that share.
- Copying the complete folder preserves history and settings. A relative project
  setting follows the copied folder. Comparing copied states works after the
  original folder and source documents are removed.
- In-project placement excludes the actual managed paths; unrelated project
  directories with the same names remain inventoried. Outside outputs are
  rejected. Long project/state paths are exercised.
- A standard-user launch from unwritable portable storage fails clearly without
  falling back to profile/system-temp storage. Links/junctions for managed data
  are rejected; malformed exclusion metadata is covered by regression tests.

## Correctness and native acceptance

- **105 tests in each environment:** Linux/Xvfb, Windows source and the separate
  frozen test runner, with no failures or skips. This includes the existing
  hashing/mutation, partial coverage, format, UI/layout and offline/read-only
  tests plus portable copying, ownership, confinement and exclusion tests.
- **16 source/production-EXE comparisons** check complete workbook members,
  all statuses, Unicode/literal strings, exclusions, opaque archives, all three
  capture modes and previous-release states. Only workbook timestamps are
  normalized. Seven matched fatal-error cases preserve destinations. Version 5
  states remain readable; the previous EXE rejects new format 6 states.
- **13 native recovery assertions pass under a standard, unelevated token:**
  locks, denied folders/root, retry, atomic state/report preservation, excluded
  locks, Quick without content access, sampled read failures and staging cleanup.
- The production GUI creates states, chooses older states, switches modes,
  displays read issues and writes the fixed report. Normal/short-window layouts
  are visually reviewed; idle progress is hidden. No application TCP connections
  were observed during the GUI check.
- Native Excel opens complete/partial GUI reports and reports from all three
  modes normally. Plain white data, headers, numeric flags, pivot sums and
  changed/Unknown file drill-down pass. Read-only closes preserve original bytes.

## Reproduction and limits

Two independent directory builds, with fresh verified interpreters/venvs and
separately compiled portable bootloaders, produce identical EXE bytes. Complete
patched bootloader source and its checksum are published with the release.
Every embedded DLL/PYD matches the pinned Python distribution. Component and
validation receipts record artifact size, SHA-256 and bootloader inputs. The EXE
is **11,966,933 bytes**, SHA-256:

```text
83ec83e832bd210de8d2e4de2756cd64ef9852855efc0acb0b9ebdfaa595d65f
```

A local 8,000-file/501-folder fixture takes **1.450 s with 16 workers** and
**1.370 s with 32 workers**, including onefile startup and state saving. Both
captures read zero file-content bytes. This is a small-content NTFS metadata
regression test, not a representative SMB throughput measurement.

Quick review still performs no content reads; its size/timestamp limitations and
optional sampled/full modes are unchanged. Historical controlled SMB measurements
are in [performance](performance.md); they are v0.8 measurements, not a new claim
about another SMB server. The portable folder may itself be on SMB; runtime
extraction then uses that share and startup depends on its speed/permissions.

The local Defender scan and dependency advisory observations are recorded in the
security receipt. The EXE remains unsigned. Application-level safeguards are not
an OS sandbox. Private inventories, paths, screenshots, credentials and raw logs
are not release assets.
