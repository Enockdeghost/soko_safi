import csv
import io
import secrets
from datetime import datetime
from flask import current_app, make_response
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch

def send_sms(phone, message):
    print(f"[SMS to {phone}]: {message}")
    return True

def create_notification(user_id, type, message):
    from app.models import Notification
    from app.extensions import db
    notif = Notification(user_id=user_id, type=type, message=message)
    db.session.add(notif)
    db.session.commit()
    return notif

def log_transaction(user_id, action, details, ip_address=None):
    from app.models import TransactionLog
    from app.extensions import db
    log = TransactionLog(user_id=user_id, action=action, details=details, ip_address=ip_address)
    db.session.add(log)
    db.session.commit()
    return log

def generate_pdf_report(lines, title):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    p.setFont("Helvetica-Bold", 16)
    p.drawString(1*inch, height-1*inch, title)
    y = height - 1.5*inch
    p.setFont("Helvetica", 10)
    for line in lines:
        while len(line) > 80 and y > 1*inch:
            p.drawString(1*inch, y, line[:80])
            line = line[80:]
            y -= 0.2*inch
        p.drawString(1*inch, y, line)
        y -= 0.2*inch
        if y < 1*inch:
            p.showPage()
            y = height - 1*inch
            p.setFont("Helvetica", 10)
    p.save()
    buffer.seek(0)
    return buffer

def generate_csv_response(data, headers, filename):
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(headers)
    for row in data:
        cw.writerow(row)
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}.csv"
    output.headers["Content-type"] = "text/csv"
    return output

def mobile_money_charge(phone, amount, reference):
    success = True
    if success:
        transaction_id = f"TXN{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{secrets.randbelow(1000)}"
        return {'success': True, 'transaction_id': transaction_id, 'reference': reference}
    else:
        return {'success': False, 'message': 'Payment failed'}