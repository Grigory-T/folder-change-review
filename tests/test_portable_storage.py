"""Portable ownership, copying, report confinement and input-tree exclusions."""
from runtime_safety import portable_directory
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import folder_change_review as app
import runtime_safety as safety
from state_store import StateHistory


class PortableStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.tool=self.base/'Tool';self.tool.mkdir()
        self.project=self.base/'Project';self.project.mkdir()
        (self.project/'document.pdf').write_bytes(b'document')
        location=portable_directory(self.tool);location.__enter__();self.addCleanup(location.__exit__,None,None,None)

    def capture(self, root=None):
        history=StateHistory(self.tool)
        path=history.new_state_path()
        with contextlib.redirect_stdout(io.StringIO()):state=app.create_snapshot(root or self.project,path)
        return path,state

    def test_ignores_profile_and_system_temp_and_cleans_processing_files(self):
        unused=self.base/'Unused';unused.mkdir();(unused/'sentinel').write_bytes(b'keep')
        old=tempfile.tempdir
        with patch.dict(os.environ,{'LOCALAPPDATA':str(unused),'APPDATA':str(unused),'TEMP':str(unused),'TMP':str(unused)}):
            tempfile.tempdir=None
            try:
                history=StateHistory(self.tool);history.save_settings({'project':str(self.project),'workers':16})
                a,_=self.capture();b,_=self.capture()
                with contextlib.redirect_stdout(io.StringIO()):app.compare_files(a,b,self.tool/app.OUTPUT_FILE)
            finally:tempfile.tempdir=old
        self.assertEqual([p.name for p in unused.iterdir()],['sentinel'])
        self.assertEqual(history.states,self.tool/'states')
        self.assertTrue((self.tool/'settings.json').is_file())
        self.assertEqual(list((self.tool/'work').iterdir()),[])
        self.assertFalse((self.tool/'.states').exists())

    def test_copy_folder_preserves_history_settings_and_offline_comparison(self):
        history=StateHistory(self.tool)
        history.save_settings({'project':str(self.tool),'workers':32,'review_mode':'sampled','report_directory':'unused'})
        (self.tool/'own.pdf').write_bytes(b'own')
        a,_=self.capture(self.tool);b,_=self.capture(self.tool)
        destination=self.base/'Copied Tool';shutil.copytree(self.tool,destination)
        shutil.rmtree(self.tool)
        with portable_directory(destination):
            copied=StateHistory(destination)
            self.assertEqual(copied.settings()['project'],str(destination))
            self.assertEqual(copied.settings()['workers'],32)
            self.assertNotIn('report_directory',copied.settings())
            items,errors=copied.list_states();self.assertEqual(len(items),2);self.assertFalse(errors)
            with contextlib.redirect_stdout(io.StringIO()):counts=app.compare_files(destination/'states'/a.name,destination/'states'/b.name,destination/app.OUTPUT_FILE)
            self.assertEqual(counts,{'Unchanged':1})
            self.assertTrue((destination/app.OUTPUT_FILE).is_file())

    def test_self_scan_excludes_only_its_actual_supporting_paths(self):
        for name in ('states','runtime','work'):
            folder=self.tool/name;folder.mkdir();(folder/'ignored.bin').write_bytes(b'ignored')
        (self.tool/'settings.json').write_text('{}')
        (self.tool/'document.pdf').write_bytes(b'doc')
        ordinary=self.tool/'User files'/'states';ordinary.mkdir(parents=True);(ordinary/'keep.pdf').write_bytes(b'keep')
        (self.tool/'folder-change-review.exe').write_bytes(b'tool')
        a,state=self.capture(self.tool)
        self.assertEqual({row['parts'][-1] for row in state['files']},{'document.pdf','keep.pdf'})
        self.assertEqual(len(state['excluded_tool_paths']),5)
        b,_=self.capture(self.tool)
        self.assertEqual({row['Status'] for row in app.compare_snapshots(app.load_snapshot(a),app.load_snapshot(b))},{'Unchanged'})

    def test_state_or_report_outside_tool_is_rejected_without_replacement(self):
        outside=self.base/'outside.fcrstate';outside.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError,'containing the EXE'):app.create_snapshot(self.project,outside)
        self.assertEqual(outside.read_bytes(),b'keep')
        a,_=self.capture();report=self.base/'outside.xlsx';report.write_bytes(b'keep')
        with self.assertRaises(ValueError):app.compare_files(a,a,report)
        self.assertEqual(report.read_bytes(),b'keep')
        with self.assertRaises(ValueError):app.load_snapshot(outside)

    def test_application_root_inside_project_keeps_documents_read_only(self):
        document=self.tool/'document.pdf';document.write_bytes(b'keep')
        before=hashlib.sha256(document.read_bytes()).hexdigest()
        with safety.safe_operation((self.tool,),self.tool):
            with self.assertRaises(PermissionError):document.write_bytes(b'bad')
            with self.assertRaises(PermissionError):(self.tool/'other.txt').write_bytes(b'bad')
            self.assertTrue(safety.inside(tempfile.gettempdir(),self.tool/'work'))
        self.assertEqual(hashlib.sha256(document.read_bytes()).hexdigest(),before)
        self.capture(self.tool)

    def test_supporting_folder_cannot_be_selected_as_project(self):
        (self.tool/'runtime').mkdir()
        with self.assertRaises(ValueError):self.capture(self.tool/'runtime')

    def test_unrelated_same_named_user_folders_remain_visible(self):
        for name in ('states','work','runtime'):
            folder=self.project/name;folder.mkdir();(folder/'doc.pdf').write_bytes(b'doc')
        _,state=self.capture()
        self.assertEqual(state['file_count'],4)

    def test_portable_data_symlink_does_not_write_or_read_outside_tool(self):
        target=self.base/'Outside';target.mkdir();(target/'sentinel').write_bytes(b'keep')
        link=self.tool/'states'
        if os.name=='nt':
            import subprocess
            subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],check=True,capture_output=True)
        else:link.symlink_to(target,target_is_directory=True)
        history=StateHistory(self.tool)
        with self.assertRaises(ValueError):history.new_state_path()
        items,errors=history.list_states();self.assertEqual(items,[]);self.assertTrue(errors)
        self.assertEqual([p.name for p in target.iterdir()],['sentinel'])

    def test_older_format_five_modes_remain_readable(self):
        path,state=self.capture();old=copy.deepcopy(state);old['version']=5;old.pop('excluded_tool_paths')
        oldpath=self.tool/'old.json';oldpath.write_text(json.dumps(old))
        self.assertEqual(app.compare_snapshots(app.load_snapshot(oldpath),state)[0]['Status'],'Unchanged')

    def test_cli_automatically_saves_states_beside_exe(self):
        with contextlib.redirect_stdout(io.StringIO()):code=app.main(['snapshot','--root',str(self.project)])
        self.assertEqual(code,0)
        self.assertEqual(len(StateHistory(self.tool).list_states()[0]),1)

    def test_saved_exclusions_apply_to_both_inventories_without_source_lookup(self):
        _,current=self.capture(self.tool)
        earlier=copy.deepcopy(current);earlier['version']=5;earlier.pop('excluded_tool_paths')
        earlier['files'].append({'path':str(self.tool/'work'/'old.bin'),'parts':['work','old.bin'],'size':1,'sha256':None,'mtime_ns':1})
        with patch.object(app,'portable_exclusions',side_effect=AssertionError('Offline compare must not inspect source')):
            self.assertEqual(app.compare_snapshots(earlier,current),[])

    def test_linked_legacy_directory_does_not_import_external_history_or_settings(self):
        target=self.base/'Outside';target.mkdir()
        (target/'settings.json').write_text('{"workers":32}')
        (target/'unreadable.fcrstate').write_bytes(b'not a state')
        link=self.tool/'.states'
        if os.name=='nt':
            import subprocess
            subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],check=True,capture_output=True)
        else:link.symlink_to(target,target_is_directory=True)
        history=StateHistory(self.tool)
        self.assertEqual(history.settings(),{})
        history.save_settings({'workers':16})
        self.assertEqual(list(history.states.iterdir()),[])
        self.assertEqual((target/'settings.json').read_text(),'{"workers":32}')

    def test_malformed_exclusion_metadata_is_rejected(self):
        from state_store import validate_mode
        _,state=self.capture()
        for paths in (["."],["../states"],["C:states"],["unrelated"],[None]):
            bad=copy.deepcopy(state);bad['excluded_tool_paths']=paths
            with self.subTest(paths=paths),self.assertRaises(ValueError):validate_mode(bad)
        bad=copy.deepcopy(state);bad['root']=None
        with self.assertRaises(ValueError):validate_mode(bad)
