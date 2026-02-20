from flask import Flask, render_template, request
import mysql.connector

app = Flask(__name__)

# Database connection
conn = mysql.connector.connect(
    host="localhost",
    user="aman",
    password="aman123",
    database="meeting_scheduler_db"
)
cursor = conn.cursor()

def check_conflict(user_id, meeting_date, start_time, end_time):
    query = """
    SELECT 1
    FROM meeting m
    JOIN meeting_participant mp
        ON m.meeting_id = mp.meeting_id
    WHERE mp.user_id = %s
      AND m.meeting_date = %s
      AND (%s < m.end_time AND %s > m.start_time)
    """
    cursor.execute(query, (user_id, meeting_date, start_time, end_time))
    return cursor.fetchone() is not None

@app.route("/", methods=["GET", "POST"])
def index():
    message = ""

    if request.method == "POST":
        user_id = request.form["user_id"]
        meeting_date = request.form["meeting_date"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]

        if check_conflict(user_id, meeting_date, start_time, end_time):
            message = "❌ Member is busy at this time."
        else:
            cursor.execute(
                "INSERT INTO meeting (meeting_date, start_time, end_time) VALUES (%s, %s, %s)",
                (meeting_date, start_time, end_time)
            )
            meeting_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO meeting_participant (meeting_id, user_id) VALUES (%s, %s)",
                (meeting_id, user_id)
            )

            conn.commit()
            message = "✅ Meeting scheduled successfully."

    return render_template("index.html", message=message)

if __name__ == "__main__":
    app.run(debug=True)
