"""Shared validation and real downloadable report formats."""
from io import BytesIO, StringIO
import csv
from html import escape
from flask import Response, send_file


def text_field(data,key,limit=200,required=True):
    value=str(data.get(key,'')).strip()
    if (required and not value) or len(value)>limit: raise ValueError(f'{key.replace("_"," ").title()} is required and must be at most {limit} characters.' if required else f'{key} is too long.')
    return value


def export_report(title,headers,rows,kind):
    if kind=='csv':
        buffer=StringIO();writer=csv.writer(buffer);writer.writerow(headers)
        writer.writerows([("'"+str(v)) if str(v).startswith(('=','+','-','@')) else v for v in row] for row in rows)
        return Response('\ufeff'+buffer.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="report.csv"','Cache-Control':'private, no-store'})
    if kind=='xlsx':
        from openpyxl import Workbook
        workbook=Workbook();sheet=workbook.active;sheet.title='Report';sheet.append(headers)
        for row in rows:
            sheet.append([str(v) if v is not None else '' for v in row])
            for cell in sheet[sheet.max_row]: cell.data_type='s'
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for col in sheet.columns: sheet.column_dimensions[col[0].column_letter].width=min(45,max(16,max(len(str(c.value or '')) for c in col)+2))
        buffer=BytesIO();workbook.save(buffer);buffer.seek(0)
        response=send_file(buffer,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',as_attachment=True,download_name='report.xlsx')
    elif kind=='pdf':
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import A4,landscape
        from reportlab.lib import colors
        buffer=BytesIO();styles=getSampleStyleSheet();document=SimpleDocTemplate(buffer,pagesize=landscape(A4),leftMargin=24,rightMargin=24,topMargin=24,bottomMargin=24)
        values=[[Paragraph(escape(str(v or '')),styles['Normal']) for v in row] for row in [headers]+rows]
        table=Table(values,repeatRows=1,colWidths=[(landscape(A4)[0]-48)/len(headers)]*len(headers))
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E7F8E9')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#D6E5D7')),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
        document.build([Paragraph(escape(title),styles['Title']),Spacer(1,12),table]);buffer.seek(0)
        response=send_file(buffer,mimetype='application/pdf',as_attachment=True,download_name='report.pdf')
    else: raise ValueError('Select CSV, Excel or PDF.')
    response.headers['Cache-Control']='private, no-store';return response
