"""I/O budgets, approximation limits, mode compatibility and quick-tree coverage."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import folder_change_review as app
from openpyxl import load_workbook
from state_store import read_metadata


class ReviewModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.root = self.base/'project'; self.root.mkdir()
        self.file = self.root/'file.bin'
        self.file.write_bytes(b'a'*(app.SAMPLE_SIZE*12))
        self.stamp = 1_700_000_000_000_000_000
        os.utime(self.file, ns=(self.stamp, self.stamp))
        self.sequence = 0

    def capture(self, mode='quick', workers=16):
        self.sequence += 1
        with contextlib.redirect_stdout(io.StringIO()):
            result = app.create_snapshot(self.root, self.base/f'{self.sequence}.fcrstate', workers, mode=mode)
        self.assertEqual(app.load_snapshot(self.base/f'{self.sequence}.fcrstate'), result)
        return result

    def status(self, a, b):
        return app.compare_snapshots(a, b)[0]['Status']

    def edit(self, offset, restore=True):
        with self.file.open('r+b') as f:
            f.seek(offset); f.write(b'Z')
        stamp = self.stamp if restore else self.stamp + 10_000_000_000
        os.utime(self.file, ns=(stamp, stamp))

    def test_quick_default_opens_no_contents_and_saves_no_fingerprint(self):
        with patch.object(app, 'open', side_effect=AssertionError('Quick must not open contents'), create=True), \
             patch.object(app, 'hash_file', side_effect=AssertionError('Quick must not hash')):
            state = self.capture()
        self.assertEqual(state['review_mode'], 'quick')
        self.assertEqual(state['statistics']['content_bytes_read'], 0)
        self.assertIsNone(state['files'][0]['sha256'])
        self.assertEqual(read_metadata(self.base/'1.fcrstate')['review_mode'], 'quick')

    def test_quick_detects_size_and_time_but_documents_preserved_metadata_limit(self):
        a = self.capture(); self.edit(0, restore=False)
        self.assertEqual(self.status(a, self.capture()), 'Changed')
        os.utime(self.file, ns=(self.stamp, self.stamp))
        self.assertEqual(self.status(a, self.capture()), 'Unchanged')
        self.file.write_bytes(b'different size')
        os.utime(self.file, ns=(self.stamp, self.stamp))
        self.assertEqual(self.status(a, self.capture()), 'Changed')

    def test_timestamp_only_change_depends_on_mode(self):
        for mode in app.REVIEW_MODES:
            with self.subTest(mode=mode):
                a = self.capture(mode)
                stamp = self.file.stat().st_mtime_ns + 10_000_000_000
                os.utime(self.file, ns=(stamp, stamp))
                self.assertEqual(self.status(a, self.capture(mode)), 'Changed' if mode == 'quick' else 'Unchanged')

    def test_samples_detect_first_middle_and_last_edits_with_restored_time(self):
        for offset in (0, self.file.stat().st_size//2, self.file.stat().st_size-1):
            with self.subTest(offset=offset):
                self.file.write_bytes(b'a'*(app.SAMPLE_SIZE*12)); os.utime(self.file, ns=(self.stamp,self.stamp))
                a = self.capture('sampled'); self.edit(offset)
                self.assertEqual(self.status(a, self.capture('sampled')), 'Changed')

    def test_unsampled_edit_is_detected_only_by_full_mode_when_time_restored(self):
        a = {mode:self.capture(mode) for mode in app.REVIEW_MODES}
        self.edit(app.SAMPLE_SIZE*2)
        for mode in app.REVIEW_MODES:
            self.assertEqual(self.status(a[mode], self.capture(mode)), 'Changed' if mode == 'full' else 'Unchanged')

    def test_sample_read_budget_is_bounded_even_for_large_logical_file(self):
        with self.file.open('r+b') as f:f.truncate(4*1024**3 + 17)
        state = self.capture('sampled')
        self.assertEqual(state['statistics']['content_bytes_read'], 3*app.SAMPLE_SIZE)
        self.assertEqual(state['files'][0]['size'], 4*1024**3+17)

    def test_samples_merge_overlapping_ranges_and_support_empty_files(self):
        for size in (0,1,app.SAMPLE_SIZE-1,app.SAMPLE_SIZE,app.SAMPLE_SIZE+1,3*app.SAMPLE_SIZE):
            with self.subTest(size=size):
                self.file.write_bytes(b'a'*size)
                state = self.capture('sampled')
                self.assertEqual(state['statistics']['content_bytes_read'], min(size,3*app.SAMPLE_SIZE))
                self.assertEqual(self.status(state, self.capture('sampled')), 'Unchanged')

    def test_sample_handles_short_reads_and_rejects_premature_eof(self):
        properties = self.file.stat(); real_open = io.open
        class Short:
            def __init__(self, *args, **kwargs): self.f = real_open(*args, **kwargs)
            def __enter__(self):return self
            def __exit__(self,*args):self.f.close()
            def seek(self,*args):return self.f.seek(*args)
            def read(self,n):return self.f.read(min(n,127))
        expected = app.sample_file(str(self.file), properties)
        with patch.object(app, 'open', side_effect=Short, create=True):
            self.assertEqual(app.sample_file(str(self.file),properties), expected)
        class Empty(Short):
            def read(self,n):return b''
        with patch.object(app,'open',side_effect=Empty,create=True), self.assertRaises(OSError):
            app.sample_file(str(self.file), properties)

    def test_sample_mutation_and_failure_create_unknown_not_deleted(self):
        a = self.capture('sampled')
        with patch.object(app,'sample_file',side_effect=OSError('File changed while being sampled')):
            b = self.capture('sampled')
        self.assertFalse(b['complete']); self.assertEqual(self.status(a,b),'Unknown')
        old = self.file.stat(); self.file.write_bytes(b'changed size')
        with self.assertRaises(OSError):app.sample_file(str(self.file),old)

    def test_cross_mode_comparison_is_rejected_before_replacing_report(self):
        self.capture('quick'); self.capture('full')
        report = self.base/'existing.xlsx'; report.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'different review modes'):
            app.compare_files(self.base/'1.fcrstate',self.base/'2.fcrstate',report)
        self.assertEqual(report.read_bytes(),b'keep')

    def test_legacy_full_states_still_compare_with_new_full_states(self):
        current = self.capture('full'); legacy = copy.deepcopy(current)
        legacy.update(version=4);legacy.pop('review_mode')
        for row in legacy['files']:row.pop('mtime_ns')
        path=self.base/'legacy.fcrstate'
        with app.staged_output(path) as temp:app.write_container(temp,legacy)
        self.assertEqual(self.status(app.load_snapshot(path),current),'Unchanged')

    def test_invalid_modes_and_schema_are_rejected(self):
        with self.assertRaises(ValueError):self.capture('unknown')
        state=self.capture()
        for key,value in [('review_mode','other'),('hash_algorithm','sha256')]:
            bad=copy.deepcopy(state);bad[key]=value
            path=self.base/'bad.json';path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):app.load_snapshot(path)
        for key,value in [('mtime_ns','bad'),('sha256','a'*64)]:
            bad=copy.deepcopy(state);bad['files'][0][key]=value
            path=self.base/'bad.json';path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):app.load_snapshot(path)

    def test_quick_parallel_tree_matches_serial_and_covers_denied_subtrees(self):
        for i in range(75):
            folder=self.root/f'area-{i}';folder.mkdir();(folder/'doc.pdf').write_bytes(b'doc')
        a=self.capture(workers=1)
        self.assertEqual(a['files'],self.capture(workers=32)['files'])
        original=app.os.scandir
        def denied(path):
            if not isinstance(path,int) and app.absolute(path)==str(self.root/'area-1'):raise PermissionError(13,'denied')
            return original(path)
        with patch.object(app.os,'scandir',side_effect=denied):b=self.capture(workers=32)
        rows=app.compare_snapshots(a,b)
        self.assertEqual(sum(row['Status']=='Unknown' for row in rows),1)
        self.assertNotIn('Deleted',[row['Status'] for row in rows])

    def test_quick_report_states_assumption_without_hash_column(self):
        self.capture(); self.capture()
        with contextlib.redirect_stdout(io.StringIO()):app.compare_files(self.base/'1.fcrstate',self.base/'2.fcrstate',self.base/'report.xlsx')
        book=load_workbook(self.base/'report.xlsx');self.addCleanup(book.close)
        self.assertIn('Quick review',book['Changes']['B5'].value)
        self.assertIn('Preserved timestamps',book['Changes']['B5'].value)
        headers=[cell.value for cell in book['Changes'][6]]
        self.assertFalse(any('SHA' in str(value) for value in headers))

    def test_cli_default_is_quick_and_explicit_full_remains_available(self):
        for flags,expected in [([], 'quick'),(['--mode','sampled'],'sampled'),(['--mode','full'],'full')]:
            target=self.base/(expected+'.fcrstate')
            with contextlib.redirect_stdout(io.StringIO()):code=app.main(['snapshot','--root',str(self.root),'--output',str(target),*flags])
            self.assertEqual(code,0);self.assertEqual(read_metadata(target)['review_mode'],expected)
