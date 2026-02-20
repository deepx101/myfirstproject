import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    user="aman",
    password="aman123",
    database="meeting_scheduler_db"
)

cursor = conn.cursor()
print("✅ Database connected successfully")


# -------------------------------------------------
# CHECK TIME CONFLICT
# -------------------------------------------------
def check_conflict(user_id, meeting_date, start_time, end_time):
    query = """
    SELECT 1
    FROM meeting
    WHERE user_id = %s
      AND meeting_date = %s
      AND (%s < end_time AND %s > start_time)
    """
    cursor.execute(query, (user_id, meeting_date, start_time, end_time))
    return cursor.fetchone() is not None


# -------------------------------------------------
# SCHEDULE MEETING
# -------------------------------------------------
def schedule_meeting(meeting_title, user_id, department_id,
                     meeting_date, start_time, end_time):

    if check_conflict(user_id, meeting_date, start_time, end_time):
        print("❌ Conflict detected for user")
        return

    insert_meeting = """
    INSERT INTO meeting
    (meeting_title, meeting_date, start_time, end_time, user_id, department_id)
    VALUES (%s, %s, %s, %s, %s, %s)
    """

    cursor.execute(insert_meeting, (
        meeting_title,
        meeting_date,
        start_time,
        end_time,
        user_id,
        department_id
    ))

    meeting_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO meeting_participant (meeting_id, user_id) VALUES (%s, %s)",
        (meeting_id, user_id)
    )

    conn.commit()
    print("✅ Meeting scheduled successfully")


# -------------------------------------------------
# TEST CASES
# -------------------------------------------------

print("\n--- TEST 1: First meeting (should succeed) ---")
schedule_meeting(
    "Project Discussion",
    1,          # user_id
    1,          # department_id
    "2026-01-25",
    "10:00:00",
    "11:00:00"
)

print("\n--- TEST 2: Overlapping meeting (should fail) ---")
schedule_meeting(
    "Faculty Review",
    1,
    1,
    "2026-01-25",
    "10:30:00",
    "11:30:00"
)

print("\n--- TEST 3: Same time, different date (should succeed) ---")
schedule_meeting(
    "Next Day Meeting",
    1,
    1,
    "2026-01-26",
    "10:00:00",
    "11:00:00"
)

print("\n--- TEST 4: Different user, same time (should succeed) ---")
schedule_meeting(
    "Other User Meeting",
    2,
    1,
    "2026-01-25",
    "10:30:00",
    "11:30:00"
)
