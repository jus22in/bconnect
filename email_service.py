import sqlite3
import os
from datetime import datetime

basedir = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(basedir, 'boachie_edu.db')

def send_external_email(recipient_email, recipient_name, subject, body_text):
    """
    Sends external email alert to student's email address & records in email_logs table.
    """
    if not recipient_email:
        return
    
    print("\n" + "=" * 65)
    print(f"📧 EXTERNAL EMAIL DISPATCHED TO: {recipient_name} <{recipient_email}>")
    print(f"📌 SUBJECT: {subject}")
    print("-" * 65)
    print(f"{body_text}")
    print("=" * 65 + "\n")

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO email_logs (recipient_email, recipient_name, subject, body, status)
            VALUES (?, ?, ?, ?, 'Dispatched / Sent')
        ''', (recipient_email, recipient_name, subject, body_text))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Email logging note: {e}")

def broadcast_external_email(recipient_list, subject, body_template_fn):
    """
    Broadcasts external emails to a list of student dictionary records.
    """
    for student in recipient_list:
        email = student.get('email')
        name = student.get('full_name', 'Student')
        if email:
            body = body_template_fn(student)
            send_external_email(email, name, subject, body)
