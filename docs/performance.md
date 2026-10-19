# Fast change review

## What caused the slowdown

Before v0.8, every state fully SHA-256-hashed every included file. A folder with
many gigabytes of Office documents and media therefore required that content to
cross SMB on every capture. This was very different from Folder Review's Quick
inventory. Each content open also incurred Windows metadata queries, followed by
two explicit handle checks and a path check. Folder enumeration was serial.

The published v0.7 EXE was checksum-verified before testing. Its source version
needed 65.25 s on the mixed fixture versus 65.16 s for the EXE: packaging was not
the cause. Increasing workers from 16 to 32 gave 66.37 s. Increasing the hashing
buffer from 256 KiB to 1 MiB gave 70.93 s. Neither addressed the dominant I/O.

v0.8 defaults to Quick review. It reuses size/time metadata from directory
entries, opens no file contents, and removes those per-file content/metadata
checks from the quick path. Folder reads run in a bounded pool. Full contents
keeps the existing mutation checks; the smaller hashing buffer is retained.
More concurrency is available for servers that benefit, but is not a promised
speed multiplier. On this fixture one versus 16 folder workers was similar.

## Controlled Windows SMB measurements

Windows 11 x86-64 client; authenticated, read-only SMB2 fixture server with an
additional 2 ms delay per READ. The first fixture contained 400 synthetic
Office-heavy files plus eight media files, **1,061,919,747 bytes**, in 13 folders.
All fixtures were synthetic; no private project was accessed.

| Delivery / mode | Workers | Elapsed | SMB file-content bytes returned |
|---|---:|---:|---:|
| Folder Change Review v0.7 EXE | 16 | 65.160 s | 1,090,799,622 |
| Folder Change Review v0.7 EXE | 32 | 66.369 s | 1,090,824,198 |
| Folder Review v0.17 Quick inventory EXE | 16 | 25.962 s | 59,891,295 |
| Folder Change Review v0.8 Quick review EXE | 16 | **1.808 s** | **0** |
| Folder Change Review v0.8 Quick review EXE | 32 | 1.858 s | 0 |
| Folder Change Review v0.8 Sampled contents EXE | 16 | 13.090 s | 100,104,366 |

Quick review was about **36 times faster** than the previous EXE here. The SMB
QUERY_INFO count fell from 15,902 to 436. The earlier Office-only 400-file fixture
also improved from 43.31 s to 1.90 s in pre-release measurements.

Full contents still needs complete reads; a pre-release v0.8 measurement was
66.18 s, consistent with preserving that mode's stronger checks. Sampled contents
requested 71,138,475 successful payload bytes; Windows buffering/read-ahead explains
why the actual SMB bytes returned were higher. These byte counters have different
meanings and are not interchangeable.

A second fixture had **8,000 files in 2,111 folders**, with **31.25 GiB logical
sizes**. These were sparse files for testing metadata traversal, not storage
throughput. Quick review returned **zero content bytes** and took 12.95–16.68 s
across the recorded 16/32-worker runs. The final EXE's 16-worker run was 16.684 s.
One worker took 16.952 s. Two states plus controlled edits produced exactly
2 Added, 2 Deleted, 1 Changed and 7,997 Unchanged rows. Export of the 8,002-row
union took 1.17 s, with correct native Excel pivots and file drill-down.

Timings include process startup for EXE captures. Folder Review's time includes
its workbook export; Folder Change Review capture and comparison are independent
steps. Runs were sequential, caches were not flushed, and the fixture server is
not a model of every SMB deployment. These are controlled observations, not a
throughput guarantee for another server, network or antivirus configuration.

## Review modes and accuracy

- **Quick review (default):** full path identifies the file; size and modification
  time determine Changed. No contents are read. Timestamp-only changes count as
  Changed. Edits preserving both size and timestamp can be missed.
- **Sampled contents:** compare size and SHA-256 of the first, middle and last
  64 KiB. Overlapping ranges merge; files up to 192 KiB are read fully. Other
  edits outside the samples can be missed, even if the timestamp changes.
- **Full contents:** compare size and SHA-256 of all bytes. The initial-size read
  bound, growth probe and mutation/identity checks remain in place.

Use the same mode for both states. Existing formats 1–4 are recognized as Full
contents. Create two new Quick review states for the fast workflow. The chooser
and workbook show the mode/limitations; incompatible modes cannot be compared.
Read failures remain coverage gaps reported as Unknown, never invented deletions.

## Review of Folder Review's 2026-10-19 commits

All five commits were reviewed:

| Reference commit | Applicability |
|---|---|
| [7fffcea](https://github.com/Grigory-T/folder-review/commit/7fffceade000e4b23380ece478fa446b405b9d32): avoid duplicate hashing / diagnostics | Avoid unnecessary I/O here through explicit capture modes and successful-content-byte/timing statistics. Duplicate size/prefix filters cannot prove a file unchanged between two states. |
| [e364ae9](https://github.com/Grigory-T/folder-review/commit/e364ae9cb9ce659426d52152d79caed20477f5dc): UI/CLI modes | Add capture-mode selection and clear approximation limits for this tool's different purpose. |
| [7e7caf7](https://github.com/Grigory-T/folder-review/commit/7e7caf714e689fef9ee894206f6903b19befc980): frozen-mode verification | Exercise all capture modes and their blind spots, including production CLI/source parity. |
| [e4ffe44](https://github.com/Grigory-T/folder-review/commit/e4ffe4444c23a75580ea86ca99a1ae644a9b0ff8): restore pinned runtime | Already implemented here: every production build extracts the verified runtime afresh. |
| [b95a8be](https://github.com/Grigory-T/folder-review/commit/b95a8be0aec1243a8186a7063e0b1425b00dca85): summary verification | Specific to that project's workbook summary. This tool verifies all workbook members and its own state metadata instead. |

ZIP/RAR/7z remain ordinary files. Archive expansion/integrity inspection and
within-tree duplicate detection are different features and were not transferred.
