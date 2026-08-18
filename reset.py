import os
import sqlite3

basedir = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(basedir, 'boachie_edu.db')

def reset_database():
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print(f"Removed database at: {DB_PATH}")
        except Exception as e:
            print(f"DB removal note: {e}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Users Table (Includes Required Email Address)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            index_number TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            student_level TEXT NOT NULL,
            level_other TEXT,
            enrolled_course TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            approval_status TEXT DEFAULT 'Pending Approval',
            lecturer_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Weekly Availability Slots
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weekly_availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_label TEXT NOT NULL,
            available_date TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Meetings Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            availability_id INTEGER,
            topic TEXT NOT NULL,
            preferred_date TEXT NOT NULL,
            preferred_time TEXT NOT NULL,
            notes TEXT,
            status TEXT DEFAULT 'Pending Review',
            lecturer_response TEXT,
            request_feedback INTEGER DEFAULT 0,
            is_final INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (availability_id) REFERENCES weekly_availability (id)
        )
    ''')

    # Live Online Classes (Created by Dr. Boachie under Meetings)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS online_classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT NOT NULL,
            topic TEXT NOT NULL,
            start_time TEXT NOT NULL,
            duration TEXT NOT NULL,
            end_time TEXT NOT NULL,
            agenda TEXT,
            slides_filename TEXT,
            status TEXT DEFAULT 'Scheduled', -- 'Scheduled', 'Live Now', 'Ended'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Class Waiting Room & Join / Reentry Approval Requests
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS class_join_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            request_type TEXT DEFAULT 'Initial Entry', -- 'Initial Entry' or 'Reentry'
            status TEXT DEFAULT 'Pending', -- 'Pending', 'Approved', 'Denied'
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (class_id) REFERENCES online_classes (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Permanent Attendance Tracking Ledger
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS class_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT DEFAULT 'Present', -- 'Present', 'Absent'
            join_count INTEGER DEFAULT 1,
            first_joined_at TIMESTAMP,
            last_joined_at TIMESTAMP,
            last_left_at TIMESTAMP,
            FOREIGN KEY (class_id) REFERENCES online_classes (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Course Assignments & Lecture Materials
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS course_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT NOT NULL,
            target_level TEXT NOT NULL,
            title TEXT NOT NULL,
            instructions TEXT,
            filename TEXT NOT NULL,
            deadline TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Student Assignment Submissions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            grade TEXT,
            status TEXT DEFAULT 'Submitted - Pending Grade',
            lecturer_feedback TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            graded_at TIMESTAMP,
            FOREIGN KEY (assignment_id) REFERENCES course_assignments (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Theses Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS theses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            stage TEXT NOT NULL,
            abstract TEXT NOT NULL,
            filename TEXT NOT NULL,
            status TEXT DEFAULT 'Under Review',
            supervisor_feedback TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Complaints Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL,
            details TEXT NOT NULL,
            is_anonymous INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Under Review',
            lecturer_response TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Academic Requests Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS academic_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            request_type TEXT NOT NULL,
            purpose TEXT NOT NULL,
            details TEXT,
            status TEXT DEFAULT 'Under Review',
            lecturer_response TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Announcements Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            target_type TEXT DEFAULT 'all',
            target_value TEXT DEFAULT 'All Students',
            priority TEXT DEFAULT 'Normal',
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Interactive Thread Discussion Messages
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS thread_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            sender_type TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # In-System Notifications Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_type TEXT NOT NULL,
            user_id INTEGER,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            target_url TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # External Email Notifications Dispatch Archive
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_email TEXT NOT NULL,
            recipient_name TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT DEFAULT 'Dispatched / Sent',
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print("Database reset successfully with Required Student Email & External Email Dispatch Ledger!")

if __name__ == '__main__':
    reset_database()
