from flask import Flask, flash, render_template, request, redirect, url_for, session
import psycopg2
import psycopg2.extras
from werkzeug.security import check_password_hash, generate_password_hash
import calendar
from datetime import datetime, date
from functools import wraps
import smtplib
import os


app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")


# Gmail SMTP config - Use App Password (generate at https://myaccount.google.com/apppasswords)
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")

# ---------------- DATABASE CONNECTION ----------------
def get_db():
    """Get a new database connection per request."""
    db_url = os.environ.get('DATABASE_URL', '')
    # Render gives 'postgres://' but psycopg2 needs 'postgresql://'
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    conn = psycopg2.connect(db_url)
    return conn

def execute_query(query, params=None, fetch='all', commit=False):
    """
    Execute a query and return results.
    fetch: 'all', 'one', or None
    commit: True for INSERT/UPDATE/DELETE
    Returns: fetched rows (as dicts), lastrowid for INSERT, or None
    """
    # PostgreSQL uses %s placeholders — same as MySQL, so no query changes needed.
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(query, params)
        result = None
        if fetch == 'all':
            result = cursor.fetchall()
            # Convert RealDictRow list to plain list of dicts
            result = [dict(row) for row in result]
        elif fetch == 'one':
            row = cursor.fetchone()
            result = dict(row) if row else None
        if commit:
            conn.commit()
            # For INSERT, return the last inserted id
            if query.strip().upper().startswith('INSERT'):
                # PostgreSQL uses RETURNING or lastval()
                cursor.execute("SELECT lastval()")
                last_id = cursor.fetchone()
                result = last_id[0] if last_id else None
        return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


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
        if role_id != 100:
            flash("Admin access required!")
            return redirect(url_for('faculty_dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_role(user_id):
    """Get user role from database"""
    result = execute_query(
        'SELECT role_id FROM "user" WHERE user_id = %s', (user_id,), fetch='one'
    )
    return result['role_id'] if result else None


def get_departments():
    return execute_query(
        "SELECT * FROM department ORDER BY department_name", fetch='all'
    )


def get_roles():
    """Get all roles from database"""
    return execute_query(
        """SELECT role_id, role_name FROM role WHERE role_id != 100 ORDER BY role_name""",
        fetch='all'
    )


def send_meeting_email(recipients, action, meeting_info):
    """Send notification email to meeting members."""
    if action == 'created':
        subject = f'New Meeting Created: {meeting_info["title"]}'
    elif action == 'updated':
        subject = f'Meeting Updated: {meeting_info["title"]}'
    else:
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
        identifier = request.form['username']
        password = request.form['password']

        user = execute_query(
            'SELECT * FROM "user" WHERE user_id = %s OR email = %s',
            (identifier, identifier),
            fetch='one'
        )

        if user and check_password_hash(user['password_hash'], password):
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
    user_name = session.get("user_name", "Admin")
    return render_template("admin/admin_dashboard.html", user=user_name)


@app.route("/faculty/dashboard")
def faculty_dashboard():
    user_name = session.get("user_name", "Faculty")
    return render_template("faculty_dashboard.html", user=user_name)


# -------------------Admin Dashboard------------------

@app.route("/admin/add-department", methods=["GET", "POST"])
def add_department():
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    if request.method == "POST":
        department_name = request.form["department_name"]
        execute_query(
            "INSERT INTO department (department_name) VALUES (%s)",
            (department_name,),
            commit=True
        )
        return redirect(url_for("view_departments"))

    return render_template("admin/add_department.html")


@app.route("/admin/view-departments", methods=["GET"])
def view_departments():
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    search = request.args.get("search", "").strip()

    if search:
        departments = execute_query(
            "SELECT * FROM department WHERE department_name ILIKE %s",
            ("%" + search + "%",),
            fetch='all'
        )
    else:
        departments = execute_query("SELECT * FROM department", fetch='all')

    return render_template(
        "admin/view_departments.html",
        departments=departments,
        search_query=search
    )


@app.route("/admin/delete-department/<int:dept_id>")
def delete_department(dept_id):
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    users_count = execute_query(
        'SELECT COUNT(*) AS total FROM "user" WHERE department_id=%s',
        (dept_id,), fetch='one'
    )['total']

    meetings_count = execute_query(
        "SELECT COUNT(*) AS total FROM meeting WHERE department_id=%s",
        (dept_id,), fetch='one'
    )['total']

    if users_count > 0 or meetings_count > 0:
        return "❌ Cannot delete department. Users or meetings exist."

    execute_query(
        "DELETE FROM department WHERE department_id=%s",
        (dept_id,), commit=True, fetch=None
    )
    return redirect(url_for("view_departments"))


@app.route("/admin/search-departments")
def search_departments():
    if "user_id" not in session or session["role_id"] != 100:
        return {"error": "Unauthorized"}, 403

    keyword = request.args.get("q", "").strip()

    if keyword == "":
        departments = execute_query("SELECT * FROM department", fetch='all')
    else:
        departments = execute_query(
            "SELECT * FROM department WHERE department_name ILIKE %s",
            ("%" + keyword + "%",), fetch='all'
        )
    return {"departments": departments}


@app.route("/admin/view-users")
def view_users():
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    keyword = request.args.get("q", "").strip()

    query = """
        SELECT u.user_id, u.user_name, u.email, u.user_mobileno,
               d.department_name, r.role_name, u.role_id
        FROM "user" u
        LEFT JOIN department d ON u.department_id = d.department_id
        LEFT JOIN role r ON u.role_id = r.role_id
    """
    params = []

    if keyword:
        query += """
        WHERE u.user_name ILIKE %s
           OR u.email ILIKE %s
           OR d.department_name ILIKE %s
           OR r.role_name ILIKE %s
        """
        params = ["%" + keyword + "%"] * 4

    query += ' ORDER BY u.user_id'

    users = execute_query(query, params if params else None, fetch='all')
    users = [u for u in users if u['role_id'] != 100]

    return render_template("admin/view_users.html", users=users, search_query=keyword)


@app.route("/admin/edit-user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    if request.method == "POST":
        user_name = request.form["user_name"]
        email = request.form["email"]
        department_id = request.form.get("department_id")
        role_id = request.form["role_id"]

        execute_query("""
            UPDATE "user"
            SET user_name=%s, email=%s, department_id=%s, role_id=%s
            WHERE user_id=%s
        """, (user_name, email, department_id, role_id, user_id), commit=True, fetch=None)

        return redirect(url_for("view_users"))

    user = execute_query('SELECT * FROM "user" WHERE user_id=%s', (user_id,), fetch='one')
    departments = execute_query("SELECT * FROM department", fetch='all')
    roles = execute_query("SELECT * FROM role", fetch='all')

    return render_template("admin/edit_user.html", user=user, departments=departments, roles=roles)


@app.route("/admin/delete-user/<int:user_id>")
def delete_user(user_id):
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    execute_query('DELETE FROM "user" WHERE user_id=%s', (user_id,), commit=True, fetch=None)
    return redirect(url_for("view_users"))


@app.route("/admin/search-meetings")
def search_meetings():
    if "user_id" not in session or session["role_id"] != 100:
        return {"error": "Unauthorized"}, 403

    keyword = request.args.get("q", "").strip()

    query = """
        SELECT m.meeting_title, m.meeting_date, m.start_time, m.end_time,
               m.venue, d.department_name, u.user_name
        FROM meeting m
        JOIN department d ON m.department_id = d.department_id
        JOIN "user" u ON m.user_id = u.user_id
    """
    params = []

    if keyword:
        query += """
        WHERE m.meeting_title ILIKE %s
           OR d.department_name ILIKE %s
           OR u.user_name ILIKE %s
        """
        params = ["%" + keyword + "%"] * 3

    results = execute_query(query, params if params else None, fetch='all')

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


# ---------------- MY CREATED MEETINGS ----------------

@app.route("/faculty/my-created-meetings")
@login_required
def my_created_meetings():
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
        query += " AND (m.meeting_title ILIKE %s OR d.department_name ILIKE %s)"
        params.extend(["%" + keyword + "%"] * 2)

    query += " GROUP BY m.meeting_id, m.meeting_title, m.meeting_date, m.start_time, m.end_time, m.venue, d.department_name ORDER BY m.meeting_date DESC"

    meetings = execute_query(query, params, fetch='all')
    return render_template("my_created_meetings.html", meetings=meetings, search_query=keyword)


@app.route("/faculty/meeting-edit/<int:meeting_id>", methods=['GET', 'POST'])
@login_required
def edit_meeting(meeting_id):
    meeting = execute_query(
        "SELECT * FROM meeting WHERE meeting_id = %s AND user_id = %s",
        (meeting_id, session["user_id"]), fetch='one'
    )
    if not meeting:
        flash("❌ You can only edit your own meetings!")
        return redirect(url_for("my_created_meetings"))

    participants = execute_query("""
        SELECT u.user_id, u.user_name
        FROM meeting_participant mp
        JOIN "user" u ON mp.user_id = u.user_id
        WHERE mp.meeting_id = %s
    """, (meeting_id,), fetch='all')

    all_users = execute_query("""
        SELECT u.user_id, u.user_name, u.email, u.user_mobileno, d.department_name
        FROM "user" u
        LEFT JOIN department d ON u.department_id = d.department_id
        WHERE u.role_id != 100
    """, fetch='all')

    departments = execute_query("SELECT * FROM department ORDER BY department_name", fetch='all')

    def parse_time(time_str):
        for fmt in ("%H:%M:%S", "%I:%M %p", "%H:%M"):
            try:
                return datetime.strptime(str(time_str), fmt).strftime("%H:%M:%S")
            except ValueError:
                continue
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
            JOIN "user" u ON mp.user_id = u.user_id
            LEFT JOIN department d_meeting ON m.department_id = d_meeting.department_id
            WHERE m.meeting_date = %s
            AND u.user_id IN ({format_strings})
            AND %s < m.end_time
            AND %s > m.start_time
            AND m.meeting_id != %s
        """
        conflict_params = [new_date, *participant_ids, new_start_time, new_end_time, meeting_id]
        conflicting_members = execute_query(conflict_query, conflict_params, fetch='all')

        if conflicting_members:
            conflict_messages = [
                f"Member: {m['user_name']} (ID: {m['user_id']}), "
                f"Meeting Dept: {m['meeting_department_name']}, "
                f"Scheduled on: {m['meeting_date']} from {m['start_time']} to {m['end_time']}"
                for m in conflicting_members
            ]
            flash("Conflicts detected:\n" + "\n".join(conflict_messages))
            return render_template('edit_meeting.html',
                                   meeting=meeting, participants=participants,
                                   all_users=all_users, departments=departments)

        execute_query("""
            UPDATE meeting SET meeting_title=%s, meeting_date=%s,
            start_time=%s, end_time=%s, venue=%s, department_id=%s
            WHERE meeting_id=%s
        """, (new_title, new_date, new_start_time, new_end_time, new_venue, new_dept_id, meeting_id),
            commit=True, fetch=None)

        execute_query("DELETE FROM meeting_participant WHERE meeting_id=%s",
                      (meeting_id,), commit=True, fetch=None)
        for uid in new_participants:
            execute_query("INSERT INTO meeting_participant (user_id, meeting_id) VALUES (%s, %s)",
                          (uid, meeting_id), commit=True, fetch=None)

        meeting_details = execute_query("""
            SELECT m.meeting_title, m.meeting_date, m.start_time, m.end_time, m.venue, d.department_name
            FROM meeting m
            JOIN department d ON m.department_id = d.department_id
            WHERE m.meeting_id = %s
        """, (meeting_id,), fetch='one')

        emails_rows = execute_query("""
            SELECT DISTINCT u.email
            FROM meeting_participant mp
            JOIN "user" u ON mp.user_id = u.user_id
            WHERE mp.meeting_id = %s AND u.email IS NOT NULL
        """, (meeting_id,), fetch='all')
        emails = [row['email'] for row in emails_rows]

        if emails and meeting_details:
            send_meeting_email(emails, 'updated', {
                'title': meeting_details['meeting_title'],
                'date': meeting_details['meeting_date'],
                'start_time': meeting_details['start_time'],
                'end_time': meeting_details['end_time'],
                'venue': meeting_details['venue'],
                'dept_name': meeting_details['department_name']
            })

        flash('✅ Meeting updated successfully!')
        return redirect(url_for('my_created_meetings'))

    return render_template('edit_meeting.html',
                           meeting=meeting, participants=participants,
                           all_users=all_users, departments=departments)


@app.route("/faculty/delete-meeting/<int:meeting_id>")
@login_required
def delete_meeting(meeting_id):
    meeting = execute_query("""
        SELECT meeting_title FROM meeting
        WHERE meeting_id = %s AND user_id = %s
    """, (meeting_id, session["user_id"]), fetch='one')

    if not meeting:
        flash("❌ You can only delete your own meetings!")
        return redirect(url_for("my_created_meetings"))

    emails_rows = execute_query("""
        SELECT DISTINCT u.email
        FROM meeting_participant mp
        JOIN "user" u ON mp.user_id = u.user_id
        WHERE mp.meeting_id = %s AND u.email IS NOT NULL
    """, (meeting_id,), fetch='all')
    emails = [row['email'] for row in emails_rows]

    if emails:
        title = meeting['meeting_title']
        send_meeting_email(emails, 'deleted/cancelled', {
            'title': title[:50] + '...' if len(title) > 50 else title,
            'date': 'N/A (cancelled)', 'start_time': 'N/A',
            'end_time': 'N/A', 'venue': 'N/A', 'dept_name': 'N/A'
        })

    execute_query("DELETE FROM meeting_participant WHERE meeting_id = %s",
                  (meeting_id,), commit=True, fetch=None)
    execute_query("DELETE FROM meeting WHERE meeting_id = %s",
                  (meeting_id,), commit=True, fetch=None)

    flash(f'✅ "{meeting["meeting_title"][:30]}" deleted successfully!')
    return redirect(url_for("my_created_meetings"))


@app.route("/admin/edit-department/<int:dept_id>", methods=["GET", "POST"])
def edit_department(dept_id):
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    if request.method == "POST":
        department_name = request.form["department_name"]
        execute_query(
            "UPDATE department SET department_name=%s WHERE department_id=%s",
            (department_name, dept_id), commit=True, fetch=None
        )
        return redirect(url_for("view_departments"))

    department = execute_query(
        "SELECT * FROM department WHERE department_id=%s", (dept_id,), fetch='one'
    )
    return render_template("admin/edit_department.html", department=department)


@app.route("/admin/add-user", methods=["GET", "POST"])
def add_user():
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    if request.method == "POST":
        user_name = request.form["name"]
        email = request.form["email"]
        user_mobileNo = request.form["mobile_no"]
        password = request.form["password"]
        role_id = request.form["role_id"]
        department_id = request.form["department_id"]

        role = execute_query("SELECT role_id FROM role WHERE role_id = %s", (role_id,), fetch='one')
        if not role:
            flash("Invalid role selected!")
            return redirect(url_for("add_user"))

        hashed_password = generate_password_hash(password)

        execute_query("""
            INSERT INTO "user"
            (user_name, email, user_mobileno, password_hash, role_id, department_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_name, email, user_mobileNo, hashed_password, role_id, department_id),
            commit=True, fetch=None)

        flash(f'✅ User "{user_name}" added successfully!')
        return redirect(url_for("view_users"))

    roles = execute_query("SELECT role_id, role_name FROM role ORDER BY role_name", fetch='all')
    departments = execute_query("SELECT * FROM department ORDER BY department_name", fetch='all')

    return render_template("admin/add_user.html", departments=departments, roles=roles)


@app.route("/admin/view-meetings")
def view_all_meetings():
    if "user_id" not in session or session["role_id"] != 100:
        return redirect(url_for("login"))

    keyword = request.args.get("q", "").strip()

    query = """
        SELECT m.meeting_id, m.meeting_title, m.meeting_date,
               m.start_time, m.end_time, m.venue, m.user_id,
               d.department_name, u.user_name, u.user_mobileno,
               COUNT(mp.participant_id) as participant_count
        FROM meeting m
        JOIN department d ON m.department_id = d.department_id
        JOIN "user" u ON m.user_id = u.user_id
        LEFT JOIN meeting_participant mp ON m.meeting_id = mp.meeting_id
    """
    params = []

    if keyword:
        query += """
        WHERE m.meeting_title ILIKE %s OR d.department_name ILIKE %s OR u.user_name ILIKE %s
        """
        params = ["%" + keyword + "%"] * 3

    query += """
        GROUP BY m.meeting_id, m.meeting_title, m.meeting_date, m.start_time,
                 m.end_time, m.venue, m.user_id, d.department_name, u.user_name, u.user_mobileno
        ORDER BY m.meeting_date DESC
    """

    meetings = execute_query(query, params if params else None, fetch='all')
    return render_template("admin/view_meetings.html", meetings=meetings, search_query=keyword)


@app.route("/admin/view-meeting-members/<int:meeting_id>")
@login_required
def view_meeting_members(meeting_id):
    meeting = execute_query("""
        SELECT m.meeting_title, m.meeting_date, m.start_time, m.end_time,
               d.department_name, u.user_name as creator_name, u.user_id as creator_id
        FROM meeting m
        JOIN department d ON m.department_id = d.department_id
        JOIN "user" u ON m.user_id = u.user_id
        WHERE m.meeting_id = %s
    """, (meeting_id,), fetch='one')

    if not meeting:
        flash("Meeting not found!", "error")
        return redirect(url_for("view_all_meetings"))

    members = execute_query("""
        SELECT DISTINCT mp.participant_id, mp.user_id, u.user_name,
               u.email, u.user_mobileno, r.role_name, d.department_name
        FROM meeting_participant mp
        JOIN "user" u ON mp.user_id = u.user_id
        LEFT JOIN role r ON u.role_id = r.role_id
        LEFT JOIN department d ON u.department_id = d.department_id
        WHERE mp.meeting_id = %s
        ORDER BY u.user_name
    """, (meeting_id,), fetch='all')

    return render_template("/view_meeting_members.html",
                           meeting=meeting, members=members,
                           participant_count=len(members))


@app.route("/view-my-meeting-members/<int:meeting_id>")
@login_required
def view_my_meeting_members(meeting_id):
    meeting = execute_query("""
        SELECT m.meeting_title, m.meeting_date, m.start_time, m.end_time,
               d.department_name, u.user_name as creator_name, u.user_id as creator_id
        FROM meeting m
        JOIN department d ON m.department_id = d.department_id
        JOIN "user" u ON m.user_id = u.user_id
        WHERE m.meeting_id = %s
    """, (meeting_id,), fetch='one')

    if not meeting:
        flash("Meeting not found!", "error")
        return redirect(url_for("view_all_meetings"))

    members = execute_query("""
        SELECT DISTINCT mp.participant_id, mp.user_id, u.user_name,
               u.email, u.user_mobileno, r.role_name, d.department_name
        FROM meeting_participant mp
        JOIN "user" u ON mp.user_id = u.user_id
        LEFT JOIN role r ON u.role_id = r.role_id
        LEFT JOIN department d ON u.department_id = d.department_id
        WHERE mp.meeting_id = %s
        ORDER BY u.user_name
    """, (meeting_id,), fetch='all')

    return render_template("/view_my_meeting_members.html",
                           meeting=meeting, members=members,
                           participant_count=len(members))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/faculty/my-schedule")
def my_schedule():
    keyword = request.args.get("q", "").strip()

    query = """
        SELECT m.meeting_id, m.meeting_title, m.meeting_date,
               m.start_time, m.end_time, m.venue, m.user_id,
               d.department_name, u.user_name, u.user_mobileno,
               COUNT(mp.participant_id) as participant_count
        FROM meeting m
        JOIN department d ON m.department_id = d.department_id
        JOIN "user" u ON m.user_id = u.user_id
        LEFT JOIN meeting_participant mp ON m.meeting_id = mp.meeting_id
    """
    params = []

    if keyword:
        query += " WHERE m.meeting_title ILIKE %s OR d.department_name ILIKE %s OR u.user_name ILIKE %s"
        params = ["%" + keyword + "%"] * 3

    query += """
        GROUP BY m.meeting_id, m.meeting_title, m.meeting_date, m.start_time,
                 m.end_time, m.venue, m.user_id, d.department_name, u.user_name, u.user_mobileno
        ORDER BY m.meeting_date DESC
    """

    meetings = execute_query(query, params if params else None, fetch='all')
    return render_template("/my_schedule.html", meetings=meetings, search_query=keyword)


@app.route('/department_calendar')
def department_calendar():
    if "user_id" not in session:
        return redirect('/login')

    user_id = session["user_id"]

    dept = execute_query(
        'SELECT department_id FROM "user" WHERE user_id = %s', (user_id,), fetch='one'
    )

    if not dept or not dept["department_id"]:
        return "Department not assigned", 404

    department_id = dept["department_id"]

    # PostgreSQL equivalent of CURDATE() is CURRENT_DATE
    # DATE_FORMAT() -> TO_CHAR() in PostgreSQL
    meetings = execute_query("""
        SELECT m.meeting_id, m.meeting_title as title, m.meeting_date as date, m.venue,
               CASE WHEN m.meeting_date < CURRENT_DATE THEN 'past' ELSE 'upcoming' END as status,
               TO_CHAR(m.meeting_date, 'YYYY-MM-DD') as date_iso
        FROM meeting m
        WHERE m.department_id = %s
    """, (department_id,), fetch='all')

    events = []
    for m in meetings:
        events.append({
            "title": m["title"][:30] if m["title"] else "Untitled",
            "date": m["date_iso"],
            "venue": m["venue"] or "TBD",
            "status": m["status"]
        })

    return render_template("department_calendar.html", events=events)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        mobile_no = request.form['mobile_no']
        password = request.form['password']
        role_id = request.form['role_id']
        department_id = request.form['department_id']

        if not mobile_no.isdigit() or len(mobile_no) != 10:
            return render_template('register.html',
                                   error="Mobile number must be exactly 10 digits!",
                                   departments=get_departments(), roles=get_roles())

        existing_mobile = execute_query(
            'SELECT * FROM "user" WHERE user_mobileno = %s', (mobile_no,), fetch='one'
        )
        if existing_mobile:
            return render_template('register.html',
                                   error="Mobile number already registered!",
                                   departments=get_departments(), roles=get_roles())

        if len(password) < 6:
            return render_template('register.html',
                                   error="Password must be at least 6 characters!",
                                   departments=get_departments(), roles=get_roles())

        existing_email = execute_query(
            'SELECT * FROM "user" WHERE email = %s', (email,), fetch='one'
        )
        if existing_email:
            return render_template('register.html',
                                   error="Email already registered!",
                                   departments=get_departments(), roles=get_roles())

        existing_request = execute_query(
            "SELECT * FROM registration_requests WHERE email = %s", (email,), fetch='one'
        )
        if existing_request:
            return render_template('register.html',
                                   error="Registration request already pending!",
                                   departments=get_departments(), roles=get_roles())

        password_hash = generate_password_hash(password)
        execute_query("""
            INSERT INTO registration_requests
            (name, email, user_mobileno, password_hash, role_id, department_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, email, mobile_no, password_hash, role_id, department_id),
            commit=True, fetch=None)

        return render_template('register.html', success=True)

    return render_template('register.html', departments=get_departments(), roles=get_roles())


@app.route('/admin/registration_requests')
@login_required
def registration_requests():
    if session.get("role_id") != 100:
        return redirect(url_for('admin_dashboard'))

    requests_list = execute_query("""
        SELECT r.*, d.department_name, r.role_id,
               (SELECT role_name FROM role WHERE role_id = r.role_id) as role_name
        FROM registration_requests r
        LEFT JOIN department d ON r.department_id = d.department_id
        WHERE r.status = 'pending'
        ORDER BY r.created_at DESC
    """, fetch='all')

    return render_template('admin/registration_requests.html', requests=requests_list)


@app.route('/admin/approve_request/<int:request_id>')
@login_required
def approve_request(request_id):
    if get_role(session['user_id']) != 100:
        return redirect(url_for('admin_dashboard'))

    reg_request = execute_query(
        "SELECT * FROM registration_requests WHERE id = %s AND status = 'pending'",
        (request_id,), fetch='one'
    )
    if not reg_request:
        flash('Request not found or already processed!')
        return redirect(url_for('registration_requests'))

    execute_query("""
        INSERT INTO "user" (user_name, email, user_mobileno, password_hash, department_id, role_id)
        VALUES (%s, %s, %s, %s, %s, 101)
    """, (reg_request['name'], reg_request['email'], reg_request['user_mobileno'],
          reg_request['password_hash'], reg_request['department_id']),
        commit=True, fetch=None)

    execute_query(
        "UPDATE registration_requests SET status = 'approved' WHERE id = %s",
        (request_id,), commit=True, fetch=None
    )

    flash(f'✅ User "{reg_request["name"]}" ({reg_request["user_mobileno"]}) approved!')
    return redirect(url_for('registration_requests'))


@app.route('/admin/reject_request/<int:request_id>')
@login_required
def reject_request(request_id):
    if get_role(session['user_id']) != 100:
        return redirect(url_for('admin_dashboard'))

    execute_query(
        "UPDATE registration_requests SET status = 'rejected' WHERE id = %s",
        (request_id,), commit=True, fetch=None
    )
    flash('❌ Registration request rejected!')
    return redirect(url_for('registration_requests'))


@app.route('/profile')
def profile():
    if "user_id" not in session:
        return redirect('/login')

    user = execute_query("""
        SELECT u.user_name, u.email, u.user_mobileno, d.department_name, r.role_name
        FROM "user" u
        LEFT JOIN department d ON u.department_id = d.department_id
        LEFT JOIN role r ON u.role_id = r.role_id
        WHERE u.user_id = %s
    """, (session["user_id"],), fetch='one')

    if not user:
        return "User not found", 404

    user_data = {
        "user_id": session["user_id"],
        "user_name": user["user_name"],
        "email": user["email"],
        "user_mobileNo": user["user_mobileno"] or "N/A",
        "department_name": user["department_name"] or "N/A",
        "role_name": user["role_name"] or "N/A"
    }
    return render_template("user_profile.html", user=user_data)


@app.route('/admin_profile')
def admin_profile():
    if "user_id" not in session:
        return redirect('/login')

    user = execute_query("""
        SELECT u.user_name, u.email, u.user_mobileno, d.department_name, r.role_name
        FROM "user" u
        LEFT JOIN department d ON u.department_id = d.department_id
        LEFT JOIN role r ON u.role_id = r.role_id
        WHERE u.user_id = %s
    """, (session["user_id"],), fetch='one')

    if not user:
        return "User not found", 404

    user_data = {
        "user_id": session["user_id"],
        "user_name": user["user_name"],
        "email": user["email"],
        "user_mobileNo": user["user_mobileno"] or "N/A",
        "department_name": user["department_name"] or "N/A",
        "role_name": user["role_name"] or "N/A"
    }
    return render_template("admin_profile.html", user=user_data)


@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if "user_id" not in session:
        return redirect('/login')

    message = ""

    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']

        stored = execute_query(
            'SELECT password_hash FROM "user" WHERE user_id=%s',
            (session["user_id"],), fetch='one'
        )

        if not stored:
            message = "User not found!"
            return render_template("change_password.html", message=message)

        if check_password_hash(stored['password_hash'], old_password):
            new_hashed = generate_password_hash(new_password)
            execute_query(
                'UPDATE "user" SET password_hash=%s WHERE user_id=%s',
                (new_hashed, session["user_id"]), commit=True, fetch=None
            )
            message = "Password updated successfully!"
        else:
            message = "Old password is incorrect!"

    return render_template("change_password.html", message=message)


@app.route('/admin/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_admin_profile():
    user_id = session['user_id']

    current_user = execute_query("""
        SELECT u.user_name, u.email, u.user_mobileno, u.department_id, u.role_id,
               d.department_name, r.role_name
        FROM "user" u
        LEFT JOIN department d ON u.department_id = d.department_id
        LEFT JOIN role r ON u.role_id = r.role_id
        WHERE u.user_id = %s
    """, (user_id,), fetch='one')

    if request.method == 'POST':
        new_name = request.form['name']
        new_email = request.form['email']
        new_mobile = request.form['mobile_no']

        execute_query("""
            UPDATE "user" SET user_name = %s, email = %s, user_mobileno = %s
            WHERE user_id = %s
        """, (new_name, new_email, new_mobile, user_id), commit=True, fetch=None)

        session['user_name'] = new_name
        session['email'] = new_email

        flash('✅ Profile updated successfully!')
        return redirect(url_for('profile'))

    departments = execute_query("SELECT * FROM department ORDER BY department_name", fetch='all')
    roles = execute_query("SELECT * FROM role ORDER BY role_name", fetch='all')

    return render_template('edit_admin_profile.html',
                           user=current_user, departments=departments, roles=roles)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user_id = session['user_id']

    current_user = execute_query("""
        SELECT u.user_name, u.email, u.user_mobileno, u.department_id, u.role_id,
               d.department_name, r.role_name
        FROM "user" u
        LEFT JOIN department d ON u.department_id = d.department_id
        LEFT JOIN role r ON u.role_id = r.role_id
        WHERE u.user_id = %s
    """, (user_id,), fetch='one')

    if request.method == 'POST':
        new_name = request.form['name']
        new_email = request.form['email']
        new_mobile = request.form['mobile_no']

        execute_query("""
            UPDATE "user" SET user_name = %s, email = %s, user_mobileno = %s
            WHERE user_id = %s
        """, (new_name, new_email, new_mobile, user_id), commit=True, fetch=None)

        session['user_name'] = new_name
        session['email'] = new_email

        flash('✅ Profile updated successfully!')
        return redirect(url_for('profile'))

    departments = execute_query("SELECT * FROM department ORDER BY department_name", fetch='all')
    roles = execute_query("SELECT * FROM role ORDER BY role_name", fetch='all')

    return render_template('edit_profile.html',
                           user=current_user, departments=departments, roles=roles)


@app.route("/faculty/create-schedule", methods=["GET", "POST"])
def create_schedule():
    error = ""
    success = ""

    departments = execute_query("SELECT department_id, department_name FROM department", fetch='all')
    all_users = execute_query("""
        SELECT u.user_id, u.user_name, u.email, u.user_mobileno, d.department_name
        FROM "user" u
        LEFT JOIN department d ON u.department_id = d.department_id
        WHERE u.role_id != 100
    """, fetch='all')

    def parse_time(time_str):
        for fmt in ("%I:%M %p", "%H:%M"):
            try:
                return datetime.strptime(time_str, fmt).strftime("%H:%M:%S")
            except ValueError:
                continue
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
            meeting_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time_24 = parse_time(start_time_str)
            end_time_24 = parse_time(end_time_str)
        except ValueError as e:
            error = str(e)
            return render_template("create_schedule.html",
                                   members=all_users, departments=departments, error=error)

        if not participants:
            error = "Please select at least one participant."
            return render_template("create_schedule.html",
                                   members=all_users, departments=departments, error=error)

        creator_id_str = str(session["user_id"])
        if creator_id_str not in participants:
            participants.append(creator_id_str)

        participant_ids = [int(pid) for pid in participants]
        format_strings = ','.join(['%s'] * len(participant_ids))

        conflict_query = f"""
            SELECT u.user_id, u.user_name, d_meeting.department_name AS meeting_department_name,
                   m.meeting_title, m.meeting_date, m.start_time, m.end_time
            FROM meeting m
            JOIN meeting_participant mp ON m.meeting_id = mp.meeting_id
            JOIN "user" u ON mp.user_id = u.user_id
            LEFT JOIN department d_meeting ON m.department_id = d_meeting.department_id
            WHERE m.meeting_date = %s
            AND u.user_id IN ({format_strings})
            AND %s < m.end_time
            AND %s > m.start_time
        """
        conflict_params = [meeting_date, *participant_ids, start_time_24, end_time_24]
        conflicting_members = execute_query(conflict_query, conflict_params, fetch='all')

        if conflicting_members:
            msgs = [
                f"Member: {m['user_name']} (ID: {m['user_id']}), "
                f"Meeting Dept: {m['meeting_department_name']}, "
                f"Scheduled on: {m['meeting_date']} from {m['start_time']} to {m['end_time']}"
                for m in conflicting_members
            ]
            return render_template("create_schedule.html",
                                   members=all_users, departments=departments,
                                   error="Conflicts detected:\n" + "\n".join(msgs))

        # Insert meeting - need RETURNING id for PostgreSQL
        conn = get_db()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                INSERT INTO meeting
                (meeting_title, meeting_date, start_time, end_time, user_id, department_id, venue)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING meeting_id
            """, (title, meeting_date, start_time_24, end_time_24,
                  session["user_id"], department_id, venue))
            meeting_id = cur.fetchone()['meeting_id']

            for uid in participant_ids:
                cur.execute("INSERT INTO meeting_participant (user_id, meeting_id) VALUES (%s, %s)",
                            (uid, meeting_id))
            conn.commit()
        finally:
            conn.close()

        # Send email
        meeting_details = execute_query("""
            SELECT m.meeting_title, m.meeting_date, m.start_time, m.end_time, m.venue, d.department_name
            FROM meeting m
            JOIN department d ON m.department_id = d.department_id
            WHERE m.meeting_id = %s
        """, (meeting_id,), fetch='one')

        emails_rows = execute_query("""
            SELECT DISTINCT u.email
            FROM meeting_participant mp
            JOIN "user" u ON mp.user_id = u.user_id
            WHERE mp.meeting_id = %s AND u.email IS NOT NULL
        """, (meeting_id,), fetch='all')
        emails = [row['email'] for row in emails_rows]

        if emails and meeting_details:
            send_meeting_email(emails, 'created', {
                'title': meeting_details['meeting_title'],
                'date': meeting_details['meeting_date'],
                'start_time': meeting_details['start_time'],
                'end_time': meeting_details['end_time'],
                'venue': meeting_details['venue'],
                'dept_name': meeting_details['department_name']
            })

        success = "✅ Meeting scheduled successfully."

    return render_template("create_schedule.html",
                           members=all_users, departments=departments,
                           success=success, error=error)


# ---------------- RUN APP ----------------
if __name__ == "__main__":
    from apscheduler.schedulers.background import BackgroundScheduler

    def delete_past_meetings():
        try:
            execute_query(
                "DELETE FROM meeting WHERE meeting_date < CURRENT_DATE",
                commit=True, fetch=None
            )
            print(f"[{datetime.now()}] Old meetings deleted.")
        except Exception as e:
            print(f"Error deleting old meetings: {e}")

    scheduler = BackgroundScheduler()
    scheduler.add_job(delete_past_meetings, 'cron', hour=0, minute=0)
    scheduler.start()
    app.run(debug=True)
