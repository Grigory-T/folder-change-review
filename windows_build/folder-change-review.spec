from pathlib import Path
from zipfile import ZipFile
from importlib.metadata import distribution
import sys
import os

root = Path(SPECPATH).parent
testing = os.environ.get("FOLDER_CHANGE_REVIEW_BUILD_TESTS") == "1"
data = [(str(root / "LICENSE"), "licenses/project"),
        (str(Path(sys.base_prefix) / "LICENSE.txt"), "licenses/python"),
        (str(Path(sys.base_prefix) / "tcl/tk8.6/license.terms"), "licenses/tcl-tk")]
for package in ("xlsxwriter", "pyinstaller"):
    installed = distribution(package)
    for file in installed.files:
        if file.name.lower() in ("license.txt", "copying.txt"):
            data.append((str(installed.locate_file(file)), "licenses/" + package))
a = Analysis(
    [str(root / "windows_build" / ("test_entry.py" if testing else "entry.py"))],
    pathex=[str(root), str(root / "tests")], binaries=[],
    datas=data,
    hiddenimports=[], excludes=["setuptools", "pkg_resources", "packaging"] + ([] if testing else ["openpyxl"]),
    optimize=0,
)
# Stable standard-library container order for repeatable builds.
for destination, source, _ in a.datas:
    if destination == "base_library.zip":
        library = Path(source)
        ordered = library.with_suffix(".ordered.zip")
        with ZipFile(library) as source_zip, ZipFile(ordered, "w") as target_zip:
            target_zip.comment = source_zip.comment
            for info in sorted(source_zip.infolist(), key=lambda item: item.filename):
                target_zip.writestr(info, source_zip.read(info.filename))
        ordered.replace(library)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="folder-change-review-tests" if testing else "folder-change-review", debug=False, strip=False, upx=False,
    console=testing, runtime_tmpdir=r"%LOCALAPPDATA%\FolderChangeReview",
)
