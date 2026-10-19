from runtime_safety import portable_directory
"""Incomplete scans must never become apparently complete comparison states."""
import contextlib
import errno
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import folder_change_review as app
import runtime_safety


class CaptureFailureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        location = portable_directory(self.temporary.name)
        location.__enter__()
        self.addCleanup(location.__exit__, None, None, None)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.project = self.base/'Project'
        self.project.mkdir()
        (self.project/'readable.pdf').write_bytes(b'keep')
        self.blocked = self.project/'Restricted'
        self.blocked.mkdir()
        (self.blocked/'report.docx').write_bytes(b'document')
        (self.blocked/'unseen.pdf').write_bytes(b'unseen')
        self.output = self.base/'previous.fcrstate'
        with contextlib.redirect_stdout(io.StringIO()):
            app.create_snapshot(self.project, self.output, 1, mode="full")
        self.previous = self.output.read_bytes()

    def partial_then_retry(self, failure, kind):
        for workers in (1, 16, 32):
            with self.subTest(workers=workers):
                target = self.base/f'partial-{workers}.fcrstate'
                with failure(), contextlib.redirect_stdout(io.StringIO()):
                    state = app.create_snapshot(self.project, target, workers, mode="full")
                self.assertFalse(state['complete'])
                self.assertEqual(state['read_error_count'], 1)
                self.assertEqual(state['read_errors'][0]['kind'], kind)
                self.assertEqual(app.load_snapshot(target), state)
                self.assertEqual(self.output.read_bytes(), self.previous)
                self.assertEqual(list(self.base.glob('.folder-change-review-*')), [])
                self.assertEqual(runtime_safety._roots, ())
                self.assertFalse(runtime_safety._offline)
                rows = app.compare_snapshots(app.load_snapshot(self.output), state)
                self.assertNotIn('Deleted', [row['Status'] for row in rows])
                self.assertIn('Unknown', [row['Status'] for row in rows])
                for row in rows:
                    if row['Status'] == 'Unknown':
                        self.assertEqual((row['Added'],row['Deleted'],row['Changed']), (None,None,None))
        with contextlib.redirect_stdout(io.StringIO()):
            state = app.create_snapshot(self.project, self.base/'retry.fcrstate', 32, mode="full")
        self.assertTrue(state['complete'])
        self.assertEqual(state['file_count'], len(list(self.project.rglob('*.*'))))

    def test_denied_subfolder_saves_partial_and_preserves_previous_state(self):
        original = os.scandir
        def denied(path):
            if not isinstance(path, int) and app.absolute(path) == str(self.blocked):
                raise PermissionError(errno.EACCES, 'Access denied', os.fspath(path))
            return original(path)
        self.partial_then_retry(lambda: patch.object(app.os, 'scandir', side_effect=denied), 'directory')

    def test_interrupted_enumeration_preserves_coverage_gap(self):
        original = os.scandir
        project = self.blocked
        (project/'unseen.pdf').write_bytes(b'unseen')
        class Interrupted:
            def __enter__(self):
                self.entries = original(app.extended(project))
                self.iterator = iter(self.entries)
                return self
            def __exit__(self, *args):
                self.entries.close()
            def __iter__(self): return self
            def __next__(self):
                if getattr(self, 'yielded', False):
                    raise OSError(errno.EIO, 'Interrupted enumeration', str(project))
                self.yielded = True
                return next(self.iterator)
        def interrupted(path):
            return Interrupted() if not isinstance(path, int) and app.absolute(path) == str(self.blocked) else original(path)
        self.partial_then_retry(lambda: patch.object(app.os, 'scandir', side_effect=interrupted), 'directory')

    def test_file_disappears_before_hash_is_unknown(self):
        original = app.hash_file
        def vanished(path):
            if Path(path).name == 'report.docx':
                raise FileNotFoundError(errno.ENOENT, 'No longer available', path)
            return original(path)
        self.partial_then_retry(lambda: patch.object(app, 'hash_file', side_effect=vanished), 'file')

    def test_failed_metadata_is_an_unknown_scope(self):
        original = os.scandir
        blocked = self.blocked
        class Entry:
            name = 'report.docx'
            def stat(self, **kwargs):
                raise PermissionError(errno.EACCES, 'Metadata access denied', str(blocked/self.name))
        with original(app.extended(self.blocked)) as entries:
            others = [entry for entry in entries if entry.name != Entry.name]
        class DeniedMetadata:
            def __enter__(self): return iter([Entry(), *others])
            def __exit__(self, *args): pass
        def denied(path):
            return DeniedMetadata() if not isinstance(path, int) and app.absolute(path) == str(self.blocked) else original(path)
        self.partial_then_retry(lambda: patch.object(app.os, 'scandir', side_effect=denied), 'unknown')

    def test_access_message_has_plain_path_and_actionable_recovery(self):
        path = app.extended(self.blocked)
        message = app.capture_error_message(PermissionError(errno.EACCES, 'Access denied', path))
        self.assertIn(str(self.blocked), message)
        self.assertIn('read permission', message)
        self.assertIn('Existing states are unchanged', message)
        self.assertNotIn('\\\\?\\', message)

    def test_lock_and_disappearance_messages_are_distinct(self):
        locked = OSError('locked')
        locked.winerror = 32
        locked.filename = str(self.blocked/'report.docx')
        message = app.capture_error_message(locked)
        self.assertIn('locked by another application', message)
        self.assertIn('Close the application', message)
        vanished = FileNotFoundError(errno.ENOENT, 'gone', str(self.blocked))
        self.assertIn('became unavailable', app.capture_error_message(vanished))

    def test_other_errors_keep_their_specific_explanation(self):
        for error in (ValueError('Choose a folder'), PermissionError('Project is read-only'), OSError('File changed while being hashed')):
            self.assertEqual(app.capture_error_message(error), str(error))

    def test_cli_access_denial_uses_the_same_explanation(self):
        output = io.StringIO()
        with patch.object(app, 'create_snapshot', side_effect=PermissionError(errno.EACCES, 'denied', str(self.blocked))), contextlib.redirect_stderr(output):
            code = app.main(['snapshot', '--root', str(self.project), '--output', str(self.output)])
        self.assertEqual(code, 1)
        self.assertIn('read permission', output.getvalue())
        self.assertEqual(self.output.read_bytes(), self.previous)
