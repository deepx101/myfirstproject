from flask import Flask, flash, render_template, request, redirect, url_for, session
import mysql.connector
from werkzeug.security import check_password_hash, generate_password_hash
import calendar
from datetime import datetime, date
from functools import wraps
import smtplib
# from email.mime.text import MimeText
# from email.mime.multipart import MimeMultipart
import os


app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")


# Gmail SMTP config - Use App Password (generate at https://myaccount.google.com/apppasswords)
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
# ---------------- DATABASE CONNECTION ----------------
conn = mysql.connector.connect(
    host="localhost",
    user="aman",
    password="aman123",
    database="meeting_scheduler_db",
)
cursor = conn.cursor(dictionary=True)
# ----------------Helper functions-------------


def get_session_user_info():
    """Safely get user info from session"""
    return {
        'user_id': session.get('user_id'),
        'user_name': session.get('user_name', 'User'),
        'email': session.get('email'),
        'role_id': session.get('role_id')
    }


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first!")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first!")
            return redirect(url_for('login'))
        role_id = get_role(session['user_id'])
        if role_id != 100:  # Admin role
            flash("Admin access required!")
            return redirect(url_for('faculty_dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_role(user_id):  # ✅ MUST have user_id parameter
    """Get user role from database"""
    cursor.execute("SELECT role_id FROM user WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    return result['role_id'] if result else None


def get_departments():
    cursor.execute("SELECT * FROM department ORDER BY department_name")
    return cursor.fetchall()


def get_roles():
    """Get all roles from database"""
    cursor.execute("""
        SELECT role_id, role_name 
        FROM role 
        WHERE role_id != 100  -- Exclude Admin role
        ORDER BY role_name
    """)
    return cursor.fetchall()
def send_meeting_email(recipients, action, meeting_info):
    """Send notification email to meeting members."""
    
    # CUSTOM SUBJECTS WITHOUT EMOJIS (works everywhere)
    if action == 'created':
        subject = f'New Meeting Created: {meeting_info["title"]}'
    elif action == 'updated':
        subject = f'Meeting Updated: {meeting_info["title"]}'
    else:  # deleted/cancelled
        subject = f'Meeting Cancelled: {meeting_info["title"]}'
    
    body = f"""
Meeting {action.upper()} Notification:

Title: {meeting_info["title"]}
Date: {meeting_info["date"]}
Time: {meeting_info["start_time"]} to {meeting_info["end_time"]}
Venue: {meeting_info.get("venue", "TBD")}
Department: {meeting_info.get("dept_name", "N/A")}
"""
    
    message = f"""From: {SENDER_EMAIL}
To: {', '.join(recipients)}
Subject: {subject}

{body}"""
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipients, message)
        server.quit()
        print(f"✅ Email sent to {len(recipients)} recipients ({action})")
    except Exception as e:
        print(f"❌ Email failed: {e}")

# ---------------- LOGIN ----------------


@app.route("/", methods=["GET", "POST"])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['username']  # Can be user_id OR email
        password = request.form['password']

        # ✅ LOGIN WITH USER_ID OR EMAIL
        cursor.execute("""
            SELECT * FROM user 
            WHERE user_id = %s OR email = %s
        """, (identifier, identifier))
        user = cursor.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            # ✅ SET ALL SESSION VARIABLES
            session['user_id'] = user['user_id']
            session['user_name'] = user['user_name']
            session['email'] = user['email']
            session['role_id'] = user['role_id']

            if user['role_id'] == 100:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('faculty_dashboard'))
        else:
            return render_template('login.html', error="Invalid credentials!")

    return render_template('login.html')

# ---------------- DASHBOARDS ----------------


@app.route("/admin/dashboard")
def admin_dashboard():
    if "user_id" not in session or session.get("role_id") != 100:
        return redirect(url_for("login"))

    # ✅ SAFE ACCESS - use .get() method
    user_name = session.get("user_name", "Admin")
    return render_template("admin/admin_dashboard.html", user=user_name)


@app.route("/faculty/dashboard")
def faculty_dashboard():
    # if "user_id" not in session or session.get("role_id") != 101:
    #     return redirect(url_for("login"))

    # ✅ SAFE ACCESS - use .get() method
    user_name = session.get("user_name", "Faculty")
    return render_template("faculty_dashboard.html", user=user_name)
# -------------------Admin Dashboard------------------


@app.route("/admin/add-department", methods=["GET", "POST"])
def add_department():
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    if request.method == "POST":
        department_name = request.form["department_name"]

        cursor.execute(
            "INSERT INTO department (department_name) VALUES (%s)",
            (department_name,)
        )
        conn.commit()

        return redirect(url_for("view_departments"))

    return render_template("admin/add_department.html")

# -------------view department---------------
# -------------view department with search----------------


@app.route("/admin/view-departments", methods=["GET"])
def view_departments():
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    # Get search keyword
    search = request.args.get("search", "").strip()

    if search:
        cursor.execute(
            "SELECT * FROM department WHERE department_name LIKE %s",
            ("%" + search + "%",)
        )
    else:
        cursor.execute("SELECT * FROM department")

    departments = cursor.fetchall()

    return render_template(
        "admin/view_departments.html",
        departments=departments,
        search_query=search  # Pass search term to template
    )


# ----------------delete department----------------
@app.route("/admin/delete-department/<int:dept_id>")
def delete_department(dept_id):
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    # Check users
    cursor.execute(
        "SELECT COUNT(*) AS total FROM user WHERE department_id=%s",
        (dept_id,)
    )
    users_count = cursor.fetchone()["total"]

    # Check meetings
    cursor.execute(
        "SELECT COUNT(*) AS total FROM meeting WHERE department_id=%s",
        (dept_id,)
    )
    meetings_count = cursor.fetchone()["total"]

    if users_count > 0 or meetings_count > 0:
        return "❌ Cannot delete department. Users or meetings exist."

    cursor.execute(
        "DELETE FROM department WHERE department_id=%s",
        (dept_id,)
    )
    conn.commit()

    return redirect(url_for("view_departments"))

# -------------------Search Department--------------


@app.route("/admin/search-departments")
def search_departments():
    if "user_id" not in session or session["role_id"] != 100:
        return {"error": "Unauthorized"}, 403

    keyword = request.args.get("q", "").strip()

    if keyword == "":
        cursor.execute("SELECT * FROM department")
    else:
        cursor.execute(
            "SELECT * FROM department WHERE department_name LIKE %s",
            ("%" + keyword + "%",)
        )

    departments = cursor.fetchall()
    return {"departments": departments}

# ------------view users----------------------
# ------------view users with search----------------------


@app.route("/admin/view-users")
def view_users():
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    # Get search keyword
    keyword = request.args.get("q", "").strip()

    query = """
   SELECT u.user_id, u.user_name, u.email, u.user_mobileNo,
       d.department_name, r.role_name, u.role_id
FROM user u
LEFT JOIN department d ON u.department_id = d.department_id
LEFT JOIN role r ON u.role_id = r.role_id
    """
    params = []

    if keyword:
        query += """
        WHERE u.user_name LIKE %s
           OR u.email LIKE %s
           OR d.department_name LIKE %s
           OR r.role_name LIKE %s
        """
        params = ["%" + keyword + "%"] * 4

    query += " ORDER BY u.user_id"

    cursor.execute(query, params)
    users = cursor.fetchall()

    # Filter out users with role_id 100
    users = [user for user in users if user['role_id'] != 100]

    return render_template("admin/view_users.html", users=users, search_query=keyword)
# -------------------edit user----------------------


@app.route("/admin/edit-user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    if request.method == "POST":
        user_name = request.form["user_name"]
        email = request.form["email"]
        department_id = request.form.get("department_id")
        role_id = request.form["role_id"]

        cursor.execute("""
            UPDATE user
            SET user_name=%s, email=%s,
                department_id=%s, role_id=%s
            WHERE user_id=%s
        """, (user_name, email, department_id, role_id, user_id))

        conn.commit()
        return redirect(url_for("view_users"))

    # GET data
    cursor.execute("SELECT * FROM user WHERE user_id=%s", (user_id,))
    user = cursor.fetchone()

    cursor.execute("SELECT * FROM department")
    departments = cursor.fetchall()

    cursor.execute("SELECT * FROM role")
    roles = cursor.fetchall()

    return render_template(
        "admin/edit_user.html",
        user=user,
        departments=departments,
        roles=roles
    )

# -----------delete user--------------------


@app.route("/admin/delete-user/<int:user_id>")
def delete_user(user_id):
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    cursor.execute("DELETE FROM user WHERE user_id=%s", (user_id,))
    conn.commit()

    return redirect(url_for("view_users"))

# -----------search meetings------------------------------


@app.route("/admin/search-meetings")
def search_meetings():
    if "user_id" not in session or session["role_id"] != 100:
        return {"error": "Unauthorized"}, 403

    keyword = request.args.get("q", "").strip()

    query = """
        SELECT 
            m.meeting_title,
            m.meeting_date,
            m.start_time,
            m.end_time,
            m.venue,
            d.department_name,
            u.user_name
        FROM meeting m
        JOIN department d ON m.department_id = d.department_id
        JOIN user u ON m.user_id = u.user_id
    """

    params = []

    if keyword:
        query += """
        WHERE m.meeting_title LIKE %s
           OR d.department_name LIKE %s
           OR u.user_name LIKE %s
        """
        params = ["%" + keyword + "%"] * 3

    cursor.execute(query, params)
    results = cursor.fetchall()

    meetings = []

    for m in results:
        meetings.append({
            "meeting_title": m["meeting_title"],
            "meeting_date": str(m["meeting_date"]),
            "start_time": str(m["start_time"]),
            "end_time": str(m["end_time"]),
            "venue": m["venue"],
            "department_name": m["department_name"],
            "user_name": m["user_name"]
        })

    return {"meetings": meetings}
#--------------View my created meetings and edit meetings---------
# ---------------- MY CREATED MEETINGS (Creator View + Edit) ----------------
@app.route("/faculty/my-created-meetings")
@login_required
def my_created_meetings():
    # if session.get("role_id") != 101:
    #     return redirect(url_for("login"))
    
    keyword = request.args.get("q", "").strip()
    
    query = """
    SELECT m.meeting_id, m.meeting_title, m.meeting_date, m.start_time, m.end_time,
           m.venue, d.department_name, COUNT(mp.participant_id) as participant_count
    FROM meeting m
    JOIN department d ON m.department_id = d.department_id
    LEFT JOIN meeting_participant mp ON m.meeting_id = mp.meeting_id
    WHERE m.user_id = %s
    """
    params = [session["user_id"]]
    
    if keyword:
        query += " AND m.meeting_title LIKE %s OR d.department_name LIKE %s"
        params.extend(["%" + keyword + "%"] * 2)
    
    query += " GROUP BY m.meeting_id ORDER BY m.meeting_date DESC"
    
    cursor.execute(query, params)
    meetings = cursor.fetchall()
    
    return render_template("my_created_meetings.html", meetings=meetings, search_query=keyword)


@app.route("/faculty/meeting-edit/<int:meeting_id>", methods=['GET', 'POST'])
@login_required
def edit_meeting(meeting_id):
    cursor.execute("SELECT * FROM meeting WHERE meeting_id = %s AND user_id = %s", 
                  (meeting_id, session["user_id"]))
    meeting = cursor.fetchone()
    if not meeting:
        flash("❌ You can only edit your own meetings!")
        return redirect(url_for("my_created_meetings"))
  
    cursor.execute("""
        SELECT u.user_id, u.user_name 
        FROM meeting_participant mp 
        JOIN user u ON mp.user_id = u.user_id 
        WHERE mp.meeting_id = %s
    """, (meeting_id,))
    participants = cursor.fetchall()
  
    cursor.execute("""
    SELECT u.user_id, u.user_name, u.email, u.user_mobileNo, d.department_name
    FROM user u
    LEFT JOIN department d ON u.department_id = d.department_id
    WHERE u.role_id != 100""")
    all_users = cursor.fetchall()
  
    cursor.execute("SELECT * FROM department ORDER BY department_name")
    departments = cursor.fetchall()
  
    def parse_time(time_str):
        try:
            return datetime.strptime(time_str, "%H:%M:%S").strftime("%H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(time_str, "%I:%M %p").strftime("%H:%M:%S")
            except ValueError:
                try:
                    return datetime.strptime(time_str, "%H:%M").strftime("%H:%M:%S")
                except ValueError:
                    raise ValueError(f"Time format not recognized: {time_str}")

    if request.method == 'POST':
        new_title = request.form['meeting_title']
        new_date_str = request.form['meeting_date']
        new_start_time_str = request.form['start_time']
        new_end_time_str = request.form['end_time']
        new_venue = request.form['venue']
        new_dept_id = request.form['department_id']
        
        try:
            new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
            new_start_time = parse_time(new_start_time_str)
            new_end_time = parse_time(new_end_time_str)
        except ValueError as e:
            flash(str(e))
            return render_template('edit_meeting.html', 
                                   meeting=meeting, participants=participants,
                                   all_users=all_users, departments=departments)

        new_participants = request.form.getlist('participants')
        if not new_participants:
            flash("Please select at least one participant.")
            return render_template('edit_meeting.html', 
                                   meeting=meeting, participants=participants,
                                   all_users=all_users, departments=departments)
        
        participant_ids = [int(pid) for pid in new_participants]
        if str(session["user_id"]) not in new_participants:
            participant_ids.append(session["user_id"])

        format_strings = ','.join(['%s'] * len(participant_ids))
        conflict_query = f"""
    SELECT u.user_id, u.user_name, d_meeting.department_name AS meeting_department_name,
           m.meeting_title, m.meeting_date, m.start_time, m.end_time
    FROM meeting m
    JOIN meeting_participant mp ON m.meeting_id = mp.meeting_id
    JOIN user u ON mp.user_id = u.user_id
    LEFT JOIN department d_user ON u.department_id = d_user.department_id
    LEFT JOIN department d_meeting ON m.department_id = d_meeting.department_id
    WHERE m.meeting_date = %s
    AND u.user_id IN ({format_strings})
    AND %s < m.end_time
    AND %s > m.start_time
    AND m.meeting_id != %s
"""
        conflict_params = [new_date, *participant_ids, new_start_time, new_end_time, meeting_id]
        cursor.execute(conflict_query, conflict_params)
        conflicting_members = cursor.fetchall()

        if conflicting_members:
            conflict_messages = []
            for member in conflicting_members:
                conflict_messages.append(
                f"Member: {member['user_name']} (ID: {member['user_id']}), "
                f"Meeting Dept: {member['meeting_department_name']}, "
                f"Scheduled on: {member['meeting_date']} "
                f"from {member['start_time']} to {member['end_time']}\n"
                )
            error_message = "Conflicts detected:\n" + "\n".join(conflict_messages)
            flash(error_message)
            return render_template('edit_meeting.html', 
                                   meeting=meeting, participants=participants,
                                   all_users=all_users, departments=departments)

        # *** SAVE OLD DETAILS BEFORE UPDATE FOR EMAIL ***
        old_meeting_info = {
            'title': meeting['meeting_title'],
            'date': meeting['meeting_date'],
            'start_time': meeting['start_time'],
            'end_time': meeting['end_time'],
            'venue': meeting['venue']
        }
        
        # Update meeting
        cursor.execute("""
            UPDATE meeting SET meeting_title=%s, meeting_date=%s, 
            start_time=%s, end_time=%s, venue=%s, department_id=%s
            WHERE meeting_id=%s
        """, (new_title, new_date, new_start_time, new_end_time, new_venue, new_dept_id, meeting_id))
        
        # Update participants
        cursor.execute("DELETE FROM meeting_participant WHERE meeting_id=%s", (meeting_id,))
        for user_id in new_participants:
            cursor.execute("INSERT INTO meeting_participant (user_id, meeting_id) VALUES (%s, %s)", 
                          (user_id, meeting_id))
        conn.commit()

        # *** NEW: SEND EDIT EMAIL ***
        # Get updated meeting details
        cursor.execute("""
            SELECT m.meeting_title, m.meeting_date, m.start_time, m.end_time, m.venue, d.department_name 
            FROM meeting m 
            JOIN department d ON m.department_id = d.department_id 
            WHERE m.meeting_id = %s
        """, (meeting_id,))
        meeting_details = cursor.fetchone()

        # Get participant emails
        cursor.execute("""
            SELECT DISTINCT u.email 
            FROM meeting_participant mp 
            JOIN user u ON mp.user_id = u.user_id 
            WHERE mp.meeting_id = %s AND u.email IS NOT NULL
        """, (meeting_id,))
        emails = [row['email'] for row in cursor.fetchall()]

        if emails and meeting_details:
            meeting_info = {
                'title': meeting_details['meeting_title'],
                'date': meeting_details['meeting_date'],
                'start_time': meeting_details['start_time'],
                'end_time': meeting_details['end_time'],
                'venue': meeting_details['venue'],
                'dept_name': meeting_details['department_name']
            }
            send_meeting_email(emails, 'updated', meeting_info)

        flash('✅ Meeting updated successfully!')
        return redirect(url_for('my_created_meetings'))

    return render_template('edit_meeting.html', 
                           meeting=meeting, participants=participants,
                           all_users=all_users, departments=departments)
#----------delete meeting----------------
@app.route("/faculty/delete-meeting/<int:meeting_id>")
@login_required
def delete_meeting(meeting_id):
    # Check ownership
    cursor.execute("""
        SELECT meeting_title FROM meeting 
        WHERE meeting_id = %s AND user_id = %s
    """, (meeting_id, session["user_id"]))
    meeting = cursor.fetchone()
  
    if not meeting:
        flash("❌ You can only delete your own meetings!")
        return redirect(url_for("my_created_meetings"))

    # *** NEW: GET EMAILS AND SEND DELETE NOTIFICATION BEFORE DELETION ***
    cursor.execute("""
        SELECT DISTINCT u.email 
        FROM meeting_participant mp 
        JOIN user u ON mp.user_id = u.user_id 
        WHERE mp.meeting_id = %s AND u.email IS NOT NULL
    """, (meeting_id,))
    emails = [row['email'] for row in cursor.fetchall()]

    if emails:
        meeting_info = {
            'title': meeting['meeting_title'][:50] + '...' if len(meeting['meeting_title']) > 50 else meeting['meeting_title'],
            'date': 'N/A (cancelled)',
            'start_time': 'N/A',
            'end_time': 'N/A',
            'venue': 'N/A',
            'dept_name': 'N/A'
        }
        send_meeting_email(emails, 'deleted/cancelled', meeting_info)

    # Delete participants first (foreign key)
    cursor.execute("DELETE FROM meeting_participant WHERE meeting_id = %s", (meeting_id,))
  
    # Delete meeting
    cursor.execute("DELETE FROM meeting WHERE meeting_id = %s", (meeting_id,))
  
    conn.commit()
  
    flash(f'✅ "{meeting["meeting_title"][:30]}" deleted successfully!')
    return redirect(url_for("my_created_meetings"))
# ---------------edit department------------


@app.route("/admin/edit-department/<int:dept_id>", methods=["GET", "POST"])
def edit_department(dept_id):
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    if request.method == "POST":
        department_name = request.form["department_name"]

        cursor.execute(
            "UPDATE department SET department_name=%s WHERE department_id=%s",
            (department_name, dept_id)
        )
        conn.commit()

        return redirect(url_for("view_departments"))

    cursor.execute(
        "SELECT * FROM department WHERE department_id=%s",
        (dept_id,)
    )
    department = cursor.fetchone()

    return render_template(
        "admin/edit_department.html",
        department=department
    )

# --------------------add user----------------------


@app.route("/admin/add-user", methods=["GET", "POST"])
def add_user():
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    if request.method == "POST":
        user_name = request.form["name"]
        email = request.form["email"]
        user_mobileNo = request.form["mobile_no"]
        password = request.form["password"]
        role_id = request.form["role_id"]  # ✅ FIXED: was "role", now "role_id"
        department_id = request.form["department_id"]
        mobile_no = request.form["mobile_no"] # new for mobile NO

        # ✅ VALIDATE ROLE EXISTS
        cursor.execute(
            "SELECT role_id FROM role WHERE role_id = %s", (role_id,))
        if not cursor.fetchone():
            flash("Invalid role selected!")
            return redirect(url_for("add_user"))

        hashed_password = generate_password_hash(password)

        cursor.execute("""
            INSERT INTO user
            (user_name, email, user_mobileNo, password_hash, role_id, department_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_name, email, user_mobileNo, hashed_password, role_id, department_id))

        conn.commit()
        flash(f'✅ User "{user_name}" added successfully!')
        return redirect(url_for("view_users"))  # ✅ Better redirect

    # ✅ FETCH ROLES FROM DATABASE
    cursor.execute("SELECT role_id, role_name FROM role ORDER BY role_name")
    roles = cursor.fetchall()

    # Get departments (existing)
    cursor.execute("SELECT * FROM department ORDER BY department_name")
    departments = cursor.fetchall()

    return render_template(
        "admin/add_user.html",
        departments=departments,
        roles=roles  # ✅ Pass roles to template
    )


# -------------view all meetings----------------
# -------------view all meetings with search----------------


# @app.route("/admin/view-meetings")
# def view_all_meetings():
#     if "user_id" not in session or session["role_id"] != 100:
#         return redirect(url_for("login"))

#     # Get search keyword
#     keyword = request.args.get("q", "").strip()

#     query = """
#     SELECT m.meeting_title, m.meeting_date,
#            m.start_time, m.end_time, m.venue,
#            m.user_id,  -- ✅ ADDED: user_id
#            d.department_name, u.user_name
#     FROM meeting m
#     JOIN department d ON m.department_id = d.department_id
#     JOIN user u ON m.user_id = u.user_id
#     """
#     params = []

#     if keyword:
#         query += """
#         WHERE m.meeting_title LIKE %s
#            OR d.department_name LIKE %s
#            OR u.user_name LIKE %s
#         """
#         params = ["%" + keyword + "%"] * 3

#     query += " ORDER BY m.meeting_date DESC"

#     cursor.execute(query, params)
#     meetings = cursor.fetchall()

#     return render_template("admin/view_meetings.html", meetings=meetings, search_query=keyword)
@app.route("/admin/view-meetings")
def view_all_meetings():
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    # Get search keyword
    keyword = request.args.get("q", "").strip()

    query = """
   SELECT m.meeting_id,  -- ✅ ADDED for View Members link
       m.meeting_title, m.meeting_date,
       m.start_time, m.end_time, m.venue,
       m.user_id,
       d.department_name, u.user_name, u.user_mobileNo,
       COUNT(mp.participant_id) as participant_count  -- ✅ NEW: participant count
FROM meeting m
JOIN department d ON m.department_id = d.department_id
JOIN user u ON m.user_id = u.user_id
LEFT JOIN meeting_participant mp ON m.meeting_id = mp.meeting_id
    """
    params = []

    if keyword:
        query += """
        WHERE m.meeting_title LIKE %s
           OR d.department_name LIKE %s
           OR u.user_name LIKE %s
        GROUP BY m.meeting_id, m.meeting_title, m.meeting_date, 
                 m.start_time, m.end_time, m.venue, m.user_id,
                 d.department_name, u.user_name
        """
        params = ["%" + keyword + "%"] * 3
    else:
        query += """
        GROUP BY m.meeting_id, m.meeting_title, m.meeting_date, 
                 m.start_time, m.end_time, m.venue, m.user_id,
                 d.department_name, u.user_name
        """

    query += " ORDER BY m.meeting_date DESC"

    cursor.execute(query, params)
    meetings = cursor.fetchall()

    return render_template("admin/view_meetings.html", meetings=meetings, search_query=keyword)
# -------------------new routes for view meeting members feature---------


@app.route("/admin/view-meeting-members/<int:meeting_id>")
@login_required
def view_meeting_members(meeting_id):
    # Get meeting details
    cursor.execute("""
        SELECT m.meeting_title, m.meeting_date, m.start_time, m.end_time,
               d.department_name, u.user_name as creator_name, u.user_id as creator_id
        FROM meeting m
        JOIN department d ON m.department_id = d.department_id
        JOIN user u ON m.user_id = u.user_id
        WHERE m.meeting_id = %s
    """, (meeting_id,))
    meeting = cursor.fetchone()

    if not meeting:
        flash("Meeting not found!", "error")
        return redirect(url_for("view_all_meetings"))

    # Updated query to include participant's department
    cursor.execute("""
        SELECT DISTINCT mp.participant_id,
                        mp.user_id,
                        u.user_name,
                        u.email,
                        u.user_mobileNo,
                        r.role_name,
                        d.department_name -- Added department name here
        FROM meeting_participant mp
        JOIN user u ON mp.user_id = u.user_id
        LEFT JOIN role r ON u.role_id = r.role_id
        LEFT JOIN department d ON u.department_id = d.department_id -- Join with department
        WHERE mp.meeting_id = %s
        ORDER BY u.user_name
    """, (meeting_id,))
    members = cursor.fetchall()

    return render_template("/view_meeting_members.html",
                           meeting=meeting,
                           members=members,
                           participant_count=len(members)
                           )
# ---------------View my Meeting members------------
@app.route("/view-my-meeting-members/<int:meeting_id>")
@login_required
def view_my_meeting_members(meeting_id):
    # if "user_id" not in session or session["role_id"] != 100:
    #     return redirect(url_for("login"))

    # Get meeting details
    cursor.execute("""
        SELECT m.meeting_title, m.meeting_date, m.start_time, m.end_time,
               d.department_name, u.user_name as creator_name, u.user_id as creator_id
        FROM meeting m
        JOIN department d ON m.department_id = d.department_id
        JOIN user u ON m.user_id = u.user_id
        WHERE m.meeting_id = %s
    """, (meeting_id,))
    meeting = cursor.fetchone()

    if not meeting:
        flash("Meeting not found!", "error")
        return redirect(url_for("view_all_meetings"))

    # Updated query to include participant's department
    cursor.execute("""
        SELECT DISTINCT mp.participant_id,
                        mp.user_id,
                        u.user_name,
                        u.email,
                        u.user_mobileNo,
                        r.role_name,
                        d.department_name -- Added department name here
        FROM meeting_participant mp
        JOIN user u ON mp.user_id = u.user_id
        LEFT JOIN role r ON u.role_id = r.role_id
        LEFT JOIN department d ON u.department_id = d.department_id -- Join with department
        WHERE mp.meeting_id = %s
        ORDER BY u.user_name
    """, (meeting_id,))
    members = cursor.fetchall()

    return render_template("/view_my_meeting_members.html",
                           meeting=meeting,
                           members=members,
                           participant_count=len(members)
                           )
# ---------------- LOGOUT ----------------


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -----------------My Schedule----------------
# -----------------My Schedule with Search----------------


@app.route("/faculty/my-schedule")
def my_schedule():
    # if "user_id" not in session or session["role_id"] != 100:
    #     return redirect(url_for("login"))

    # Get search keyword
    keyword = request.args.get("q", "").strip()

    query = """
   SELECT m.meeting_id,  -- ✅ ADDED for View Members link
       m.meeting_title, m.meeting_date,
       m.start_time, m.end_time, m.venue,
       m.user_id,
       d.department_name, u.user_name, u.user_mobileNo,
       COUNT(mp.participant_id) as participant_count  -- ✅ NEW: participant count
FROM meeting m
JOIN department d ON m.department_id = d.department_id
JOIN user u ON m.user_id = u.user_id
LEFT JOIN meeting_participant mp ON m.meeting_id = mp.meeting_id
    """
    params = []

    if keyword:
        query += """
        WHERE m.meeting_title LIKE %s
           OR d.department_name LIKE %s
           OR u.user_name LIKE %s
        GROUP BY m.meeting_id, m.meeting_title, m.meeting_date, 
                 m.start_time, m.end_time, m.venue, m.user_id,
                 d.department_name, u.user_name
        """
        params = ["%" + keyword + "%"] * 3
    else:
        query += """
        GROUP BY m.meeting_id, m.meeting_title, m.meeting_date, 
                 m.start_time, m.end_time, m.venue, m.user_id,
                 d.department_name, u.user_name
        """

    query += " ORDER BY m.meeting_date DESC"

    cursor.execute(query, params)
    meetings = cursor.fetchall()

    return render_template("/my_schedule.html", meetings=meetings, search_query=keyword)
# ----------------------department-calendar-----------------


@app.route('/department_calendar')
def department_calendar():
    if "user_id" not in session:
        return redirect('/login')

    user_id = session["user_id"]

    # Get user's department
    cursor.execute(
        "SELECT department_id FROM user WHERE user_id = %s",
        (user_id,)
    )
    dept = cursor.fetchone()

    if not dept or not dept["department_id"]:
        return "Department not assigned", 404

    department_id = dept["department_id"]

    # ✅ FIXED: Better SQL query with proper JOINs and date handling
    cursor.execute("""
        SELECT m.meeting_id, m.meeting_title as title, m.meeting_date as date, m.venue,
               CASE WHEN m.meeting_date < CURDATE() THEN 'past' ELSE 'upcoming' END as status,
               DATE_FORMAT(m.meeting_date, '%Y-%m-%d') as date_iso
        FROM meeting m
        WHERE m.department_id = %s
    """, (department_id,))

    meetings = cursor.fetchall()

    # ✅ FIXED: Simple, clean event formatting
    events = []
    for m in meetings:
        events.append({
            "title": m["title"][:30] if m["title"] else "Untitled",
            "date": m["date_iso"],  # ✅ Use pre-formatted ISO date from SQL
            "venue": m["venue"] or "TBD",
            "status": m["status"]
        })

    print(f"DEBUG: Found {len(events)} events: {events}")  # Debug line

    return render_template(
        "department_calendar.html",
        events=events
    )
# ---------------USER REGISTRATION BY THEMSELVES (sign up)-------------


# @app.route('/register', methods=['GET', 'POST'])
# def register():
#     if request.method == 'POST':
#         name = request.form['name']
#         email = request.form['email']
#         password = request.form['password']
#         role_id = request.form['role_id']
#         department_id = request.form['department_id']

#         # Validate password
#         if len(password) < 6:
#             return render_template('register.html',
#                                    error="Password must be at least 6 characters!",
#                                    departments=get_departments(),
#                                    roles=get_roles())  # ✅ Use get_roles()

#         # Check if email exists
#         cursor.execute("SELECT * FROM user WHERE email = %s", (email,))
#         if cursor.fetchone():
#             return render_template('register.html',
#                                    error="Email already registered!",
#                                    departments=get_departments(),
#                                    roles=get_roles())

#         # Check pending request
#         cursor.execute(
#             "SELECT * FROM registration_requests WHERE email = %s", (email,))
#         if cursor.fetchone():
#             return render_template('register.html',
#                                    error="Registration request already pending!",
#                                    departments=get_departments(),
#                                    roles=get_roles())

#         # Hash password and store
#         password_hash = generate_password_hash(password)
#         cursor.execute("""
#             INSERT INTO registration_requests (name, email, password_hash, role_id, department_id) 
#             VALUES (%s, %s, %s, %s, %s)
#         """, (name, email, password_hash, role_id, department_id))
#         conn.commit()

#         return render_template('register.html', success=True)

#     # ✅ FIXED: Use get_roles() not get_role()
#     return render_template('register.html',
#                            departments=get_departments(),
#                            roles=get_roles())
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        mobile_no = request.form['mobile_no']  # ✅ NEW: Mobile number
        password = request.form['password']
        role_id = request.form['role_id']
        department_id = request.form['department_id']
        
        # ✅ NEW: Validate mobile number
        if not mobile_no.isdigit() or len(mobile_no) != 10:
            return render_template('register.html', 
                                error="Mobile number must be exactly 10 digits!", 
                                departments=get_departments(),
                                roles=get_roles())
        
        # ✅ Check if mobile exists
        cursor.execute("SELECT * FROM user WHERE user_mobileNo = %s", (mobile_no,))
        if cursor.fetchone():
            return render_template('register.html', 
                                error="Mobile number already registered!", 
                                departments=get_departments(),
                                roles=get_roles())
        
        # Existing email checks...
        if len(password) < 6:
            return render_template('register.html', 
                                error="Password must be at least 6 characters!", 
                                departments=get_departments(),
                                roles=get_roles())
        
        cursor.execute("SELECT * FROM user WHERE email = %s", (email,))
        if cursor.fetchone():
            return render_template('register.html', 
                                error="Email already registered!", 
                                departments=get_departments(),
                                roles=get_roles())
        
        cursor.execute("SELECT * FROM registration_requests WHERE email = %s", (email,))
        if cursor.fetchone():
            return render_template('register.html', 
                                error="Registration request already pending!", 
                                departments=get_departments(),
                                roles=get_roles())
        
        # ✅ SAVE MOBILE NUMBER to registration_requests
        password_hash = generate_password_hash(password)
        cursor.execute("""
            INSERT INTO registration_requests 
            (name, email, user_mobileNo, password_hash, role_id, department_id) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, email, mobile_no, password_hash, role_id, department_id))  # ✅ Added mobile
        conn.commit()
        
        return render_template('register.html', success=True)
    
    return render_template('register.html',
                         departments=get_departments(),
                         roles=get_roles())


@app.route('/admin/registration_requests')
@login_required
def registration_requests():
    if session.get("role_id") != 100:  # ✅ Use session directly - SAFER
        return redirect(url_for('admin_dashboard'))

    cursor.execute("""
        SELECT r.*, d.department_name, r.role_id,
               (SELECT role_name FROM role WHERE role_id = r.role_id) as role_name
        FROM registration_requests r 
        LEFT JOIN department d ON r.department_id = d.department_id
        WHERE r.status = 'pending'
        ORDER BY r.created_at DESC
    """)
    requests = cursor.fetchall()

    return render_template('admin/registration_requests.html', requests=requests)


# @app.route('/admin/approve_request/<int:request_id>')
# @login_required
# def approve_request(request_id):
#     if get_role(session['user_id']) != 100:
#         return redirect(url_for('admin_dashboard'))

#     cursor.execute(
#         "SELECT * FROM registration_requests WHERE id = %s AND status = 'pending'", (request_id,))
#     request = cursor.fetchone()
#     if not request:
#         flash('Request not found or already processed!')
#         return redirect(url_for('registration_requests'))

#     # ✅ COPY ALL DATA including user's password_hash to user table
#     cursor.execute("""
#         INSERT INTO user (user_name, email, password_hash, department_id, role_id) 
#         VALUES (%s, %s, %s, %s, %s)
#     """, (request['name'], request['email'], request['password_hash'], request['department_id'], request['role_id']))

#     # Mark as approved
#     cursor.execute(
#         "UPDATE registration_requests SET status = 'approved' WHERE id = %s", (request_id,))
#     conn.commit()

#     flash(
#         f'✅ User "{request["name"]}" approved! They can login with their chosen password.')
#     return redirect(url_for('registration_requests'))
@app.route('/admin/approve_request/<int:request_id>')
@login_required
def approve_request(request_id):
    if get_role(session['user_id']) != 100:
        return redirect(url_for('admin_dashboard'))

    cursor.execute("SELECT * FROM registration_requests WHERE id = %s AND status = 'pending'", (request_id,))
    request = cursor.fetchone()
    if not request:
        flash('Request not found or already processed!')
        return redirect(url_for('registration_requests'))

    # ✅ COPY MOBILE NUMBER to user table
    cursor.execute("""
        INSERT INTO user (user_name, email, user_mobileNo, password_hash, department_id, role_id) 
        VALUES (%s, %s, %s, %s, %s, 101)
    """, (request['name'], request['email'], request['user_mobileNo'], request['password_hash'], request['department_id']))

    cursor.execute("UPDATE registration_requests SET status = 'approved' WHERE id = %s", (request_id,))
    conn.commit()

    flash(f'✅ User "{request["name"]}" ({request["user_mobileNo"]}) approved!')
    return redirect(url_for('registration_requests'))


@app.route('/admin/reject_request/<int:request_id>')
@login_required
def reject_request(request_id):
    if get_role(session['user_id']) != 100:
        return redirect(url_for('admin_dashboard'))

    cursor.execute(
        "UPDATE registration_requests SET status = 'rejected' WHERE id = %s", (request_id,))
    conn.commit()
    flash('❌ Registration request rejected!')
    return redirect(url_for('registration_requests'))

# ----------------------User Profile-------------------------------


@app.route('/profile')
def profile():
    if "user_id" not in session:
        return redirect('/login')

    user_id = session["user_id"]

    # Fetch user info with department, role, and mobile number
    cursor.execute("""
        SELECT u.user_name, u.email, u.user_mobileNo, d.department_name, r.role_name
        FROM user u
        LEFT JOIN department d ON u.department_id = d.department_id
        LEFT JOIN role r ON u.role_id = r.role_id
        WHERE u.user_id = %s
    """, (user_id,))

    user = cursor.fetchone()
    if not user:
        return "User not found", 404

    # Prepare user data with mobile number
    user_data = {
        "user_id": session["user_id"],
        "user_name": user["user_name"],
        "email": user["email"],
        "user_mobileNo": user["user_mobileNo"] or "N/A",
        "department_name": user["department_name"] or "N/A",
        "role_name": user["role_name"] or "N/A"
    }

    return render_template("user_profile.html", user=user_data)
#------------------Admin Profile------------

@app.route('/admin_profile')
def admin_profile():
    if "user_id" not in session:
        return redirect('/login')

    user_id = session["user_id"]

    # Fetch user info with department, role, and mobile number
    cursor.execute("""
        SELECT u.user_name, u.email, u.user_mobileNo, d.department_name, r.role_name
        FROM user u
        LEFT JOIN department d ON u.department_id = d.department_id
        LEFT JOIN role r ON u.role_id = r.role_id
        WHERE u.user_id = %s
    """, (user_id,))

    user = cursor.fetchone()
    if not user:
        return "User not found", 404

    # Prepare user data with mobile number
    user_data = {
        "user_id": session["user_id"],
        "user_name": user["user_name"],
        "email": user["email"],
        "user_mobileNo": user["user_mobileNo"] or "N/A",
        "department_name": user["department_name"] or "N/A",
        "role_name": user["role_name"] or "N/A"
    }

    return render_template("admin_profile.html", user=user_data)

    
#---------Edit admin Profile-------------
# @app.route('/edit_admin_profile')
# def edit_user_profile():
#     return render_template('edit_admin_profile.html')
# --------------------------Change Password-------------


@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if "user_id" not in session:
        return redirect('/login')

    message = ""

    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']

        # Fetch hashed password from DB - ✅ Fixed: lowercase 'user'
        cursor.execute(
            "SELECT password_hash FROM user WHERE user_id=%s", (session["user_id"],))
        stored_password_row = cursor.fetchone()

        if not stored_password_row:
            message = "User not found!"
            return render_template("change_password.html", message=message)

        # Access by key because cursor is dictionary=True
        stored_password = stored_password_row['password_hash']

        if check_password_hash(stored_password, old_password):
            new_hashed = generate_password_hash(new_password)
            cursor.execute(
                "UPDATE user SET password_hash=%s WHERE user_id=%s",
                (new_hashed, session["user_id"])
            )
            conn.commit()
            message = "Password updated successfully!"
        else:
            message = "Old password is incorrect!"

    return render_template("change_password.html", message=message)

#--------------------Edit Admin Profile----------
@app.route('/admin/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_admin_profile():
    user_id = session['user_id']
    
    # Get current user data
    cursor.execute("""
        SELECT u.user_name, u.email, u.user_mobileNo, u.department_id, u.role_id,
               d.department_name, r.role_name
        FROM user u
        LEFT JOIN department d ON u.department_id = d.department_id
        LEFT JOIN role r ON u.role_id = r.role_id
        WHERE u.user_id = %s
    """, (user_id,))
    current_user = cursor.fetchone()
    
    if request.method == 'POST':
        new_name = request.form['name']
        new_email = request.form['email']
        new_mobile = request.form['mobile_no']
        
        # ✅ UPDATE DATABASE
        cursor.execute("""
            UPDATE user 
            SET user_name = %s, email = %s, user_mobileNo = %s
            WHERE user_id = %s
        """, (new_name, new_email, new_mobile, user_id))
        
        # 🔥 CRITICAL: COMMIT THE CHANGES!
        conn.commit()  # ← THIS WAS MISSING!
        
        # Update session
        session['user_name'] = new_name
        session['email'] = new_email
        
        flash('✅ Profile updated successfully!')
        return redirect(url_for('profile'))
    
    # Get dropdown options
    cursor.execute("SELECT * FROM department ORDER BY department_name")
    departments = cursor.fetchall()
    
    cursor.execute("SELECT * FROM role ORDER BY role_name")
    roles = cursor.fetchall()
    
    return render_template('edit_admin_profile.html', 
                         user=current_user, 
                         departments=departments, 
                         roles=roles)
#----------------EDIT USER PROFILE ROUTE---------------------
@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user_id = session['user_id']
    
    # Get current user data
    cursor.execute("""
        SELECT u.user_name, u.email, u.user_mobileNo, u.department_id, u.role_id,
               d.department_name, r.role_name
        FROM user u
        LEFT JOIN department d ON u.department_id = d.department_id
        LEFT JOIN role r ON u.role_id = r.role_id
        WHERE u.user_id = %s
    """, (user_id,))
    current_user = cursor.fetchone()
    
    if request.method == 'POST':
        new_name = request.form['name']
        new_email = request.form['email']
        new_mobile = request.form['mobile_no']
        
        # ✅ UPDATE DATABASE
        cursor.execute("""
            UPDATE user 
            SET user_name = %s, email = %s, user_mobileNo = %s
            WHERE user_id = %s
        """, (new_name, new_email, new_mobile, user_id))
        
        # 🔥 CRITICAL: COMMIT THE CHANGES!
        conn.commit()  # ← THIS WAS MISSING!
        
        # Update session
        session['user_name'] = new_name
        session['email'] = new_email
        
        flash('✅ Profile updated successfully!')
        return redirect(url_for('profile'))
    
    # Get dropdown options
    cursor.execute("SELECT * FROM department ORDER BY department_name")
    departments = cursor.fetchall()
    
    cursor.execute("SELECT * FROM role ORDER BY role_name")
    roles = cursor.fetchall()
    
    return render_template('edit_profile.html', 
                         user=current_user, 
                         departments=departments, 
                         roles=roles)
# ---------------- CREATE SCHEDULE ----------------


# @app.route("/faculty/create-schedule", methods=["GET", "POST"])
# def create_schedule():
#     # if "user_id" not in session or session["role_id"] != 101:
#     #     return redirect(url_for("login"))

#     error = ""
#     success = ""
#     conflict_details = None

#     # 🔹 Fetch ALL departments for dropdown
#     cursor.execute("SELECT department_id, department_name FROM department")
#     departments = cursor.fetchall()

#     # 🔹 Fetch all members except admin
#     cursor.execute(
#     """
#     SELECT u.user_id, u.user_name, u.email, u.user_mobileNo, d.department_name
#     FROM user u
#     LEFT JOIN department d ON u.department_id = d.department_id
#     WHERE u.role_id != 100
#     """
# )
#     members = cursor.fetchall()

#     if request.method == "POST":
#         title = request.form["meeting_title"]
#         date = request.form["meeting_date"]
#         start_time = request.form["start_time"]
#         end_time = request.form["end_time"]
#         venue = request.form["venue"]
#         department_id = request.form["department_id"]   # ✅ NEW
#         participants = request.form.getlist("participants")

#         if not participants:
#             error = "Please select at least one participant."
#             return render_template(
#                 "create_schedule.html",
#                 members=members,
#                 departments=departments,
#                 error=error
#             )

#         # ---------------- CONFLICT CHECK ----------------
#         conflict_details = []

#         conflict_query = """
#         SELECT m.meeting_id, m.meeting_date, m.start_time, m.end_time
#         FROM meeting m
#         JOIN meeting_participant mp ON m.meeting_id = mp.meeting_id
#         WHERE mp.user_id = %s
#         AND m.meeting_date = %s
#         AND %s < m.end_time
#         AND %s > m.start_time
#         """

#         for user_id in participants:
#             cursor.execute(
#                 conflict_query, (user_id, date, start_time, end_time))
#             conflict = cursor.fetchone()

#             if conflict:
#                 cursor.execute(
#                     "SELECT user_name FROM user WHERE user_id = %s",
#                     (user_id,)
#                 )
#                 user_name = cursor.fetchone()["user_name"]

#                 cursor.execute(
#                     """
#                     SELECT department_name FROM department
#                     WHERE department_id = %s
#                     """,
#                     (department_id,)
#                 )
#                 department_name = cursor.fetchone()["department_name"]

#                 conflict_details.append({
#                     "user_id": user_id,
#                     "user_name": user_name,
#                     "department": department_name,
#                     "date": conflict["meeting_date"],
#                     "start_time": conflict["start_time"],
#                     "end_time": conflict["end_time"]
#                 })

#         if conflict_details:
#             error = "One or more selected members already have a conflicting meeting."
#             return render_template(
#                 "create_schedule.html",
#                 members=members,
#                 departments=departments,
#                 error=error,
#                 conflict_details=conflict_details
#             )

#         # ---------------- INSERT MEETING ----------------
#         insert_meeting = """
#         INSERT INTO meeting
#         (meeting_title, meeting_date, start_time, end_time,
#          user_id, department_id, venue)
#         VALUES (%s, %s, %s, %s, %s, %s, %s)
#         """
#         cursor.execute(insert_meeting, (
#             title, date, start_time, end_time,
#             session["user_id"], department_id, venue
#         ))
#         conn.commit()

#         meeting_id = cursor.lastrowid

#         # ---------------- INSERT PARTICIPANTS ----------------
#         insert_participant = """
#         INSERT INTO meeting_participant (user_id, meeting_id)
#         VALUES (%s, %s)
#         """
#         for user_id in participants:
#             cursor.execute(insert_participant, (user_id, meeting_id))
#         conn.commit()

#         success = "✅ Meeting scheduled successfully."

#     return render_template(
#         "create_schedule.html",
#         members=members,
#         departments=departments,
#         success=success,
#         error=error,
#         conflict_details=conflict_details
#     )
@app.route("/faculty/create-schedule", methods=["GET", "POST"])
def create_schedule():
    error = ""
    success = ""
    conflict_details = []

    # Fetch all departments for dropdown
    cursor.execute("SELECT department_id, department_name FROM department")
    departments = cursor.fetchall()

    # Fetch all members except admin
    cursor.execute(
        """
        SELECT u.user_id, u.user_name, u.email, u.user_mobileNo, d.department_name
        FROM user u
        LEFT JOIN department d ON u.department_id = d.department_id
        WHERE u.role_id != 100
        """
    )
    members = cursor.fetchall()

    def parse_time(time_str):
        try:
            return datetime.strptime(time_str, "%I:%M %p").strftime("%H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(time_str, "%H:%M").strftime("%H:%M:%S")
            except ValueError:
                raise ValueError(f"Time format not recognized: {time_str}")

    if request.method == "POST":
        title = request.form["meeting_title"]
        date_str = request.form["meeting_date"]
        start_time_str = request.form["start_time"]
        end_time_str = request.form["end_time"]
        venue = request.form["venue"]
        department_id = request.form["department_id"]
        participants = request.form.getlist("participants")

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time_24 = parse_time(start_time_str)
            end_time_24 = parse_time(end_time_str)
        except ValueError as e:
            error = str(e)
            return render_template(
                "create_schedule.html",
                members=members,
                departments=departments,
                error=error
            )

        if not participants:
            error = "Please select at least one participant."
            return render_template(
                "create_schedule.html",
                members=members,
                departments=departments,
                error=error
            )

        creator_id_str = str(session["user_id"])
        if creator_id_str not in participants:
            participants.append(creator_id_str)

        participant_ids = [int(pid) for pid in participants]

        format_strings = ','.join(['%s'] * len(participant_ids))
        conflict_query = f"""
        SELECT u.user_id, u.user_name, d_meeting.department_name AS meeting_department_name, m.meeting_title, m.meeting_date, m.start_time, m.end_time
        FROM meeting m
        JOIN meeting_participant mp ON m.meeting_id = mp.meeting_id
        JOIN user u ON mp.user_id = u.user_id
        LEFT JOIN department d_meeting ON m.department_id = d_meeting.department_id
        WHERE m.meeting_date = %s
        AND u.user_id IN ({format_strings})
        AND %s < m.end_time
        AND %s > m.start_time
        """
        conflict_params = [date, *participant_ids, start_time_24, end_time_24]
        cursor.execute(conflict_query, conflict_params)
        conflicting_members = cursor.fetchall()

        if conflicting_members:
            conflict_messages = []
            for member in conflicting_members:
                conflict_messages.append(
                f"Member: {member['user_name']} (ID: {member['user_id']}), "
                f"Meeting Dept: {member['meeting_department_name']}, "
                f"Scheduled on: {member['meeting_date']} "
                f"from {member['start_time']} to {member['end_time']}\n"
                )
            error_message = "Conflicts detected:\n" + "\n".join(conflict_messages)
            return render_template(
                "create_schedule.html",
                members=members,
                departments=departments,
                error=error_message
            )

        # Insert the new meeting
        insert_meeting = """
        INSERT INTO meeting
        (meeting_title, meeting_date, start_time, end_time, user_id, department_id, venue)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_meeting, (
            title, date, start_time_24, end_time_24,
            session["user_id"], department_id, venue
        ))
        conn.commit()

        meeting_id = cursor.lastrowid

        # Insert participants
        insert_participant = "INSERT INTO meeting_participant (user_id, meeting_id) VALUES (%s, %s)"
        for user_id in participant_ids:
            cursor.execute(insert_participant, (user_id, meeting_id))
        conn.commit()

        # *** NEW: SEND CREATE EMAIL ***
        # Get meeting details
        cursor.execute("""
            SELECT m.meeting_title, m.meeting_date, m.start_time, m.end_time, m.venue, d.department_name 
            FROM meeting m 
            JOIN department d ON m.department_id = d.department_id 
            WHERE m.meeting_id = %s
        """, (meeting_id,))
        meeting_details = cursor.fetchone()

        # Get participant emails (including creator)
        cursor.execute("""
            SELECT DISTINCT u.email 
            FROM meeting_participant mp 
            JOIN user u ON mp.user_id = u.user_id 
            WHERE mp.meeting_id = %s AND u.email IS NOT NULL
        """, (meeting_id,))
        emails = [row['email'] for row in cursor.fetchall()]

        if emails and meeting_details:
            meeting_info = {
                'title': meeting_details['meeting_title'],
                'date': meeting_details['meeting_date'],
                'start_time': meeting_details['start_time'],
                'end_time': meeting_details['end_time'],
                'venue': meeting_details['venue'],
                'dept_name': meeting_details['department_name']
            }
            send_meeting_email(emails, 'created', meeting_info)

        success = "✅ Meeting scheduled successfully."

    return render_template(
        "create_schedule.html",
        members=members,
        departments=departments,
        success=success,
        error=error
    )
# ---------------- RUN APP ----------------
if __name__ == "__main__":
     # Start the scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from datetime import datetime

    def delete_past_meetings():
        try:
            cursor.execute("DELETE FROM meeting WHERE meeting_date < CURDATE()")
            conn.commit()
            print(f"[{datetime.now()}] Old meetings deleted.")
        except Exception as e:
            print(f"Error deleting old meetings: {e}")

    scheduler = BackgroundScheduler()
    scheduler.add_job(delete_past_meetings, 'cron', hour=0, minute=0)
    scheduler.start()
    app.run(debug=True)
# #delete old meetings locally
# def delete_past_meetings():
#     try:
#         cursor.execute("DELETE FROM meeting WHERE meeting_date < CURDATE()")
#         conn.commit()
#         print(f"[{datetime.now()}] Old meetings deleted.")
#     except Exception as e:
#         print(f"Error deleting old meetings: {e}")

# if __name__ == "__main__":
#     # Test the delete function immediately
#     delete_past_meetings()
#     app.run(debug=True)