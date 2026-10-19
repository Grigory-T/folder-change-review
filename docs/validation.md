# v0.10.0 validation

Validated on 2026-10-19 on Windows 11 x86-64 with pinned Python 3.13.16,
PyInstaller 6.22.3 and XlsxWriter 3.2.9. Linux uses Python 3.14.7/Xvfb.
Machine-readable [results](validation.json), [components](components.json) and
[security checks](security-audit.json) accompany the release.

## Portable ZIP

- The ZIP contains the EXE, the already extracted `_internal` runtime, notices
  and an exact runtime hash manifest. Processing files, states and settings use
  `folder-change-review-data`; `folder-change-review.xlsx` stays beside the EXE.
- There is no runtime extraction, AppData/profile-cache/system-temp use or
  fallback. Native launches with an unrelated CWD and external TEMP/TMP/APPDATA/
  LOCALAPPDATA/PYTHONPYCACHEPREFIX sentinels leave those sentinels empty.
- Both the candidate folder and the extracted ZIP pass mandatory Windows build
  acceptance: all three modes, self-scan exclusions, whole-folder relocation,
  offline comparison, legacy history import, rejected outside outputs, rejected
  data junctions, cleaned work and failure when the tool folder is unwritable.
  The denial test drops build-transport backup privileges and first verifies
  that the test token cannot create a directory under the denied ACL.
- Root-level v0.9 states/settings and legacy `.states` remain readable. Migration
  copies states into the grouped data directory without changing originals.
  Formats 1–6 remain readable; the previous EXE rejects new format 7 states.
- Additional native placement checks pass for long paths, in-project placement,
  unrelated same-named folders and a complete tool folder on a disposable SMB
  share. The temporary share is removed afterward.
- ZIP packaging tests reject changed, missing and extra runtime files without
  replacing the previous ZIP. Saved states, reports and unrelated build copies
  are excluded from the package.

## Correctness and native acceptance

- **110 tests in each environment:** Linux/Xvfb, Windows source and the separate
  frozen test runner, with no failures or skips. Hashing/mutation, incomplete
  coverage, workbook format, UI/layout, offline/read-only boundaries, portable
  migration and deterministic packaging are covered.
- **16 source/production-EXE comparisons** match complete workbook members after
  normalizing workbook timestamps only. They cover all statuses, Unicode/literal
  text, exclusions, opaque archives, all modes and previous-release states.
  Seven matched fatal-error cases preserve destinations.
- **13 native recovery assertions pass under a standard, unelevated token:**
  file locks, denied folders/root, retry, atomic state/report preservation,
  excluded locks, Quick without content access, sampled failures and cleanup.
  A separate unwritable-folder launch fails without external-storage fallback.
- The production GUI creates states, chooses older states, switches modes,
  displays read issues and replaces the fixed report. Normal and short-window
  screenshots were reviewed; idle progress is hidden. No application TCP
  connections were observed during the check.
- **Five native Excel checks:** complete/partial GUI reports and one report from
  each mode open normally. Plain white data, English headers, numeric flags,
  pivot sums and changed/Unknown file drill-down pass. Read-only closes preserve
  original workbook bytes.

## Reproduction and performance

Two independent directory builds use fresh verified interpreters and venvs.
Both produce identical EXE bytes, the same **970 runtime files and hashes**, and
an identical deterministic ZIP. The stock hash-locked PyInstaller bootloader is
unmodified; no custom C source, compiler or bootloader patch is required. All
23 bundled DLL/PYD files match the pinned Python distribution.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `folder-change-review-windows-x64.zip` | 11,937,208 | `821726581c00bfd69f74215069c9c173c3219af56df691a72bfef4380c8ce9fb` |
| `folder-change-review.exe` inside ZIP | 2,692,234 | `8a91ff29146f614fd8861da319ad4be2fbd1bc02ba9aba57a219d7fc280144f2` |

A local 8,000-file/501-folder fixture takes about **0.3 seconds** with either 16
or 32 workers, including startup and state saving, with zero file-content reads.
Exact observations are in the validation receipt. This small-content NTFS test
checks for local metadata regressions; it does not establish SMB throughput.

Quick, sampled and full comparison behavior is unchanged. Historical controlled
SMB measurements are in [performance](performance.md); they are v0.8 observations,
not a new claim about another SMB server. A portable folder on SMB loads its
runtime directly from that share, so startup depends on its speed/permissions.

A local Defender scan of the complete application folder passed. Same-day
advisory observations for unchanged dependency versions are explicitly labelled
in the security receipt. The EXE remains unsigned; application safeguards are
not an OS sandbox. Private inventories, paths, screenshots, credentials and raw
logs are excluded from release assets.
