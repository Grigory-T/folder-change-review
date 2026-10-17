# v0.7.0 finalization validation

[Aggregate receipt](validation.json) · [security receipt](security-audit.json) ·
[complete component inventory](components.json) · [build instructions](build.md).
Private project paths, inventories, screenshots and raw logs are excluded.
Validated target: Windows 11 x86-64; Windows 10 remains untested.

## Final changes

- CPython updated to security release **3.13.16**, with **OpenSSL 3.5.9**;
  PyInstaller updated to **6.22.3**. XlsxWriter remains 3.2.9.
- Production build extracts a fresh checksum-pinned Python distribution instead
  of depending on an installed Python/uv. Build wheels are version/hash locked.
  `.gitattributes` preserves exact bytes across checkout line-ending settings.
- Complete retained third-party notices and provenance are in the source and
  EXE, including Python's incorporated libraries and Microsoft runtime conditions.
  Application MIT licensing and upstream Folder Review attribution remain.
- Unused XML parser/Expat excluded from production after upstream advisory review.
  The development test runner retains its own reader dependencies.
- Managed states/settings now always use the local machine cache, outside the
  project. Legacy local history is read at startup and copied in background on the
  next operation; original states/settings remain untouched. Source metadata
  enumeration stays lightweight.
- State output must end in `.fcrstate` and be outside the inspected tree. Only
  the selected report and its staging file are project write exceptions.
  Network/process blocking and project mutation boundaries gain behavioral tests.
- Plain Excel layout, size/delta fields, worker choices, coverage/Unknown handling,
  artifact exclusions and flexible in-project/SMB placement remain unchanged.
  State format remains 4, with formats 1–3 readable; v0.6 also reads new states.

## Automated and native acceptance

**75 tests each, zero failures/errors/skips** on Linux/Xvfb (Python 3.14.7),
Windows source and a separate frozen Windows runner (Python 3.13.16): 61 core and
14 real Tk tests. New security cases exercise real blocked socket/DNS/HTTP and
process APIs, file mutation rejection, document SHA preservation across capture/
report, local workspace separation rejection of a document/in-project state output, read-only legacy import and
legacy-copy failure recovery.
Existing bounded hashing, partial coverage, size precision, rollback, corruption,
legacy, path/alias and GUI cases continue to pass.

**13 source/production-EXE scenarios** match file records and every workbook ZIP
member, normalizing only workbook timestamps. **Seven fatal failure cases** match
exit codes, preservation and cleanup. v0.6 states are readable, and its EXE can
read format-4 states from v0.7. Older incompatible-format rejection remains
covered by source/frozen tests and prior release receipts.

**Ten native unelevated recovery assertions** pass: locks at 16/32 workers, unlock
retry, denied subtree/Unknown, restored fixture ACL retry, denied-root rollback,
locked-state rollback, locked-report rollback/retry, excluded locked Office files
and staging cleanup. Fixture ACLs are restored; production never changes ACLs.

Native placement passes inside a project, long input/output/history paths over
260 characters, a real directory junction, fixed-name overwrite, source-offline
comparison and SMB source/report parity. The long-path test launches the EXE from
a short path; EXE launch paths over 260 are not established. SMB history/workspaces
stay local. An SMB data share without Execute rejects EXE launch before startup;
a separate own disposable EXE with Execute launches from SMB and saves its default
report there. No server configuration or unrelated permissions changed; fixtures
and local fixture history were removed.

The final production GUI captures complete/partial states inside its project,
selects older A/B states, shows read issues and overwrites the fixed report.
Native Excel verifies complete and Unknown pivots/drill-down. No application TCP
connections were observed. Layout/idle-state screenshots were visually reviewed.

## Full Desktop and native Excel

Final unelevated Desktop captures each read **83,204 files / 17.228 GB**, with
**seven read issues**: **20.502 s at 16 workers**, **21.819 s at 32**, including
loading the resulting state. Only a new disposable fixture was edited/removed;
existing Desktop content remained read-only.

Union: **83,206 rows — 2 Added, 2 Deleted, 1 Changed, 83,201 Unchanged**, net
**+10 bytes**, no incidental changes. Compare/export: **22.523 s**. Both captures
could not enumerate the same branches, so Unknown file rows are zero while the
coverage warning and 14 A/B issue rows remain explicit.

**Seven native Excel reports** open normally: in-project, long-path, SMB report,
SMB-launched EXE report, complete GUI, partial GUI and full Desktop. Plain data,
flags, size precision, zoom/freeze, Unknown blank delta and pivot sums of both
delta units pass. Desktop open **2.076 s**, pivot checks **1.014 s**, correct
counts and +10 bytes. Read-only closes preserve report bytes.

Timings have uncontrolled caches/concurrent workloads and are observations, not
a controlled performance comparison to previous versions.

## Supply-chain, privacy and reproduction

Final EXE: **11,954,673 bytes**, SHA-256
`fa1037adea2846404a4e34db94fa5996f382cb849c2409600ac2d60160f39a64`.
Two clean builds in separate directories produce identical EXEs. Embedded project
bytecode matches source; code filenames are relative. All **23 DLL/PYD payloads**
match the verified Python distribution; payload/module/library/build-input hashes
and native import names are published in `components.json`. This reproduces
packaging from pinned upstream binaries, not recompilation of those binaries or
an independent cross-machine build.

`pip-audit 2.10.1` checks **11 runtime/build/test Python packages** against PyPI
advisories, with no listed vulnerabilities. Microsoft Defender custom scan finds
no threats in the exact final EXE, with definitions `1.461.67.0`; its timestamp
and checksum are in the security receipt. No external upload was requested.
These checks cannot prove permanent absence of every vulnerability or malware.
The EXE is unsigned; users can verify hashes, inspect source and reproduce it.

Public history before finalization: **77 file blobs** checked, no private-token
matches. All five previously published EXEs plus the final EXE: **8,087 payloads**
checked, no private-token matches. Final EXE contributes 1,349 payloads. Final
source/docs receive a separate private-token/credential-pattern check. Public
issues/PRs and Actions artifacts are empty. Required upstream copyright names
remain in license notices; private project names/paths/wiki facts do not.

See [SECURITY.md](../SECURITY.md) for the supported boundaries: offline local
execution, SMB filesystem access and explicitly selected output exceptions.
Application safeguards are not an OS firewall or sandbox.

The Downloads EXE checksum is verified. Real legacy history was copied into the
local cache; original bytes/mtimes and preferences were verified unchanged. The
existing Downloads workbook was open and was preserved. The final Desktop test
workbook remains available in the private Windows validation folder.
