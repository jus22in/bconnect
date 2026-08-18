import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from werkzeug.utils import secure_filename
from email_service import send_external_email, broadcast_external_email

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dr-boachie-admin-secret-2026'

basedir = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(basedir, 'boachie_edu.db')
UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.template_filter('format_date')
def format_date_filter(val, fmt='%b %d, %Y'):
    if not val:
        return ''
    if isinstance(val, str):
        try:
            clean_val = val.replace('T', ' ')[:19]
            dt = datetime.strptime(clean_val, '%Y-%m-%d %H:%M:%S')
            return dt.strftime(fmt)
        except Exception:
            return val[:10]
    try:
        return val.strftime(fmt)
    except Exception:
        return str(val)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def query_db(query, args=(), one=False):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id

def is_lecturer_logged_in():
    return session.get('lecturer_logged') == True

def get_thread_messages(item_type, item_id):
    return query_db('SELECT * FROM thread_messages WHERE item_type = ? AND item_id = ? ORDER BY created_at ASC', (item_type, item_id))

def get_lecturer_notifications():
    return query_db("SELECT * FROM notifications WHERE recipient_type = 'lecturer' ORDER BY created_at DESC LIMIT 10")

@app.context_processor
def inject_lecturer_notifications():
    if is_lecturer_logged_in():
        notifs = get_lecturer_notifications()
        unread_count = sum(1 for n in notifs if n['is_read'] == 0)
        return dict(notifications=notifs, unread_notif_count=unread_count)
    return dict(notifications=[], unread_notif_count=0)

