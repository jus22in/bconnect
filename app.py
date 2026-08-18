import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from email_service import send_external_email

app = Flask(__name__)
app.config['SECRET_KEY'] = 'boachie-edu-student-secret-2026'

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

def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        user = query_db('SELECT * FROM users WHERE id = ?', (user_id,), one=True)
        if user and user['approval_status'] == 'Approved':
            return user
    return None

def get_thread_messages(item_type, item_id):
    return query_db('SELECT * FROM thread_messages WHERE item_type = ? AND item_id = ? ORDER BY created_at ASC', (item_type, item_id))

def get_student_notifications(user_id):
    return query_db('''
        SELECT * FROM notifications
        WHERE recipient_type = 'student' AND (user_id = ? OR user_id IS NULL)
        ORDER BY created_at DESC LIMIT 10
    ''', (user_id,))

@app.context_processor
def inject_notifications():
    user = get_current_user()
    if user:
        notifs = get_student_notifications(user['id'])
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
@app.route('/')
def index():
    user = get_current_user()
    logged_in = True if user else False
    return render_template('home.html', user=user, logged_in=logged_in)

@app.route('/mark-notification/<int:notif_id>')
def mark_notification(notif_id):
    execute_db('UPDATE notifications SET is_read = 1 WHERE id = ?', (notif_id,))
    target = request.args.get('target', url_for('dashboard'))
    return redirect(target)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        index_number = request.form.get('index_number', '').strip()
        email = request.form.get('email', '').strip()
        phone_number = request.form.get('phone_number', '').strip()
        student_level = request.form.get('student_level', '').strip()
        level_other = request.form.get('level_other', '').strip()
        enrolled_course = request.form.get('enrolled_course', '').strip()
        password = request.form.get('password', '')

        if not full_name or not index_number or not email or not phone_number or not student_level or not enrolled_course or not password:
            flash('Please complete all required fields including your Email Address.', 'danger')
            return render_template('register.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('register.html')

        existing_user = query_db('SELECT * FROM users WHERE index_number = ?', (index_number,), one=True)
        if existing_user:
            flash('An account with this Index Number / ID already exists. Please login.', 'warning')
            return redirect(url_for('login'))

        hashed_password = generate_password_hash(password)

        user_id = execute_db('''
            INSERT INTO users (full_name, index_number, email, phone_number, student_level, level_other, enrolled_course, password_hash, approval_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending Approval')
        ''', (full_name, index_number, email, phone_number, student_level, level_other if student_level == 'Other' else None, enrolled_course, hashed_password))

        # In-System Lecturer Notification
        execute_db('''
            INSERT INTO notifications (recipient_type, title, message, target_url)
            VALUES ('lecturer', 'New Student Registration Awaiting Approval', ?, '/students')
        ''', (f"{full_name} ({index_number} - {enrolled_course}) registered and requires approval.",))

        # DISPATCH EXTERNAL EMAIL NOTIFICATION TO STUDENT
        email_subject = "📥 Bconnect Account Registration Confirmation - Awaiting Approval"
        email_body = f"""Dear {full_name},

Thank you for registering your student account on Bconnect (Dr. Christopher Boachie Portal).

REGISTERED PROFILE DETAILS:
• Full Name: {full_name}
• Index Number: {index_number}
• Enrolled Course: {enrolled_course}
• Academic Level: {student_level}
• Email: {email}

STATUS: Pending Lecturer Approval ⏳
Your registration details have been submitted to Dr. Christopher Boachie for verification and approval. 

You will receive another external email notification as soon as Dr. Boachie approves your account, after which you will be able to log in.

Best regards,
Bconnect Academic System &bull; Dr. Christopher Boachie Portal
"""
        send_external_email(email, full_name, email_subject, email_body)

        flash(f'Registration Submitted! Welcome {full_name}. An external confirmation email alert has been sent to {email}. Your account is currently awaiting Dr. Christopher Boachie\'s approval.', 'info')
        return render_template('pending_approval.html', full_name=full_name, index_number=index_number)

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '')

        user = query_db('SELECT * FROM users WHERE index_number = ? OR phone_number = ? OR email = ?', (identifier, identifier, identifier), one=True)

        if user and check_password_hash(user['password_hash'], password):
            status = user['approval_status']
            if status == 'Pending Approval':
                flash('⏳ Account Pending Approval! Your registration request is currently under review by Dr. Christopher Boachie. Please check back once Dr. Boachie approves your profile.', 'warning')
                return render_template('pending_approval.html', full_name=user['full_name'], index_number=user['index_number'])
            elif status == 'Rejected':
                flash('🚫 Registration Declined. Your student registration request was declined by Dr. Christopher Boachie.', 'danger')
                return render_template('login.html')
            else:
                session['user_id'] = user['id']
                flash(f'Welcome back, {user["full_name"]}!', 'success')
                return redirect(url_for('dashboard'))
        else:
            flash('Invalid Index Number/Email/Phone or Password. Please try again.', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    user = get_current_user()
    if not user:
        flash('Please login to access the dashboard.', 'warning')
        return redirect(url_for('login'))

    announcements = query_db('''
        SELECT * FROM announcements
        WHERE target_type = 'all'
           OR target_value = ?
           OR target_value = ?
           OR target_value = ?
        ORDER BY posted_at DESC
    ''', (user['student_level'], user['enrolled_course'], user['index_number']))

    meetings_count = query_db('SELECT COUNT(*) as count FROM meetings WHERE user_id = ?', (user['id'],), one=True)['count']
    thesis_count = query_db('SELECT COUNT(*) as count FROM theses WHERE user_id = ?', (user['id'],), one=True)['count']
    assignments_count = query_db('SELECT COUNT(*) as count FROM student_submissions WHERE user_id = ?', (user['id'],), one=True)['count']
    complaints_count = query_db('SELECT COUNT(*) as count FROM complaints WHERE user_id = ?', (user['id'],), one=True)['count']

    recent_meetings = query_db('SELECT * FROM meetings WHERE user_id = ? ORDER BY created_at DESC LIMIT 3', (user['id'],))
    recent_complaints = query_db('SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC LIMIT 3', (user['id'],))

    return render_template('dashboard.html',
                           user=user,
                           announcements=announcements,
                           meetings_count=meetings_count,
                           thesis_count=thesis_count,
                           assignments_count=assignments_count,
                           complaints_count=complaints_count,
                           recent_meetings=recent_meetings,
                           recent_complaints=recent_complaints)

@app.route('/meetings', methods=['GET', 'POST'])
def meetings():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    active_slots = query_db('SELECT * FROM weekly_availability WHERE is_active = 1 ORDER BY available_date ASC')
    booking_allowed = True if active_slots else False

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'book_meeting':
            if not booking_allowed:
                flash('🔒 Booking Unavailable! Dr. Christopher Boachie has not assigned available meeting slots for this week yet.', 'danger')
                return redirect(url_for('meetings'))

            availability_id = request.form.get('availability_id')
            topic = request.form.get('topic', '').strip()
            notes = request.form.get('notes', '').strip()

            slot = query_db('SELECT * FROM weekly_availability WHERE id = ?', (availability_id,), one=True)
            if not slot:
                flash('Please select an active available consultation slot.', 'danger')
            else:
                execute_db('''
                    INSERT INTO meetings (user_id, availability_id, topic, preferred_date, preferred_time, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user['id'], slot['id'], topic, slot['available_date'], slot['time_slot'], notes))

                execute_db('''
                    INSERT INTO notifications (recipient_type, title, message, target_url)
                    VALUES ('lecturer', 'New Meeting Booked from Assigned Slots', ?, '/meetings')
                ''', (f"{user['full_name']} booked {slot['available_date']} ({slot['time_slot']}) for {topic}.",))

                flash('Meeting reservation request successfully submitted to Dr. Christopher Boachie.', 'success')
                return redirect(url_for('meetings'))

    user_meetings = query_db('SELECT * FROM meetings WHERE user_id = ? ORDER BY created_at DESC', (user['id'],))

    online_classes = query_db('SELECT * FROM online_classes ORDER BY created_at DESC')
    
    classes_with_status = []
    for oc in online_classes:
        c_dict = dict(oc)
        join_req = query_db('SELECT * FROM class_join_requests WHERE class_id = ? AND user_id = ? ORDER BY requested_at DESC LIMIT 1', (oc['id'], user['id']), one=True)
        att_rec = query_db('SELECT * FROM class_attendance WHERE class_id = ? AND user_id = ?', (oc['id'], user['id']), one=True)
        
        c_dict['join_request'] = join_req
        c_dict['attendance'] = att_rec
        classes_with_status.append(c_dict)

    return render_template('meetings.html',
                           user=user,
                           active_slots=active_slots,
                           booking_allowed=booking_allowed,
                           meetings=user_meetings,
                           online_classes=classes_with_status)

@app.route('/request-class-join', methods=['POST'])
def request_class_join():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    class_id = request.form.get('class_id')
    oc = query_db('SELECT * FROM online_classes WHERE id = ?', (class_id,), one=True)
    if not oc or oc['status'] != 'Live Now':
        flash('The selected online class is not live right now.', 'danger')
        return redirect(url_for('meetings'))

    att_rec = query_db('SELECT * FROM class_attendance WHERE class_id = ? AND user_id = ?', (class_id, user['id']), one=True)
    
    if att_rec and att_rec['last_left_at'] is not None:
        request_type = 'Reentry'
        msg_text = f"⚠️ REENTRY REQUEST: {user['full_name']} (ID: {user['index_number']}) previously left class and is requesting reentry."
    else:
        request_type = 'Initial Entry'
        msg_text = f"✋ LIVE CLASS JOIN REQUEST: {user['full_name']} (ID: {user['index_number']}) requests entry into live class: {oc['topic']}."

    execute_db('''
        INSERT INTO class_join_requests (class_id, user_id, request_type, status)
        VALUES (?, ?, ?, 'Pending')
    ''', (class_id, user['id'], request_type))

    execute_db('''
        INSERT INTO notifications (recipient_type, title, message, target_url)
        VALUES ('lecturer', '✋ Live Class Join Request', ?, '/meetings')
    ''', (msg_text,))

    flash('Join request sent! You are in the Virtual Waiting Room. Waiting for Dr. Christopher Boachie to approve your entry.', 'info')
    return redirect(url_for('meetings'))

@app.route('/leave-class', methods=['POST'])
def leave_class():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    class_id = request.form.get('class_id')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    execute_db('''
        UPDATE class_attendance
        SET last_left_at = ?
        WHERE class_id = ? AND user_id = ?
    ''', (now_str, class_id, user['id']))

    execute_db('''
        UPDATE class_join_requests
        SET status = 'Expired'
        WHERE class_id = ? AND user_id = ?
    ''', (class_id, user['id']))

    flash('You have left the Live Online Class session. Reentry will require Dr. Boachie\'s approval.', 'warning')
    return redirect(url_for('meetings'))

@app.route('/thesis', methods=['GET', 'POST'])
def thesis():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        stage = request.form.get('stage', '').strip()
        abstract = request.form.get('abstract', '').strip()
        file_input = request.files.get('thesis_file')

        if file_input and file_input.filename:
            filename = secure_filename(file_input.filename)
            file_input.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        else:
            filename = f"{user['index_number']}_thesis.pdf"

        if not title or not stage or not abstract:
            flash('Please complete the title, stage, and abstract fields.', 'danger')
        else:
            execute_db('''
                INSERT INTO theses (user_id, title, stage, abstract, filename)
                VALUES (?, ?, ?, ?, ?)
            ''', (user['id'], title, stage, abstract, filename))

            execute_db('''
                INSERT INTO notifications (recipient_type, title, message, target_url)
                VALUES ('lecturer', 'New Thesis Draft Uploaded', ?, '/thesis')
            ''', (f"{user['full_name']} uploaded thesis draft: {title} ({stage}).",))

            flash('Thesis draft successfully uploaded and registered!', 'success')
            return redirect(url_for('thesis'))

    user_theses = query_db('SELECT * FROM theses WHERE user_id = ? ORDER BY submitted_at DESC', (user['id'],))
    
    theses_with_threads = []
    for t in user_theses:
        t_dict = dict(t)
        t_dict['threads'] = get_thread_messages('thesis', t['id'])
        theses_with_threads.append(t_dict)

    return render_template('thesis.html', user=user, theses=theses_with_threads)

@app.route('/assignments', methods=['GET', 'POST'])
def assignments():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        assignment_id = request.form.get('assignment_id')
        file_input = request.files.get('answer_file')

        if file_input and file_input.filename:
            filename = secure_filename(file_input.filename)
            file_input.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        else:
            filename = f"{user['index_number']}_answer.pdf"

        if not assignment_id:
            flash('Please select an assignment to submit.', 'danger')
        else:
            execute_db('''
                INSERT INTO student_submissions (assignment_id, user_id, filename)
                VALUES (?, ?, ?)
            ''', (assignment_id, user['id'], filename))

            execute_db('''
                INSERT INTO notifications (recipient_type, title, message, target_url)
                VALUES ('lecturer', 'New Assignment Answer Uploaded', ?, '/assignments')
            ''', (f"{user['full_name']} uploaded answer file: {filename}.",))

            flash('Assignment answer successfully uploaded!', 'success')
            return redirect(url_for('assignments'))

    available_assignments = query_db('''
        SELECT * FROM course_assignments
        WHERE course_code LIKE ? OR target_level = 'All Levels' OR target_level = ?
        ORDER BY created_at DESC
    ''', (f'%{user["enrolled_course"]}%', user['student_level']))

    my_submissions = query_db('''
        SELECT student_submissions.*, course_assignments.title as assignment_title, course_assignments.course_code
        FROM student_submissions
        JOIN course_assignments ON student_submissions.assignment_id = course_assignments.id
        WHERE student_submissions.user_id = ?
        ORDER BY student_submissions.submitted_at DESC
    ''', (user['id'],))

    submissions_with_threads = []
    for s in my_submissions:
        s_dict = dict(s)
        s_dict['threads'] = get_thread_messages('assignment', s['id'])
        submissions_with_threads.append(s_dict)

    return render_template('assignments.html',
                           user=user,
                           available_assignments=available_assignments,
                           my_submissions=submissions_with_threads)

@app.route('/complaints', methods=['GET', 'POST'])
def complaints():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        category = request.form.get('category', '').strip()
        priority = request.form.get('priority', '').strip()
        details = request.form.get('details', '').strip()
        is_anonymous = 1 if request.form.get('is_anonymous') == 'on' else 0

        if not category or not priority or not details:
            flash('Please provide category, priority, and complaint details.', 'danger')
        else:
            execute_db('''
                INSERT INTO complaints (user_id, category, priority, details, is_anonymous)
                VALUES (?, ?, ?, ?, ?)
            ''', (user['id'], category, priority, details, is_anonymous))

            execute_db('''
                INSERT INTO notifications (recipient_type, title, message, target_url)
                VALUES ('lecturer', 'New Complaint Logged', ?, '/complaints')
            ''', (f"Complaint logged under category: {category} ({priority} Priority).",))

            flash('Formal complaint logged securely. Status updates will appear on your log.', 'success')
            return redirect(url_for('complaints'))

    user_complaints = query_db('SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC', (user['id'],))
    
    complaints_with_threads = []
    for c in user_complaints:
        c_dict = dict(c)
        c_dict['threads'] = get_thread_messages('complaint', c['id'])
        complaints_with_threads.append(c_dict)

    return render_template('complaints.html', user=user, complaints=complaints_with_threads)

@app.route('/academic-requests', methods=['GET', 'POST'])
def academic_requests():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        request_type = request.form.get('request_type', '').strip()
        purpose = request.form.get('purpose', '').strip()
        details = request.form.get('details', '').strip()

        if not request_type or not purpose:
            flash('Please select request type and state the purpose.', 'danger')
        else:
            execute_db('''
                INSERT INTO academic_requests (user_id, request_type, purpose, details)
                VALUES (?, ?, ?, ?)
            ''', (user['id'], request_type, purpose, details))

            execute_db('''
                INSERT INTO notifications (recipient_type, title, message, target_url)
                VALUES ('lecturer', 'New Academic Request', ?, '/academic-requests')
            ''', (f"{user['full_name']} requested {request_type} for {purpose}.",))

            flash('Academic request submitted successfully.', 'success')
            return redirect(url_for('academic_requests'))

    user_requests = query_db('SELECT * FROM academic_requests WHERE user_id = ? ORDER BY created_at DESC', (user['id'],))
    
    requests_with_threads = []
    for r in user_requests:
        r_dict = dict(r)
        r_dict['threads'] = get_thread_messages('academic_request', r['id'])
        requests_with_threads.append(r_dict)

    return render_template('academic_requests.html', user=user, requests=requests_with_threads)

@app.route('/reply-thread', methods=['POST'])
def reply_thread():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    item_type = request.form.get('item_type')
    item_id = request.form.get('item_id')
    message = request.form.get('message', '').strip()
    redirect_url = request.form.get('redirect_url', url_for('dashboard'))

    if item_type and item_id and message:
        execute_db('''
            INSERT INTO thread_messages (item_type, item_id, sender_type, sender_name, message)
            VALUES (?, ?, 'student', ?, ?)
        ''', (item_type, item_id, user['full_name'], message))

        execute_db('''
            INSERT INTO notifications (recipient_type, title, message, target_url)
            VALUES ('lecturer', 'New Thread Reply from Student', ?, ?)
        ''', (f"{user['full_name']} replied on {item_type}: {message[:50]}...", f'/{item_type}s' if not item_type.endswith('s') else f'/{item_type}'))

        flash('Your reply has been sent to Dr. Christopher Boachie!', 'success')

    return redirect(redirect_url)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
