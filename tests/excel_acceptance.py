"""Native Excel acceptance; run in an interactive Windows session with pywin32."""
import argparse
import hashlib
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--rows', type=int, required=True)
    parser.add_argument('--added', type=int, required=True)
    parser.add_argument('--deleted', type=int, required=True)
    parser.add_argument('--changed', type=int, required=True)
    parser.add_argument('--changed-file', help='Expected filename in a single changed-file drill-down')
    parser.add_argument('--expect-file', action='append', default=[], help='Filename whose exact native Excel text must be present')
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    import win32com.client
    excel = win32com.client.DispatchEx('Excel.Application')
    book = None
    checksum = hashlib.sha256(args.report.read_bytes()).hexdigest()
    try:
        excel.Visible = True
        excel.DisplayAlerts = False
        excel.AutomationSecurity = 3
        started = time.perf_counter()
        book = excel.Workbooks.Open(Filename=str(args.report.resolve()), UpdateLinks=0,
                                    ReadOnly=True, AddToMru=False, CorruptLoad=0)
        opened = time.perf_counter() - started
        sheet = book.Worksheets('Changes')
        assert book.FileFormat == 51 and book.ReadOnly and book.Worksheets.Count == 1
        assert sheet.ListObjects.Count == 0 and sheet.UsedRange.HasFormula is False
        assert sheet.Hyperlinks.Count == 0
        source = sheet.AutoFilter.Range
        assert source.Row == 6 and source.Column == 2 and source.Rows.Count == args.rows + 1
        last = source.Column + source.Columns.Count - 1
        headers = [sheet.Cells(6, column).Value for column in range(2, last + 1)]
        assert headers[0] == 'Row number' and headers[-1] == 'last'
        assert 'Full path' not in headers and 'FullPath' not in headers and 'Leaf' not in headers and not any('SHA' in name.upper() for name in headers)
        levels = [name for name in headers if name.startswith('Level ')]
        assert headers == ['Row number', *levels, 'Leaf depth', 'Name without extension',
                           'File name', 'Extension', 'Size A (MiB)', 'Size B (MiB)',
                           'Status', 'Added', 'Deleted', 'Changed', 'last']
        assert sheet.Cells(2,2).Value.startswith('Table: File changes in folder ')
        assert sheet.Rows(6).RowHeight == 72 and excel.ActiveWindow.Zoom == 85
        assert not excel.ActiveWindow.FreezePanes
        assert sheet.Cells(6,2).Interior.Color == 0 and sheet.Cells(6,last).Interior.Color == 0
        assert sheet.Cells(6,3).Interior.Color == 15773696
        def column_values(column):
            if args.rows == 0:
                return []
            if args.rows == 1:
                return [(sheet.Cells(7,column).Value,)]
            return sheet.Range(sheet.Cells(7,column),sheet.Cells(6+args.rows,column)).Value
        if args.rows:
            body = sheet.Range(sheet.Cells(7,2),sheet.Cells(6+args.rows,last))
            assert body.Interior.Pattern == -4142
        for name in ('Added','Deleted','Changed'):
            column = headers.index(name)+2
            values = column_values(column)
            assert all(row[0] in (None,1) for row in values)
        for name in ('Size A (MiB)','Size B (MiB)'):
            column = headers.index(name)+2
            if args.rows:
                assert sheet.Range(sheet.Cells(7,column),sheet.Cells(6+args.rows,column)).NumberFormat == '#,##0.00'
        column = headers.index('Extension')+2
        values = column_values(column)
        assert all(row[0] is None or not row[0].startswith('.') for row in values)
        if args.expect_file:
            names = {row[0] for row in column_values(headers.index('File name')+2)}
            assert set(args.expect_file) <= names, (args.expect_file,names)
        started = time.perf_counter()
        expected = {'Added':args.added,'Deleted':args.deleted,'Changed':args.changed,'last':args.rows}
        actual = {}
        if args.rows:
            cache = book.PivotCaches().Create(SourceType=1, SourceData="'Changes'!"+source.Address)
            pivot_sheet = book.Worksheets.Add()
            pivot = cache.CreatePivotTable(TableDestination=pivot_sheet.Range('A3'),TableName='AcceptancePivot')
            pivot.PivotFields('Status').Orientation = 1
            for name, value in expected.items():
                pivot.AddDataField(pivot.PivotFields(name), 'Sum '+name, -4157)
                actual[name] = pivot.GetPivotData('Sum '+name).Value
                # With numeric 1/blank source flags, an entirely blank field
                # can produce a blank zero total in native Excel.
                assert actual[name] == value or (actual[name] is None and value == 0), (name,actual[name],value)
        if args.changed_file:
            pivot.GetPivotData('Sum Changed','Status','Changed').ShowDetail = True
            detail = book.ActiveSheet
            assert detail.UsedRange.Rows.Count == 2
            names = [detail.Cells(1,c).Value for c in range(1,detail.UsedRange.Columns.Count+1)]
            assert detail.Cells(2,names.index('File name')+1).Value == args.changed_file
        elapsed = time.perf_counter() - started
        result = {'normal_excel_open':True,'rows':args.rows,'plain_data_format':True,
                  'pivot_sums':actual if args.rows else None,'changed_file_drilldown':bool(args.changed_file),
                  'open_seconds':round(opened,3),'pivot_seconds':round(elapsed,3)}
        book.Close(SaveChanges=False); book = None
        assert hashlib.sha256(args.report.read_bytes()).hexdigest() == checksum
        args.receipt.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    finally:
        if book is not None:book.Close(SaveChanges=False)
        excel.Quit()


if __name__ == '__main__':
    main()