# Serve Uploaded Document Attachments
@app.route('/uploads/<path:filename>')
def custom_uploads(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        return send_from_directory(app.config['UPLOAD_FOLDER'], 'sample_document.txt')
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Routes
@app.route('/mark-notification/<int:notif_id>')
def mark_notification(notif_id):
    execute_db('UPDATE notifications SET is_read = 1 WHERE id = ?', (notif_id,))
    target = request.args.get('target', url_for('dashboard'))
    return redirect(target)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['lecturer_logged'] = True
        flash('Welcome back, Dr. Boachie! You are logged into your workspace.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('lecturer/login.html')

@app.route('/logout')
def logout():
    session.pop('lecturer_logged', None)
    flash('You have signed out of Bconnect Workspace.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@app.route('/dashboard')
def dashboard():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    students_count = query_db('SELECT COUNT(*) as count FROM users WHERE approval_status = "Approved"', one=True)['count']
    pending_approvals_count = query_db('SELECT COUNT(*) as count FROM users WHERE approval_status = "Pending Approval"', one=True)['count']
    meetings_count = query_db('SELECT COUNT(*) as count FROM meetings WHERE status = "Pending Review"', one=True)['count']
    active_slots_count = query_db('SELECT COUNT(*) as count FROM weekly_availability WHERE is_active = 1', one=True)['count']

    recent_students = query_db('SELECT * FROM users WHERE approval_status = "Approved" ORDER BY created_at DESC LIMIT 5')
    recent_meetings = query_db('''
        SELECT meetings.*, users.full_name, users.index_number, users.student_level, users.enrolled_course
        FROM meetings
        JOIN users ON meetings.user_id = users.id
        ORDER BY meetings.created_at DESC LIMIT 4
    ''')

    return render_template('lecturer/dashboard.html',
                           students_count=students_count,
                           pending_approvals_count=pending_approvals_count,
                           meetings_count=meetings_count,
                           active_slots_count=active_slots_count,
                           recent_students=recent_students,
                           recent_meetings=recent_meetings)

@app.route('/student-hub', methods=['GET', 'POST'])
def student_hub():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_id = request.form.get('user_id')
        lecturer_notes = request.form.get('lecturer_notes', '').strip()
        execute_db('UPDATE users SET lecturer_notes = ? WHERE id = ?', (lecturer_notes, user_id))
        
        user = query_db('SELECT * FROM users WHERE id = ?', (user_id,), one=True)
        if user and user['email']:
            send_external_email(
                user['email'],
                user['full_name'],
                "💬 Direct Feedback Note from Dr. Christopher Boachie",
                f"Dear {user['full_name']},\n\nDr. Christopher Boachie has added a direct feedback note to your student dossier:\n\n\"{lecturer_notes}\"\n\nLog in at http://127.0.0.1:5000/ to view your academic dashboard.\n\nBest regards,\nBconnect Academic Portal"
            )

        execute_db('''
            INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
            VALUES ('student', ?, 'Direct Feedback from Dr. Boachie', ?, '/dashboard')
        ''', (user_id, f"Dr. Boachie sent feedback: {lecturer_notes[:60]}..."))

        flash('Direct profile feedback note saved to student dossier & external email alert sent!', 'success')
        return redirect(url_for('student_hub', student_id=user_id))

    search = request.args.get('search', '').strip()
    selected_student_id = request.args.get('student_id')

    if search:
        all_students = query_db('''
            SELECT * FROM users
            WHERE (full_name LIKE ? OR index_number LIKE ? OR phone_number LIKE ? OR email LIKE ? OR enrolled_course LIKE ? OR student_level LIKE ?)
            ORDER BY approval_status DESC, student_level ASC, full_name ASC
        ''', (f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%'))
    else:
        all_students = query_db('SELECT * FROM users ORDER BY approval_status DESC, student_level ASC, full_name ASC')

    by_course = {}
    by_level = {}
    for s in all_students:
        crs = s['enrolled_course']
        if crs not in by_course:
            by_course[crs] = []
        by_course[crs].append(s)

        lvl = s['level_other'] if s['student_level'] == 'Other' and s['level_other'] else s['student_level']
        if lvl not in by_level:
            by_level[lvl] = []
        by_level[lvl].append(s)

    selected_student = None
    student_assignments = []
    student_theses = []
    student_meetings = []
    student_complaints = []
    student_requests = []

    if selected_student_id:
        selected_student = query_db('SELECT * FROM users WHERE id = ?', (selected_student_id,), one=True)
        if selected_student:
            student_assignments = query_db('''
                SELECT student_submissions.*, course_assignments.title as assignment_title, course_assignments.course_code
                FROM student_submissions
                JOIN course_assignments ON student_submissions.assignment_id = course_assignments.id
                WHERE student_submissions.user_id = ?
                ORDER BY student_submissions.submitted_at DESC
            ''', (selected_student_id,))

            student_theses = query_db('SELECT * FROM theses WHERE user_id = ? ORDER BY submitted_at DESC', (selected_student_id,))
            student_meetings = query_db('SELECT * FROM meetings WHERE user_id = ? ORDER BY created_at DESC', (selected_student_id,))
            student_complaints = query_db('SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC', (selected_student_id,))
            student_requests = query_db('SELECT * FROM academic_requests WHERE user_id = ? ORDER BY created_at DESC', (selected_student_id,))

    return render_template('lecturer/student_hub.html',
                           all_students=all_students,
                           by_course=by_course,
                           by_level=by_level,
                           search=search,
                           selected_student=selected_student,
                           student_assignments=student_assignments,
                           student_theses=student_theses,
                           student_meetings=student_meetings,
                           student_complaints=student_complaints,
                           student_requests=student_requests)

@app.route('/approve-student', methods=['POST'])
def approve_student():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    user_id = request.form.get('user_id')
    action = request.form.get('action')

    user = query_db('SELECT * FROM users WHERE id = ?', (user_id,), one=True)
    if not user:
        flash('Student record not found.', 'danger')
        return redirect(url_for('students'))

    if action == 'approve':
        execute_db('UPDATE users SET approval_status = "Approved" WHERE id = ?', (user_id,))
        
        execute_db('''
            INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
            VALUES ('student', ?, 'Student Account Registration Approved!', 'Dr. Christopher Boachie approved your registration request. You may now log in.', '/login')
        ''', (user_id,))

        if user['email']:
            send_external_email(
                user['email'],
                user['full_name'],
                "✓ Bconnect Student Account Registration Approved!",
                f"Dear {user['full_name']},\n\nGreat news! Dr. Christopher Boachie has verified and approved your student account registration for {user['enrolled_course']} ({user['index_number']}).\n\nYou may now log in using your password at:\nhttp://127.0.0.1:5000/login\n\nWelcome to Bconnect!\nDr. Christopher Boachie Academic Portal"
            )

        flash(f'✓ Student registration approved & external email sent for {user["full_name"]} ({user["index_number"]})!', 'success')
    elif action == 'reject':
        execute_db('UPDATE users SET approval_status = "Rejected" WHERE id = ?', (user_id,))
        flash(f'Student registration declined for {user["full_name"]}.', 'warning')

    return redirect(request.form.get('redirect_url', url_for('students')))

# BATCH APPROVE ALL PENDING STUDENT REGISTRATIONS
@app.route('/approve-all-students', methods=['POST'])
def approve_all_students():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    pending_list = query_db('SELECT id, full_name, email, index_number, enrolled_course FROM users WHERE approval_status = "Pending Approval"')
    if pending_list:
        execute_db('UPDATE users SET approval_status = "Approved" WHERE approval_status = "Pending Approval"')
        
        for p in pending_list:
            execute_db('''
                INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
                VALUES ('student', ?, 'Student Account Registration Approved!', 'Dr. Christopher Boachie approved your registration request. You may now log in.', '/login')
            ''', (p['id'],))

            if p['email']:
                send_external_email(
                    p['email'],
                    p['full_name'],
                    "✓ Bconnect Student Account Registration Approved!",
                    f"Dear {p['full_name']},\n\nGreat news! Dr. Christopher Boachie has verified and approved your student account registration for {p['enrolled_course']} ({p['index_number']}).\n\nYou may now log in using your password at:\nhttp://127.0.0.1:5000/login\n\nWelcome to Bconnect!\nDr. Christopher Boachie Academic Portal"
                )

        flash(f'✓ ACCEPT ALL SUCCESSFUL: Approved all {len(pending_list)} pending student registration requests & dispatched external email alerts!', 'success')
    else:
        flash('No pending student registrations to approve.', 'info')

    return redirect(request.form.get('redirect_url', url_for('students')))

@app.route('/students', methods=['GET', 'POST'])
def students():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_id = request.form.get('user_id')
        lecturer_notes = request.form.get('lecturer_notes', '').strip()
        execute_db('UPDATE users SET lecturer_notes = ? WHERE id = ?', (lecturer_notes, user_id))
        
        user = query_db('SELECT * FROM users WHERE id = ?', (user_id,), one=True)
        if user and user['email']:
            send_external_email(
                user['email'],
                user['full_name'],
                "💬 Direct Feedback Note from Dr. Christopher Boachie",
                f"Dear {user['full_name']},\n\nDr. Christopher Boachie has added a direct feedback note to your student profile:\n\n\"{lecturer_notes}\"\n\nLog in at http://127.0.0.1:5000/ to view your academic dashboard.\n\nBest regards,\nBconnect Academic Portal"
            )

        execute_db('''
            INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
            VALUES ('student', ?, 'Direct Feedback from Dr. Boachie', ?, '/dashboard')
        ''', (user_id, f"Dr. Boachie sent feedback: {lecturer_notes[:60]}..."))

        flash('Direct feedback sent to student profile & external email alert dispatched!', 'success')
        return redirect(url_for('students'))

    search = request.args.get('search', '').strip()
    if search:
        all_students = query_db('''
            SELECT * FROM users
            WHERE (full_name LIKE ? OR index_number LIKE ? OR phone_number LIKE ? OR email LIKE ? OR enrolled_course LIKE ?)
            ORDER BY approval_status DESC, student_level ASC, full_name ASC
        ''', (f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%'))
    else:
        all_students = query_db('SELECT * FROM users ORDER BY approval_status DESC, student_level ASC, full_name ASC')

    pending_students = [s for s in all_students if s['approval_status'] == 'Pending Approval']
    approved_students = [s for s in all_students if s['approval_status'] == 'Approved']

    by_level = {}
    for s in approved_students:
        lvl = s['level_other'] if s['student_level'] == 'Other' and s['level_other'] else s['student_level']
        if lvl not in by_level:
            by_level[lvl] = []
        by_level[lvl].append(s)

    by_course = {}
    for s in approved_students:
        crs = s['enrolled_course']
        if crs not in by_course:
            by_course[crs] = []
        by_course[crs].append(s)

    return render_template('lecturer/students.html',
                           all_students=all_students,
                           pending_students=pending_students,
                           approved_students=approved_students,
                           by_level=by_level,
                           by_course=by_course,
                           search=search)

@app.route('/announcements', methods=['GET', 'POST'])
def announcements():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'delete':
            announcement_id = request.form.get('announcement_id')
            execute_db('DELETE FROM announcements WHERE id = ?', (announcement_id,))
            flash('Announcement deleted.', 'info')
            return redirect(url_for('announcements'))

        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        target_type = request.form.get('target_type', 'all')
        target_value = request.form.get('target_value', 'All Students').strip()
        priority = request.form.get('priority', 'Normal')

        if not title or not content:
            flash('Please complete announcement title and body content.', 'danger')
        else:
            execute_db('''
                INSERT INTO announcements (title, content, target_type, target_value, priority)
                VALUES (?, ?, ?, ?, ?)
            ''', (title, content, target_type, target_value, priority))

            execute_db('''
                INSERT INTO notifications (recipient_type, title, message, target_url)
                VALUES ('student', 'New Official Announcement', ?, '/dashboard')
            ''', (f"Dr. Boachie posted: {title}",))

            # Broadcast external emails
            approved_students = query_db('SELECT full_name, email FROM users WHERE approval_status = "Approved"')
            broadcast_external_email(
                approved_students,
                f"📢 Official Announcement: {title}",
                lambda s: f"Dear {s['full_name']},\n\nDr. Christopher Boachie has posted a new official announcement on Bconnect:\n\nTITLE: {title}\nPRIORITY: {priority}\n\nANNOUNCEMENT DETAILS:\n{content}\n\nLog in at http://127.0.0.1:5000/ to view full details.\n\nBest regards,\nDr. Christopher Boachie Academic Portal"
            )

            flash(f'Announcement published & external email alerts sent to students!', 'success')
            return redirect(url_for('announcements'))

    all_announcements = query_db('SELECT * FROM announcements ORDER BY posted_at DESC')
    all_students = query_db('SELECT full_name, index_number, enrolled_course, student_level FROM users WHERE approval_status = "Approved" ORDER BY full_name ASC')

    return render_template('lecturer/announcements.html', announcements=all_announcements, students=all_students)

@app.route('/meetings', methods=['GET', 'POST'])
def meetings():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_availability':
            week_label = request.form.get('week_label', '').strip()
            available_date = request.form.get('available_date', '').strip()
            time_slot = request.form.get('time_slot', '').strip()
            notes = request.form.get('notes', '').strip()

            if not week_label or not available_date or not time_slot:
                flash('Please specify the week label, date, and time slot.', 'danger')
            else:
                execute_db('''
                    INSERT INTO weekly_availability (week_label, available_date, time_slot, notes, is_active)
                    VALUES (?, ?, ?, ?, 1)
                ''', (week_label, available_date, time_slot, notes))

                execute_db('''
                    INSERT INTO notifications (recipient_type, title, message, target_url)
                    VALUES ('student', '📅 Dr. Boachie Office Hours Published', ?, '/meetings')
                ''', (f"Dr. Christopher Boachie assigned meeting slots for {week_label}: {available_date} ({time_slot}). Click to book your slot.",))

                approved_students = query_db('SELECT full_name, email FROM users WHERE approval_status = "Approved"')
                broadcast_external_email(
                    approved_students,
                    f"📅 Office Hours Slots Published ({week_label})",
                    lambda s: f"Dear {s['full_name']},\n\nDr. Christopher Boachie has published office hours consultation slots for {week_label}:\n\n• Date: {available_date}\n• Time Slot: {time_slot}\n• Notes: {notes or 'N/A'}\n\nYou may now log in to book your 1-on-1 meeting slot at:\nhttp://127.0.0.1:5000/meetings\n\nBest regards,\nDr. Christopher Boachie Academic Portal"
                )

                flash(f'📅 Meeting slot published & external email alerts sent for {week_label}!', 'success')
                return redirect(url_for('meetings'))

        elif action == 'clear_week':
            execute_db('UPDATE weekly_availability SET is_active = 0')
            flash('Past weekly availability slots deactivated. Assign new slots for the current week.', 'info')
            return redirect(url_for('meetings'))

        elif action == 'decide_meeting':
            meeting_id = request.form.get('meeting_id')
            new_status = request.form.get('status')
            lecturer_response = request.form.get('lecturer_response', '').strip()
            req_feedback = 1 if request.form.get('request_feedback') == 'on' else 0

            is_final = 1 if (new_status in ['Declined', 'Completed'] and req_feedback == 0) else 0

            meeting = query_db('SELECT meetings.*, users.full_name, users.email FROM meetings JOIN users ON meetings.user_id = users.id WHERE meetings.id = ?', (meeting_id,), one=True)
            execute_db('''
                UPDATE meetings
                SET status = ?, lecturer_response = ?, request_feedback = ?, is_final = ?
                WHERE id = ?
            ''', (new_status, lecturer_response, req_feedback, is_final, meeting_id))

            if meeting:
                note_text = f"Status: {new_status}. {lecturer_response}"
                if req_feedback == 1:
                    note_text += " (Feedback requested from student)."
                execute_db('''
                    INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
                    VALUES ('student', ?, 'Meeting Request Decision Updated', ?, '/meetings')
                ''', (meeting['user_id'], note_text))

                if meeting['email']:
                    send_external_email(
                        meeting['email'],
                        meeting['full_name'],
                        f"📅 Meeting Booking Decision: {new_status}",
                        f"Dear {meeting['full_name']},\n\nDr. Christopher Boachie has updated your consultation meeting request:\n\nTOPIC: {meeting['topic']}\nDECISION STATUS: {new_status}\nDR. BOACHIE'S NOTES: {lecturer_response}\n\nLog in at http://127.0.0.1:5000/meetings for full details.\n\nBest regards,\nBconnect Academic Portal"
                    )

            flash('Meeting decision updated & external email alert dispatched!', 'success')
            return redirect(url_for('meetings'))

        # Live Online Class Management Actions
        elif action == 'schedule_online_class':
            course_code = request.form.get('course_code', '').strip()
            topic = request.form.get('topic', '').strip()
            start_time = request.form.get('start_time', '').strip()
            duration = request.form.get('duration', '').strip()
            end_time = request.form.get('end_time', '').strip()
            agenda = request.form.get('agenda', '').strip()
            file_input = request.files.get('class_slides_file')

            if file_input and file_input.filename:
                slides_filename = secure_filename(file_input.filename)
                file_input.save(os.path.join(app.config['UPLOAD_FOLDER'], slides_filename))
            else:
                slides_filename = None

            if not course_code or not topic or not start_time or not duration or not end_time:
                flash('Please fill out course code, topic, start time, duration, and end time.', 'danger')
            else:
                execute_db('''
                    INSERT INTO online_classes (course_code, topic, start_time, duration, end_time, agenda, slides_filename, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'Scheduled')
                ''', (course_code, topic, start_time, duration, end_time, agenda, slides_filename))

                execute_db('''
                    INSERT INTO notifications (recipient_type, title, message, target_url)
                    VALUES ('student', '🔴 Upcoming Live Online Class Scheduled', ?, '/meetings')
                ''', (f"Live Class: {course_code} - {topic} on {start_time} (Duration: {duration}). Note: Class room remains locked until session begins.",))

                approved_students = query_db('SELECT full_name, email FROM users WHERE approval_status = "Approved"')
                broadcast_external_email(
                    approved_students,
                    f"🔴 Upcoming Live Online Class: {course_code} - {topic}",
                    lambda s: f"Dear {s['full_name']},\n\nDr. Christopher Boachie has scheduled a Live Online Class:\n\n• Course: {course_code}\n• Lecture Topic: {topic}\n• Start Time: {start_time}\n• Duration: {duration}\n• End Time: {end_time}\n• Agenda: {agenda or 'N/A'}\n\nNOTE: The Live Video Class Room is currently locked and will unlock when Dr. Boachie starts the live session at http://127.0.0.1:5000/meetings.\n\nBest regards,\nDr. Christopher Boachie Academic Portal"
                )

                flash(f'🔴 Live Online Class scheduled! Broadcast email alerts sent to students.', 'success')
                return redirect(url_for('meetings'))

        elif action == 'upload_class_slides':
            class_id = request.form.get('class_id')
            file_input = request.files.get('slides_file')

            if file_input and file_input.filename:
                filename = secure_filename(file_input.filename)
                file_input.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                
                execute_db('UPDATE online_classes SET slides_filename = ? WHERE id = ?', (filename, class_id))
                flash('📚 Course lecture slides uploaded & updated for active Live Class!', 'success')
            else:
                flash('Please select a slide document file (.pdf, .pptx, .docx).', 'warning')

            return redirect(url_for('meetings'))

        elif action == 'start_class':
            class_id = request.form.get('class_id')
            execute_db("UPDATE online_classes SET status = 'Live Now' WHERE id = ?", (class_id,))
            
            oc = query_db('SELECT * FROM online_classes WHERE id = ?', (class_id,), one=True)
            execute_db('''
                INSERT INTO notifications (recipient_type, title, message, target_url)
                VALUES ('student', '🔴 LIVE CLASS NOW OPEN! Request Entry', ?, '/meetings')
            ''', (f"Dr. Boachie unlocked Live Class: {oc['topic']}. Click to request entry from Waiting Room.",))

            approved_students = query_db('SELECT full_name, email FROM users WHERE approval_status = "Approved"')
            broadcast_external_email(
                approved_students,
                f"🔴 LIVE CLASS NOW UNLOCKED: {oc['topic']}",
                lambda s: f"Dear {s['full_name']},\n\nDr. Christopher Boachie has unlocked the Live Online Class room for {oc['course_code']}: {oc['topic']}.\n\nClick the link below to enter the Virtual Waiting Room and request entry:\nhttp://127.0.0.1:5000/meetings\n\nBest regards,\nDr. Christopher Boachie Academic Portal"
            )

            flash('🔴 Live Class session started! Waiting Room entry gate unlocked & email dispatches sent.', 'success')
            return redirect(url_for('meetings'))

        elif action == 'end_class':
            class_id = request.form.get('class_id')
            execute_db("UPDATE online_classes SET status = 'Ended' WHERE id = ?", (class_id,))

            all_approved = query_db('SELECT id FROM users WHERE approval_status = "Approved"')
            for s in all_approved:
                existing_att = query_db('SELECT id FROM class_attendance WHERE class_id = ? AND user_id = ?', (class_id, s['id']), one=True)
                if not existing_att:
                    execute_db('''
                        INSERT INTO class_attendance (class_id, user_id, status, join_count)
                        VALUES (?, ?, 'Absent', 0)
                    ''', (class_id, s['id']))

            flash('Live Class session ended. Final attendance records archived.', 'info')
            return redirect(url_for('meetings'))

        elif action == 'decide_class_join':
            request_id = request.form.get('request_id')
            decision = request.form.get('decision')
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            req_item = query_db('SELECT class_join_requests.*, users.full_name, users.email FROM class_join_requests JOIN users ON class_join_requests.user_id = users.id WHERE class_join_requests.id = ?', (request_id,), one=True)
            if req_item:
                if decision == 'Approve':
                    execute_db("UPDATE class_join_requests SET status = 'Approved' WHERE id = ?", (request_id,))
                    
                    existing_att = query_db('SELECT * FROM class_attendance WHERE class_id = ? AND user_id = ?', (req_item['class_id'], req_item['user_id']), one=True)
                    if existing_att:
                        execute_db('''
                            UPDATE class_attendance
                            SET status = 'Present', join_count = join_count + 1, last_joined_at = ?
                            WHERE id = ?
                        ''', (now_str, existing_att['id']))
                    else:
                        execute_db('''
                            INSERT INTO class_attendance (class_id, user_id, status, join_count, first_joined_at, last_joined_at)
                            VALUES (?, ?, 'Present', 1, ?, ?)
                        ''', (req_item['class_id'], req_item['user_id'], now_str, now_str))

                    execute_db('''
                        INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
                        VALUES ('student', ?, '✓ Entry Approved: Live Class Session', 'Dr. Boachie approved your entry into the Live Online Class room.', '/meetings')
                    ''', (req_item['user_id'],))

                    if req_item['email']:
                        send_external_email(
                            req_item['email'],
                            req_item['full_name'],
                            "✓ Live Class Entry Approved!",
                            f"Dear {req_item['full_name']},\n\nDr. Christopher Boachie has approved your entry request into the Live Online Class.\n\nYou may now enter the live video room at http://127.0.0.1:5000/meetings.\n\nBest regards,\nBconnect Academic Portal"
                        )

                    flash('✓ Student entry approved, external email sent, and attendance timestamp recorded!', 'success')
                else:
                    execute_db("UPDATE class_join_requests SET status = 'Denied' WHERE id = ?", (request_id,))
                    execute_db('''
                        INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
                        VALUES ('student', ?, 'Entry Request Declined', 'Dr. Boachie declined your request to join the Live Class.', '/meetings')
                    ''', (req_item['user_id'],))
                    flash('Student entry request declined.', 'warning')

            return redirect(url_for('meetings'))

        # BATCH ACCEPT ALL WAITING ROOM CLASS JOIN REQUESTS
        elif action == 'approve_all_class_joins':
            class_id = request.form.get('class_id')
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            pending_requests = query_db('SELECT class_join_requests.*, users.full_name, users.email FROM class_join_requests JOIN users ON class_join_requests.user_id = users.id WHERE class_id = ? AND status = "Pending"', (class_id,))
            
            if pending_requests:
                execute_db('UPDATE class_join_requests SET status = "Approved" WHERE class_id = ? AND status = "Pending"', (class_id,))
                
                for req_item in pending_requests:
                    existing_att = query_db('SELECT * FROM class_attendance WHERE class_id = ? AND user_id = ?', (class_id, req_item['user_id']), one=True)
                    if existing_att:
                        execute_db('''
                            UPDATE class_attendance
                            SET status = 'Present', join_count = join_count + 1, last_joined_at = ?
                            WHERE id = ?
                        ''', (now_str, existing_att['id']))
                    else:
                        execute_db('''
                            INSERT INTO class_attendance (class_id, user_id, status, join_count, first_joined_at, last_joined_at)
                            VALUES (?, ?, 'Present', 1, ?, ?)
                        ''', (class_id, req_item['user_id'], now_str, now_str))

                    execute_db('''
                        INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
                        VALUES ('student', ?, '✓ Entry Approved: Live Class Session', 'Dr. Boachie approved your entry into the Live Online Class room.', '/meetings')
                    ''', (req_item['user_id'],))

                    if req_item['email']:
                        send_external_email(
                            req_item['email'],
                            req_item['full_name'],
                            "✓ Live Class Entry Approved!",
                            f"Dear {req_item['full_name']},\n\nDr. Christopher Boachie has approved your entry request into the Live Online Class.\n\nYou may now enter the live video room at http://127.0.0.1:5000/meetings.\n\nBest regards,\nBconnect Academic Portal"
                        )

                flash(f'✓ ACCEPT ALL SUCCESSFUL: Approved all {len(pending_requests)} waiting students & sent external email alerts!', 'success')
            else:
                flash('No students waiting in entry queue.', 'info')

            return redirect(url_for('meetings'))

    active_availability = query_db('SELECT * FROM weekly_availability WHERE is_active = 1 ORDER BY available_date ASC')
    all_meetings = query_db('''
        SELECT meetings.*, users.full_name, users.index_number, users.phone_number, users.student_level, users.enrolled_course
        FROM meetings
        JOIN users ON meetings.user_id = users.id
        ORDER BY meetings.created_at DESC
    ''')

    online_classes = query_db('SELECT * FROM online_classes ORDER BY created_at DESC')
    classes_data = []

    for oc in online_classes:
        c_dict = dict(oc)
        
        slides_list = query_db('''
            SELECT id, title, filename, created_at, 'Assignment Material' as source_type
            FROM course_assignments
            WHERE course_code LIKE ?
        ''', (f'%{oc["course_code"]}%',))
        
        slides_files = [dict(s) for s in slides_list]
        
        if oc['slides_filename']:
            slides_files.insert(0, {
                'id': 0,
                'title': f"Class Primary Slides Deck ({oc['topic']})",
                'filename': oc['slides_filename'],
                'created_at': oc['created_at'],
                'source_type': 'Live Class Slides'
            })

        pending_requests = query_db('''
            SELECT class_join_requests.*, users.full_name, users.index_number, users.student_level, users.enrolled_course
            FROM class_join_requests
            JOIN users ON class_join_requests.user_id = users.id
            WHERE class_join_requests.class_id = ? AND class_join_requests.status = 'Pending'
            ORDER BY class_join_requests.requested_at ASC
        ''', (oc['id'],))

        attendance_list = query_db('''
            SELECT class_attendance.*, users.full_name, users.index_number, users.student_level, users.enrolled_course
            FROM class_attendance
            JOIN users ON class_attendance.user_id = users.id
            WHERE class_attendance.class_id = ?
            ORDER BY class_attendance.status ASC, users.full_name ASC
        ''', (oc['id'],))

        c_dict['course_slides'] = slides_files
        c_dict['pending_requests'] = pending_requests
        c_dict['attendance_list'] = attendance_list
        classes_data.append(c_dict)

    return render_template('lecturer/meetings.html',
                           active_availability=active_availability,
                           meetings=all_meetings,
                           online_classes=classes_data)

@app.route('/thesis', methods=['GET', 'POST'])
def thesis():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    if request.method == 'POST':
        thesis_id = request.form.get('thesis_id')
        new_status = request.form.get('status')
        supervisor_feedback = request.form.get('supervisor_feedback', '').strip()

        thesis_item = query_db('SELECT theses.*, users.full_name, users.email FROM theses JOIN users ON theses.user_id = users.id WHERE theses.id = ?', (thesis_id,), one=True)
        execute_db('''
            UPDATE theses
            SET status = ?, supervisor_feedback = ?
            WHERE id = ?
        ''', (new_status, supervisor_feedback, thesis_id))

        if supervisor_feedback:
            execute_db('''
                INSERT INTO thread_messages (item_type, item_id, sender_type, sender_name, message)
                VALUES ('thesis', ?, 'lecturer', 'Dr. Christopher Boachie', ?)
            ''', (thesis_id, supervisor_feedback))

        if thesis_item:
            execute_db('''
                INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
                VALUES ('student', ?, 'Thesis Supervisor Feedback Posted', ?, '/thesis')
            ''', (thesis_item['user_id'], f"Thesis status updated to {new_status}."))

            if thesis_item['email']:
                send_external_email(
                    thesis_item['email'],
                    thesis_item['full_name'],
                    f"🎓 Thesis Supervisor Feedback: {new_status}",
                    f"Dear {thesis_item['full_name']},\n\nDr. Christopher Boachie has posted supervisor review feedback on your thesis draft:\n\nTITLE: {thesis_item['title']}\nSTATUS: {new_status}\nSUPERVISOR FEEDBACK: {supervisor_feedback}\n\nLog in at http://127.0.0.1:5000/thesis to reply in the review thread.\n\nBest regards,\nBconnect Academic Portal"
                )

        flash('Supervisor thesis review saved & external email alert sent!', 'success')
        return redirect(url_for('thesis'))

    all_theses = query_db('''
        SELECT theses.*, users.full_name, users.index_number, users.phone_number, users.student_level, users.enrolled_course
        FROM theses
        JOIN users ON theses.user_id = users.id
        ORDER BY theses.submitted_at DESC
    ''')

    theses_with_threads = []
    for t in all_theses:
        t_dict = dict(t)
        t_dict['threads'] = get_thread_messages('thesis', t['id'])
        theses_with_threads.append(t_dict)

    return render_template('lecturer/thesis.html', theses=theses_with_threads)

@app.route('/assignments', methods=['GET', 'POST'])
def assignments():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'upload_assignment':
            course_code = request.form.get('course_code', '').strip()
            target_level = request.form.get('target_level', '').strip()
            title = request.form.get('title', '').strip()
            instructions = request.form.get('instructions', '').strip()
            deadline = request.form.get('deadline', '').strip()
            file_input = request.files.get('assignment_file')

            if file_input and file_input.filename:
                filename = secure_filename(file_input.filename)
                file_input.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            else:
                filename = f"{course_code}_assignment.pdf"

            if not course_code or not target_level or not title or not deadline:
                flash('Please specify course code, target level, title, and deadline date/time.', 'danger')
            else:
                execute_db('''
                    INSERT INTO course_assignments (course_code, target_level, title, instructions, filename, deadline)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (course_code, target_level, title, instructions, filename, deadline))

                execute_db('''
                    INSERT INTO notifications (recipient_type, title, message, target_url)
                    VALUES ('student', 'New Course Assignment Uploaded by Dr. Boachie', ?, '/assignments')
                ''', (f"New assignment for {course_code}: {title} (Deadline: {deadline}).",))

                approved_students = query_db('SELECT full_name, email FROM users WHERE approval_status = "Approved"')
                broadcast_external_email(
                    approved_students,
                    f"📚 New Course Assignment Uploaded: {course_code} - {title}",
                    lambda s: f"Dear {s['full_name']},\n\nDr. Christopher Boachie has posted a new course assignment:\n\n• Course: {course_code}\n• Title: {title}\n• Target Level: {target_level}\n• Deadline: {deadline}\n• Instructions: {instructions or 'N/A'}\n\nLog in to download assignment documents and upload your answer file at:\nhttp://127.0.0.1:5000/assignments\n\nBest regards,\nDr. Christopher Boachie Academic Portal"
                )

                flash('New Course Assignment uploaded & external email alerts sent to students!', 'success')
                return redirect(url_for('assignments'))

        elif action == 'grade_submission':
            sub_id = request.form.get('submission_id')
            grade = request.form.get('grade', '').strip()
            lecturer_feedback = request.form.get('lecturer_feedback', '').strip()
            status = request.form.get('status', 'Graded & Recorded')
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            submission = query_db('SELECT student_submissions.*, users.full_name, users.email, course_assignments.title as assignment_title, course_assignments.course_code FROM student_submissions JOIN users ON student_submissions.user_id = users.id JOIN course_assignments ON student_submissions.assignment_id = course_assignments.id WHERE student_submissions.id = ?', (sub_id,), one=True)
            execute_db('''
                UPDATE student_submissions
                SET grade = ?, lecturer_feedback = ?, status = ?, graded_at = ?
                WHERE id = ?
            ''', (grade, lecturer_feedback, status, now_str, sub_id))

            if lecturer_feedback:
                execute_db('''
                    INSERT INTO thread_messages (item_type, item_id, sender_type, sender_name, message)
                    VALUES ('assignment', ?, 'lecturer', 'Dr. Christopher Boachie', ?)
                ''', (sub_id, lecturer_feedback))

            if submission:
                execute_db('''
                    INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
                    VALUES ('student', ?, 'Assignment Graded & Recorded', ?, '/assignments')
                ''', (submission['user_id'], f"Grade: {grade}. Feedback: {lecturer_feedback}"))

                if submission['email']:
                    send_external_email(
                        submission['email'],
                        submission['full_name'],
                        f"📚 Assignment Graded: {submission['course_code']} - {submission['assignment_title']}",
                        f"Dear {submission['full_name']},\n\nDr. Christopher Boachie has evaluated and graded your assignment submission:\n\nCOURSE: {submission['course_code']}\nASSIGNMENT: {submission['assignment_title']}\nGRADE: {grade}\nFEEDBACK: {lecturer_feedback}\n\nLog in at http://127.0.0.1:5000/assignments to view recorded marks.\n\nBest regards,\nBconnect Academic Portal"
                    )

            flash('Student assignment graded, archived & external email sent!', 'success')
            return redirect(url_for('assignments'))

    course_assignments = query_db('SELECT * FROM course_assignments ORDER BY created_at DESC')

    student_submissions = query_db('''
        SELECT student_submissions.*, users.full_name, users.index_number, users.student_level, users.enrolled_course, course_assignments.title as assignment_title, course_assignments.course_code
        FROM student_submissions
        JOIN users ON student_submissions.user_id = users.id
        JOIN course_assignments ON student_submissions.assignment_id = course_assignments.id
        ORDER BY student_submissions.submitted_at DESC
    ''')

    submissions_with_threads = []
    for s in student_submissions:
        s_dict = dict(s)
        s_dict['threads'] = get_thread_messages('assignment', s['id'])
        submissions_with_threads.append(s_dict)

    return render_template('lecturer/assignments.html',
                           course_assignments=course_assignments,
                           student_submissions=submissions_with_threads)

@app.route('/complaints', methods=['GET', 'POST'])
def complaints():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    if request.method == 'POST':
        complaint_id = request.form.get('complaint_id')
        new_status = request.form.get('status')
        lecturer_response = request.form.get('lecturer_response', '').strip()

        complaint = query_db('SELECT complaints.*, users.full_name, users.email FROM complaints JOIN users ON complaints.user_id = users.id WHERE complaints.id = ?', (complaint_id,), one=True)
        execute_db('''
            UPDATE complaints
            SET status = ?, lecturer_response = ?
            WHERE id = ?
        ''', (new_status, lecturer_response, complaint_id))

        if lecturer_response:
            execute_db('''
                INSERT INTO thread_messages (item_type, item_id, sender_type, sender_name, message)
                VALUES ('complaint', ?, 'lecturer', 'Dr. Christopher Boachie', ?)
            ''', (complaint_id, lecturer_response))

        if complaint and complaint['user_id']:
            execute_db('''
                INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
                VALUES ('student', ?, 'Complaint Status Updated', ?, '/complaints')
            ''', (complaint['user_id'], f"Complaint status: {new_status}."))

            if complaint['email']:
                send_external_email(
                    complaint['email'],
                    complaint['full_name'],
                    f"📝 Complaint Resolution Update: {new_status}",
                    f"Dear {complaint['full_name']},\n\nDr. Christopher Boachie has updated your formal complaint resolution status:\n\nSTATUS: {new_status}\nLECTURER RESPONSE: {lecturer_response}\n\nLog in at http://127.0.0.1:5000/complaints for details.\n\nBest regards,\nBconnect Academic Portal"
                )

        flash('Complaint resolution feedback updated & external email alert sent.', 'info')
        return redirect(url_for('complaints'))

    all_complaints = query_db('''
        SELECT complaints.*, users.full_name, users.index_number, users.phone_number, users.student_level, users.enrolled_course
        FROM complaints
        JOIN users ON complaints.user_id = users.id
        ORDER BY complaints.created_at DESC
    ''')

    complaints_with_threads = []
    for c in all_complaints:
        c_dict = dict(c)
        c_dict['threads'] = get_thread_messages('complaint', c['id'])
        complaints_with_threads.append(c_dict)

    return render_template('lecturer/complaints.html', complaints=complaints_with_threads)

@app.route('/academic-requests', methods=['GET', 'POST'])
def academic_requests():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    if request.method == 'POST':
        req_id = request.form.get('request_id')
        new_status = request.form.get('status')
        lecturer_response = request.form.get('lecturer_response', '').strip()

        req_item = query_db('SELECT academic_requests.*, users.full_name, users.email FROM academic_requests JOIN users ON academic_requests.user_id = users.id WHERE academic_requests.id = ?', (req_id,), one=True)
        execute_db('''
            UPDATE academic_requests
            SET status = ?, lecturer_response = ?
            WHERE id = ?
        ''', (new_status, lecturer_response, req_id))

        if lecturer_response:
            execute_db('''
                INSERT INTO thread_messages (item_type, item_id, sender_type, sender_name, message)
                VALUES ('academic_request', ?, 'lecturer', 'Dr. Christopher Boachie', ?)
            ''', (req_id, lecturer_response))

        if req_item:
            execute_db('''
                INSERT INTO notifications (recipient_type, user_id, title, message, target_url)
                VALUES ('student', ?, 'Academic Request Status Updated', ?, '/academic-requests')
            ''', (req_item['user_id'], f"Request status: {new_status}."))

            if req_item['email']:
                send_external_email(
                    req_item['email'],
                    req_item['full_name'],
                    f"📄 Academic Request Status Update: {new_status}",
                    f"Dear {req_item['full_name']},\n\nDr. Christopher Boachie has updated your academic request status:\n\nREQUEST TYPE: {req_item['request_type']}\nSTATUS: {new_status}\nRESPONSE: {lecturer_response}\n\nLog in at http://127.0.0.1:5000/academic-requests for details.\n\nBest regards,\nBconnect Academic Portal"
                )

        flash('Academic request feedback & status saved.', 'success')
        return redirect(url_for('academic_requests'))

    all_requests = query_db('''
        SELECT academic_requests.*, users.full_name, users.index_number, users.phone_number, users.student_level, users.enrolled_course
        FROM academic_requests
        JOIN users ON academic_requests.user_id = users.id
        ORDER BY academic_requests.created_at DESC
    ''')

    requests_with_threads = []
    for r in all_requests:
        r_dict = dict(r)
        r_dict['threads'] = get_thread_messages('academic_request', r['id'])
        requests_with_threads.append(r_dict)

    return render_template('lecturer/academic_requests.html', requests=requests_with_threads)

@app.route('/reply-thread', methods=['POST'])
def reply_thread():
    if not is_lecturer_logged_in():
        return redirect(url_for('login'))

    item_type = request.form.get('item_type')
    item_id = request.form.get('item_id')
    message = request.form.get('message', '').strip()
    redirect_url = request.form.get('redirect_url', url_for('dashboard'))

    if item_type and item_id and message:
        execute_db('''
            INSERT INTO thread_messages (item_type, item_id, sender_type, sender_name, message)
            VALUES (?, ?, 'lecturer', 'Dr. Christopher Boachie', ?)
        ''', (item_type, item_id, message))
        flash('Thread reply sent to student!', 'success')

    return redirect(redirect_url)

if __name__ == '__main__':
    app.run(debug=True, port=5001)
