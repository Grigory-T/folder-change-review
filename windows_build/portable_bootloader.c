/* Copyright (c) 2026, Folder Change Review contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later WITH Bootloader-exception
 * Inserted into the checksum-pinned PyInstaller Windows bootloader source.
 * The combined application retains its separate MIT license.
 */
static int
_pyi_create_portable_application_directory(struct PYI_CONTEXT *pyi_ctx)
{
    char directory[PYI_PATH_MAX];
    char runtime[PYI_PATH_MAX];
    wchar_t runtime_w[PYI_PATH_MAX];
    wchar_t candidate[PYI_PATH_MAX];
    DWORD attributes;
    int i;

    if (!pyi_path_dirname(directory, pyi_ctx->executable_filename) ||
        !pyi_path_join(runtime, directory, "runtime") ||
        !pyi_win32_utf8_to_wcs(runtime, runtime_w, PYI_PATH_MAX)) {
        PYI_ERROR_W(L"Cannot resolve the portable tool folder.\n");
        return -1;
    }
    if (!CreateDirectoryW(runtime_w, pyi_ctx->security_attr) && GetLastError() != ERROR_ALREADY_EXISTS) {
        PYI_ERROR_W(L"Cannot create runtime beside the EXE. Place the tool in a writable folder.\n");
        return -1;
    }
    attributes = GetFileAttributesW(runtime_w);
    if (attributes == INVALID_FILE_ATTRIBUTES || !(attributes & FILE_ATTRIBUTE_DIRECTORY) ||
        (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) {
        PYI_ERROR_W(L"The portable runtime folder must be a real directory, not a link or junction.\n");
        return -1;
    }
    for (i = 0; i < 16; ++i) {
        if (swprintf_s(candidate, PYI_PATH_MAX, L"%ls\\_MEI%08x-%016llx-%d",
                       runtime_w, _getpid(), (unsigned long long)GetTickCount64(), i) < 0) {
            return -1;
        }
        if (CreateDirectoryW(candidate, pyi_ctx->security_attr)) {
            if (!pyi_win32_wcs_to_utf8(candidate, pyi_ctx->application_home_dir, PYI_PATH_MAX)) {
                RemoveDirectoryW(candidate);
                return -1;
            }
            /* Cover bootstrap/runtime-hook temporary files before Python entry. */
            if (_wputenv_s(L"TEMP", runtime_w) || _wputenv_s(L"TMP", runtime_w)) {
                return -1;
            }
            return 0;
        }
    }
    PYI_ERROR_W(L"Cannot unpack beside the EXE. Check tool-folder write permissions and free space.\n");
    return -1;
}

