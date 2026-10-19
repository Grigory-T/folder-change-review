"""Portable ZIP allow-list, exact runtime identity and deterministic metadata."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from windows_build.package_release import DOCUMENTS, inventory, package, sha


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.tool=self.base/'Tool';self.tool.mkdir()
        (self.tool/'folder-change-review.exe').write_bytes(b'fixture executable')
        internal=self.tool/'_internal';internal.mkdir();(internal/'runtime.dll').write_bytes(b'fixture runtime')
        for name in DOCUMENTS:(self.tool/name).write_text('Neutral document')
        self.acceptance={'standard_onedir':True,'exe_sha256':sha(self.tool/'folder-change-review.exe')}
        self.manifest={'executable_sha256':self.acceptance['exe_sha256'],'runtime_file_sha256':inventory(self.tool)}
        (self.tool/'build-manifest.json').write_text(json.dumps(self.manifest))

    def test_zip_is_deterministic_and_excludes_states_reports_and_nested_build_copies(self):
        (self.tool/'folder-change-review-data').mkdir();(self.tool/'folder-change-review-data/private.fcrstate').write_bytes(b'private')
        (self.tool/'folder-change-review.xlsx').write_bytes(b'private report')
        nested=self.tool/'RepeatedBuild';nested.mkdir();(nested/'secret.txt').write_bytes(b'private')
        a=self.base/'A.zip';b=self.base/'B.zip'
        package(self.tool,a,self.acceptance);package(self.tool,b,self.acceptance)
        self.assertEqual(a.read_bytes(),b.read_bytes())
        with zipfile.ZipFile(a) as archive:
            self.assertEqual(set(archive.namelist()),{'folder-change-review.exe','_internal/runtime.dll','build-manifest.json',*DOCUMENTS})
            self.assertTrue(all(info.date_time==(1980,1,1,0,0,0) for info in archive.infolist()))

    def test_changed_missing_or_extra_runtime_file_preserves_previous_zip(self):
        target=self.base/'previous.zip';target.write_bytes(b'keep')
        dll=self.tool/'_internal/runtime.dll'
        for action in ('changed','missing','extra'):
            dll.write_bytes(b'fixture runtime')
            extra=self.tool/'_internal/extra.dll'
            if extra.exists():extra.unlink()
            if action=='changed':dll.write_bytes(b'changed')
            if action=='missing':dll.unlink()
            if action=='extra':extra.write_bytes(b'extra')
            with self.subTest(action=action),self.assertRaises(ValueError):package(self.tool,target,self.acceptance)
            self.assertEqual(target.read_bytes(),b'keep')

    def test_acceptance_must_belong_to_this_executable(self):
        with self.assertRaises(ValueError):package(self.tool,self.base/'bad.zip',dict(self.acceptance,exe_sha256='0'*64))
