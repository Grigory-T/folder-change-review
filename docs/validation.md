# v0.8.0 validation

Validated on 2026-10-19. Windows 11 x86-64, pinned Python 3.13.16,
PyInstaller 6.22.3 and XlsxWriter 3.2.9. Linux tests used Python 3.14.7/Xvfb.
Machine-readable [results](validation.json), [component inventory](components.json)
and [security checks](security-audit.json) accompany the release.

## Correctness and native acceptance

- **92 tests per environment**, with no failures or skips: Linux source, Windows
  source and the separate frozen Windows test runner. These include 76 core and
  16 real Tk workflow/layout tests. The production EXE excludes the test runner,
  test reader and XML parser.
- **16 source/production-EXE comparisons** cover complete workbook members,
  all statuses, moves, Unicode/literal text, exclusions, opaque archives, empty
  states, buffer boundaries, timestamp-only changes and every capture mode.
  Seven matched fatal-error cases and an additional incompatible-mode rejection
  preserve existing destinations. Prior v0.7 states remain usable as Full
  contents; the older EXE rejects the new state format.
- Approximation tests explicitly demonstrate that Quick review can miss
  equal-size edits with restored timestamps, and sampling can miss edits outside
  its ranges. Full contents catches those controlled edits. Short reads,
  premature EOF, files above 4 GiB, bounded growth and partial coverage are tested.
- **13 native recovery assertions also pass under a standard, unelevated token**:
  exclusive locks, retries, denied subtrees/root, atomic state/report preservation,
  excluded locked Office files, Quick review without content access, sampled
  read failure and staging cleanup. ACL changes affect disposable fixtures only.
- The real production GUI creates states, chooses older states, switches all
  three capture modes, shows partial-coverage details, and overwrites the fixed
  report. Screenshots were reviewed for normal and smaller-window layouts. Idle
  progress is hidden. No application TCP connections were observed in that check.
- **Six native Excel checks** open reports normally: GUI complete/partial reports,
  each of the three capture modes and the 8,002-row large-tree union. Pivot sums,
  size delta, white plain data, numeric flags and changed/Unknown file drill-down
  pass. Read-only closes preserve workbook bytes.

## Performance

See the [full analysis](performance.md) for methods, limitations, all five reviewed
Folder Review commits and mode semantics.

On the same synthetic 408-file, 1 GiB SMB fixture with 2 ms added delay per READ:

| Mode / delivery | Seconds |
|---|---:|
| Previous Folder Change Review v0.7 EXE | 65.160 |
| Folder Review v0.17 Quick inventory EXE | 25.962 |
| Final v0.8 Quick review EXE, 16 workers | **1.808** |
| Final v0.8 Quick review EXE, 32 workers | 1.858 |
| Final v0.8 Sampled contents EXE | 13.090 |

Quick review transferred zero file-content bytes. An 8,000-file/2,111-folder
metadata fixture with initially 31.25 GiB sparse logical sizes took 16.684 s in
the final EXE (16 workers), also with zero content reads. Its controlled changes
produced exactly 2 Added, 2 Deleted, 1 Changed and 7,997 Unchanged rows. Export
was 1.17 s. Sparse fixtures do not measure full-content storage throughput.
These synthetic tests do not establish performance on another SMB server.

## Reproduction and supply chain

EXE: **11,960,606 bytes**. SHA-256:

```text
27f289dc58dc2e98358c79f331f121ec62b545096a6b906e670659b9272293aa
```

Two clean builds in separate directories, each using a fresh verified interpreter
and fresh build venv, were byte-identical. Embedded application bytecode matches
source; code filenames are relative. All **23 DLL/PYD payloads** match the pinned
Python distribution. Runtime dependencies and licenses are unchanged.

Microsoft Defender's local custom-file scan passed with remediation disabled;
the file hash was unchanged. The recorded signature version is 1.461.84.0.
pip-audit 2.10.1 found no listed advisories in the 11 checked runtime/build/test
packages. The EXE remains unsigned. These checks do not prove absence of every
unknown vulnerability or threat. See [build instructions](build.md),
[runtime boundaries](../SECURITY.md) and [third-party notices](../THIRD-PARTY-NOTICES.md).

Published receipts contain aggregate measurements and relative component names.
Private inventories, screenshots, credentials, raw logs and machine/user paths
are not release artifacts.
