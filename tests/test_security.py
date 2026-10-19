"""Behavioral checks of the supported offline/read-only workflow."""
import contextlib
import hashlib
import http.client
import io
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
import urllib.request

import folder_change_review as app
from runtime_safety import offline_runtime, safe_operation


class SecurityTests(unittest.TestCase):
    def test_network_and_process_apis_are_blocked_before_use(self):
        operations = [socket.socket,
                      lambda: socket.getaddrinfo('localhost', 80),
                      lambda: urllib.request.urlopen('http://127.0.0.1:9'),
                      lambda: http.client.HTTPConnection('127.0.0.1', 9).connect(),
                      lambda: subprocess.Popen(['unused-command']),
                      lambda: os.system('unused-command')]
        with offline_runtime():
            for operation in operations:
                with self.subTest(operation=operation), self.assertRaises(PermissionError):
                    operation()

    def test_project_mutations_are_rejected_and_outputs_do_not_modify_documents(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root = base/'Project'; root.mkdir()
            doc = root/'Business.pdf'; doc.write_bytes(b'original business document')
            initial = hashlib.sha256(doc.read_bytes()).hexdigest()
            operations = [lambda: doc.write_bytes(b'bad'), doc.unlink,
                          lambda: doc.rename(root/'renamed.pdf'),
                          lambda: doc.touch(), lambda: os.utime(doc, None),
                          lambda: doc.chmod(0o600), lambda: (root/'new').mkdir(),
                          lambda: os.link(doc, root/'link.pdf')]
            with safe_operation((root,), root):
                for operation in operations:
                    with self.subTest(operation=operation), self.assertRaises(PermissionError):
                        operation()
                self.assertFalse(app.inside(tempfile.gettempdir(), root))
            with contextlib.redirect_stdout(io.StringIO()):
                app.create_snapshot(root, base/'A.fcrstate', mode="full")
                app.create_snapshot(root, base/'B.fcrstate', mode="full")
                app.compare_files(base/'A.fcrstate', base/'B.fcrstate', root/app.OUTPUT_FILE)
            self.assertEqual(hashlib.sha256(doc.read_bytes()).hexdigest(), initial)
            self.assertEqual({p.name for p in root.iterdir()},
                             {'Business.pdf', app.OUTPUT_FILE})
            self.assertFalse(list(base.rglob('.folder-change-review-*')))

    def test_capture_cannot_overwrite_a_document_as_a_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); doc = root/'Business.pdf'; doc.write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError, 'fcrstate'):
                app.create_snapshot(root, doc, mode="full")
            self.assertEqual(doc.read_bytes(), b'keep')
