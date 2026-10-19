from runtime_safety import portable_directory
"""Real Tk workflow tests; use xvfb-run on a headless Linux host."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

import folder_change_review as core
from folder_change_review_ui import Application


class DesktopWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            probe = tk.Tk()
            probe.withdraw()
            probe.destroy()
        except tk.TclError as error:
            raise unittest.SkipTest('Tk display unavailable; use xvfb-run for UI tests') from error

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        location = portable_directory(self.temp.name)
        location.__enter__()
        self.addCleanup(location.__exit__, None, None, None)
        self.work = Path(self.temp.name)
        environment = patch.dict(os.environ, {"LOCALAPPDATA": str(self.work/"MachineData")})
        environment.start(); self.addCleanup(environment.stop)
        self.project = self.work/'Project'
        self.project.mkdir()
        self.directory = self.work/'Application'
        self.directory.mkdir()
        self.window = tk.Tk()
        self.window.withdraw()
        self.app = Application(self.window, self.directory)
        self.initial_mode = self.app.mode.get()
        self.app.mode.set(core.REVIEW_MODES["full"])
        self.window.geometry('+10000+10000')
        self.window.deiconify()
        self.window.update()
        self.dialog = patch('folder_change_review_ui.messagebox.showerror').start()

    def tearDown(self):
        self.wait()
        self.app.close()
        patch.stopall()
        self.temp.cleanup()

    def wait(self):
        deadline = time.monotonic()+5
        while self.app.busy and time.monotonic() < deadline:
            self.window.update()
            time.sleep(.01)
        self.assertFalse(self.app.busy, 'Background operation did not finish')
        self.window.update()

    def states(self, count=3):
        for index in range(count):
            (self.project/'file.pdf').write_bytes(bytes([index]))
            with contextlib.redirect_stdout(io.StringIO()):
                core.create_snapshot(self.project, self.app.history.new_state_path(), 1, mode="full")
        self.app.refresh(select_latest=True)
        self.window.update()

    def selected_paths(self):
        return tuple(self.app.items[box.current()]['path'] for box in (self.app.before_box,self.app.after_box))

    def assert_idle(self):
        self.assertFalse(self.app.busy)
        self.assertEqual(self.app.capture_progress.winfo_manager(), '')
        self.assertEqual(self.app.compare_progress.winfo_manager(), '')
        self.assertEqual(float(self.app.capture_progress['value']), 0)
        self.assertEqual(float(self.app.compare_progress['value']), 0)

    def test_empty_history_and_blank_project_have_clear_idle_actions(self):
        self.assert_idle()
        self.assertTrue(self.app.capture_button.instate(['disabled']))
        self.assertTrue(self.app.compare_button.instate(['disabled']))
        self.assertIn('first state', self.app.compare_status.get())
        self.assertIn('Choose a project', self.app.capture_status.get())

    def test_new_install_defaults_to_quick_and_mode_is_saved_and_locked_when_busy(self):
        self.assertEqual(self.initial_mode, core.REVIEW_MODES['quick'])
        self.app.mode.set(core.REVIEW_MODES['sampled'])
        self.assertIn('samples', self.app.mode_help.get())
        self.app.project.set(str(self.project))
        (self.project/'file.pdf').write_bytes(b'data')
        self.app.capture_button.invoke()
        self.assertTrue(self.app.mode_box.instate(['disabled']))
        self.wait()
        self.assertEqual(self.app.history.settings()['review_mode'],'sampled')
        self.assertIn('Sampled contents', self.app.labels[0])
        self.assertFalse(self.app.mode_box.instate(['disabled']))

    def test_different_modes_disable_report_and_explain_recovery(self):
        (self.project/'file.pdf').write_bytes(b'data')
        for mode in ('quick','full'):
            with contextlib.redirect_stdout(io.StringIO()):
                core.create_snapshot(self.project,self.app.history.new_state_path(),mode=mode)
        self.app.refresh(select_latest=True)
        self.assertTrue(self.app.compare_button.instate(['disabled']))
        self.assertIn('Different review modes',self.app.compare_status.get())
        self.app.compare()
        self.assertEqual(list(self.directory.glob('*.xlsx')),[])

    def test_capture_shows_only_its_progress_then_hides_it(self):
        (self.project/'file.pdf').write_bytes(b'data')
        self.app.project.set(str(self.project))
        self.app.capture_button.invoke()
        self.assertTrue(self.app.busy)
        self.assertEqual(self.app.capture_progress.winfo_manager(),'grid')
        self.assertEqual(self.app.compare_progress.winfo_manager(),'')
        self.assertTrue(self.app.compare_button.instate(['disabled']))
        self.wait()
        self.assert_idle()
        self.assertEqual(len(self.app.items),1)
        self.assertIn('1 files',self.app.capture_status.get())
        self.assertIn('later time',self.app.compare_status.get())
        self.assertTrue(self.app.compare_button.instate(['disabled']))

    def test_compare_works_without_project_and_preserves_chosen_pair(self):
        self.states()
        self.app.before_box.current(2)
        self.app.after_box.current(1)
        self.app.selection_details()
        selected = self.selected_paths()
        (self.project/'file.pdf').unlink()
        self.project.rmdir()  # Comparing states is independent of the live folder.
        self.app.compare_button.invoke()
        self.assertTrue(self.app.busy)
        self.assertEqual(self.app.compare_progress.winfo_manager(),'grid')
        self.assertEqual(self.app.capture_progress.winfo_manager(),'')
        self.wait()
        self.assert_idle()
        self.assertEqual(self.selected_paths(),selected)
        self.assertEqual(len(list(self.directory.glob('*.xlsx'))),1)
        self.assertIn('Changed: 1',self.app.compare_status.get())
        self.assertIn('Last report:',self.app.report_name.get())
        self.assertTrue(self.app.capture_button.instate(['disabled']))

    def test_same_state_disables_compare_and_reverse_order_is_explained(self):
        self.states(2)
        self.app.before_box.current(0)
        self.app.after_box.current(0)
        self.app.selection_details()
        self.assertTrue(self.app.compare_button.instate(['disabled']))
        self.app.compare_button.invoke()
        self.assertEqual(list(self.directory.glob('*.xlsx')),[])
        self.app.after_box.current(1)
        self.app.selection_details()
        self.assertFalse(self.app.compare_button.instate(['disabled']))
        self.assertIn('newer than B',self.app.compare_status.get())
        self.assert_idle()

    def test_capture_failure_restores_controls_and_preserves_comparison(self):
        self.states()
        self.app.before_box.current(2)
        self.app.after_box.current(1)
        self.app.selection_details()
        selected = self.selected_paths()
        self.app.project.set(str(self.project))
        with patch('folder_change_review_ui.create_snapshot',side_effect=OSError('unreadable file')):
            self.app.capture_button.invoke()
            self.wait()
        self.assert_idle()
        self.assertEqual(self.selected_paths(),selected)
        self.assertEqual(len(self.app.items),3)
        self.assertIn('not saved',self.app.capture_status.get())
        self.assertFalse(self.app.capture_button.instate(['disabled']))
        self.dialog.assert_called_once()

    def test_partial_capture_is_visible_and_comparison_marks_unknown(self):
        self.states(1)
        self.app.project.set(str(self.project))
        with patch.object(core, 'hash_file', side_effect=PermissionError(13, 'Access denied', str(self.project/'file.pdf'))):
            self.app.capture_button.invoke()
            self.wait()
        self.assert_idle()
        self.assertEqual(len(self.app.items), 2)
        self.assertIn('Incomplete coverage', self.app.capture_status.get())
        self.assertIn('read issues', self.app.labels[0])
        self.assertFalse(self.app.issues_button.instate(['disabled']))
        self.app.selection_details()
        self.assertIn('Incomplete coverage', self.app.compare_status.get())
        self.app.issues_button.invoke()
        dialogs = [widget for widget in self.window.winfo_children() if isinstance(widget, tk.Toplevel)]
        self.assertEqual(len(dialogs), 1)
        dialogs[0].destroy()
        self.app.compare_button.invoke()
        self.wait()
        self.assert_idle()
        self.assertIn('Unknown: 1', self.app.compare_status.get())
        self.dialog.assert_not_called()

    def test_application_inside_project_captures_and_compares_without_own_artifacts(self):
        self.app.close()
        self.directory=self.project/'Tool';self.directory.mkdir()
        (self.directory/'folder-change-review.exe').write_bytes(b'tool')
        (self.directory/core.OUTPUT_FILE).write_bytes(b'previous report')
        (self.project/'doc.pdf').write_bytes(b'before')
        self.window=tk.Tk();self.window.withdraw()
        self.app=Application(self.window,self.directory)
        self.app.project.set("'"+str(self.project)+"'")
        self.app.capture_button.invoke();self.wait()
        (self.project/'doc.pdf').write_bytes(b'after longer')
        self.app.capture_button.invoke();self.wait()
        self.assertEqual([item['metadata']['file_count'] for item in self.app.items],[1,1])
        self.app.compare_button.invoke();self.wait()
        self.assertTrue((self.directory/core.OUTPUT_FILE).exists())
        self.assertIn('Changed: 1',self.app.compare_status.get())
        self.app.capture_button.invoke();self.wait()
        self.assertEqual(self.app.items[0]['metadata']['file_count'],1)
        self.assert_idle();self.dialog.assert_not_called()

    def test_report_stays_beside_exe_and_preserves_previous_on_failure(self):
        self.states(2)
        self.assertFalse(hasattr(self.app,'report_folder_button'))
        self.app.compare_button.invoke();self.wait()
        report=self.directory/core.OUTPUT_FILE
        self.assertTrue(report.exists())
        self.assertNotIn('report_directory',self.app.history.settings())
        previous=report.read_bytes()
        with patch('folder_change_review_ui.compare_files',side_effect=PermissionError(13,'locked',str(report))):
            self.app.compare_button.invoke();self.wait()
        self.assertEqual(report.read_bytes(),previous)
        self.assertIn('Close it in Excel',self.dialog.call_args.args[1])
        self.app.compare_button.invoke();self.wait()
        self.assertEqual(len(list(self.directory.glob('*.xlsx'))),1)
        self.assert_idle()

    def test_filesystem_validation_is_background_and_close_waits(self):
        entered, release = threading.Event(), threading.Event()
        main_thread = threading.get_ident()
        def delayed_validation(*args, **kwargs):
            self.assertNotEqual(threading.get_ident(),main_thread)
            entered.set()
            release.wait(3)
            raise ValueError('Unavailable project')
        self.app.project.set(str(self.project))
        with patch('folder_change_review_ui.create_snapshot', side_effect=delayed_validation):
            self.app.capture_button.invoke()
            self.assertTrue(entered.wait(1))
            self.app.close()
            self.assertTrue(self.window.winfo_exists())
            self.assertIn('finish',self.app.capture_status.get())
            release.set()
            self.wait()
        self.assert_idle()
        self.dialog.assert_called_once()

    def test_thread_start_failure_does_not_leave_a_busy_indicator(self):
        self.app.project.set(str(self.project))
        with patch('folder_change_review_ui.threading.Thread.start',side_effect=RuntimeError('cannot start thread')):
            self.app.capture_button.invoke()
            self.wait()
        self.assert_idle()
        self.assertIn('not saved',self.app.capture_status.get())
        self.dialog.assert_called_once()

    def test_compare_failure_keeps_last_report_and_capture_status(self):
        self.states(2)
        self.app.compare_button.invoke()
        self.wait()
        report = self.app.report_name.get()
        capture = self.app.capture_status.get()
        selected = self.selected_paths()
        with patch('folder_change_review_ui.compare_files',side_effect=OSError('cannot write report')):
            self.app.compare_button.invoke()
            self.wait()
        self.assert_idle()
        self.assertEqual(self.app.report_name.get(),report)
        self.assertEqual(self.app.capture_status.get(),capture)
        self.assertEqual(self.selected_paths(),selected)
        self.assertIn('not saved',self.app.compare_status.get())
        self.dialog.assert_called_once()

    def test_large_fonts_keep_fields_aligned_and_footer_accessible(self):
        self.app.close()
        self.window = tk.Tk()
        self.window.withdraw()
        scaling = self.window.tk.call('tk','scaling')
        self.window.tk.call('tk','scaling',2.0)
        try:
            self.app = Application(self.window,self.directory)
            self.window.geometry('820x600+10000+10000')
            self.window.deiconify()
            self.window.update()
            self.assertEqual(self.app.project_entry.winfo_rootx(),self.app.before_box.winfo_rootx())
            self.assertEqual(self.app.capture_button.winfo_width(),self.app.compare_button.winfo_width())
            self.assertLessEqual(self.app.open_button.winfo_rooty()+self.app.open_button.winfo_height(),
                                 self.window.winfo_rooty()+self.window.winfo_height())
            self.assert_idle()
        finally:
            self.window.tk.call('tk','scaling',scaling)

    def test_duplicate_labels_remain_selectable_and_refresh_keeps_selection(self):
        self.states(2)
        entries = self.app.items
        entries[1]['metadata'] = dict(entries[0]['metadata'])
        with patch.object(self.app.history,'list_states',return_value=(entries,[])):
            self.app.refresh(select_latest=True)
            self.assertEqual(len(set(self.app.labels)),2)
            self.assertEqual(self.app.before_box.current(),1)
            self.assertEqual(self.app.after_box.current(),0)
            self.assertFalse(self.app.compare_button.instate(['disabled']))
            selected = self.selected_paths()
            self.app.refresh()
            self.assertEqual(self.selected_paths(),selected)

    def test_short_window_scrolls_cards_but_keeps_footer_visible(self):
        self.states(2)
        self.window.minsize(820,440)
        self.window.geometry('820x440')
        self.window.update()
        self.assertEqual(self.app.scrollbar.winfo_manager(),'grid')
        self.assertLess(self.app.canvas.yview()[1],1)
        self.assertEqual(self.app.open_button.winfo_manager(),'grid')
        self.assertLessEqual(self.app.open_button.winfo_rooty()+self.app.open_button.winfo_height(),
                             self.window.winfo_rooty()+self.window.winfo_height())
        self.assertEqual(self.app.capture_button.winfo_width(),self.app.compare_button.winfo_width())
        self.assertEqual(self.app.capture_button.winfo_rootx(),self.app.compare_button.winfo_rootx())
        self.assertEqual(self.app.compare_button.winfo_reqwidth(),self.app.open_button.winfo_reqwidth())
        # A noninteractive Windows desktop can force a width below the window
        # manager minimum. Native console acceptance covers rendered geometry.
        if self.window.winfo_width() >= 820:
            self.assertLessEqual(abs(self.app.compare_button.winfo_rootx()+self.app.compare_button.winfo_width()
                                     -self.app.open_button.winfo_rootx()-self.app.open_button.winfo_width()),1)
        self.assertEqual(self.app.project_entry.winfo_rootx(),self.app.before_box.winfo_rootx())


if __name__ == '__main__':
    unittest.main()
