    from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

def delete_past_meetings():
    try:
        cursor.execute("DELETE FROM meeting WHERE meeting_date < CURDATE()")
        conn.commit()
        print(f"[{datetime.now()}] Old meetings deleted.")
    except Exception as e:
        print(f"Error deleting old meetings: {e}")

# Initialize scheduler
scheduler = BackgroundScheduler()
# Schedule to run daily at midnight
scheduler.add_job(delete_past_meetings, 'cron', hour=0, minute=0)
scheduler.start()