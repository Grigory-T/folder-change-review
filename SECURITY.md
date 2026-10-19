# Runtime and data boundaries

Folder Change Review runs on the Windows machine. There is no telemetry,
update checker, web client, remote execution service or automatic download in the
application. Supported remote filesystem access is SMB, including mapped drives.
The EXE may be stored on SMB with Execute permission; runtime extraction, states, settings, workspaces and reports stay beside the EXE.
No AppData or system-temp fallback is used, including for an SMB-hosted EXE.

Python socket/DNS/HTTP APIs and subprocess launches are blocked during normal
application execution. Opening the explicitly chosen report folder in Explorer
is the only shell-opening action. SMB access is performed by Windows filesystem
APIs and may involve Windows authentication/DNS traffic. This is not an OS
firewall or sandbox, and it does not constrain other programs or Windows services.
Use trusted local/SMB locations; other network redirectors and cloud-sync mounts
are not supported or tested.

Quick review enumerates directory metadata without opening file contents.
Optional content modes open project files for reading. The application does not modify content,
permissions or timestamps of inspected documents. Reads may affect access times
according to filesystem policy. The only intended project writes are the tool's own portable support paths,
report and atomic-save staging files when the tool is placed within the project.
All these locations stay inside the tool folder. Supporting directories must be
real directories rather than links/junctions. Original legacy states are read
and copied without modification. The actual supporting paths and reserved
state/report/tool names are excluded from inventory. Unrelated same-named
project directories are still inventoried. Directory timestamps may change when
outputs are created. Failed saves preserve the previous output.
Output-file symlinks are rejected. States must use `.fcrstate`; report output must
use `.xlsx`. An explicitly selected report can replace the existing report at
that path.

Snapshots and workbooks contain project paths and metadata; snapshots also contain
full or sampled SHA-256 fingerprints when content checks are enabled. They are not encrypted. They are only written inside the portable local/SMB tool folder, never uploaded by the tool. State files are technical data, not
executable pickle objects, and comparisons need no access to the live project.
Use states produced by this tool; malformed states are rejected, but parsing an
untrusted file is not a substitute for process isolation. Reports have literal
strings with formula/URL conversion disabled and contain no macros or embedded
code.

# Supply chain and audit

See [reproducible build instructions](docs/build.md), the published component
inventory and [third-party notices](THIRD-PARTY-NOTICES.md). Python and package
inputs are version/hash pinned. All embedded DLL/PYD bytes are checked against
the verified Python distribution. The PyInstaller bootloader is compiled from hash-verified upstream source with
the public `windows_build/portable_bootloader.c` change. It selects `runtime`
relative to its executable before Python starts, rejects a linked runtime folder,
and fails without falling back to other storage. The complete patched source,
source checksum, build recipe and bootloader hashes are published. Packaging
changes executable resources and appends the application archive. No UPX, archive utility or additional downloaded executable
is bundled.

Build/setup/audit tools may access public upstream repositories. They are never
invoked by the shipped EXE. The production EXE does not contain the development
runner or openpyxl. Release receipts distinguish measured results from earlier
releases. The EXE is unsigned; SHA-256 verification and reproducible builds are
available for independent checking. Antivirus and dependency checks reduce risk;
they cannot prove the absence of every vulnerability or malicious component.

To report a security issue, contact the repository maintainer through their
GitHub profile. Do not put private project inventories, paths, documents or
credentials into public issues. No project data is needed to reproduce a generic
bug; use a small synthetic fixture.
