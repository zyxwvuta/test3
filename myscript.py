import requests
import os
import sys
import psycopg2
import pytz
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
# not needed on the host
# load_dotenv('my.env')  # Ensure 'main.env' contains TOKEN and CHAT_ID

TOKEN = os.getenv('TOKEN')
CHAT_ID = os.getenv('CHAT')

MAX_REMIND_DAYS = 3  # Number of consecutive days to remind each event

local_tz = pytz.timezone('Etc/GMT-3')


def send_message(event_name):
    text = f"{event_name}"
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': text
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Error sending message for {event_name}: {e}")
        return False


def main():
    # Connect to the PostgreSQL database using the connection string
    conn = psycopg2.connect(os.getenv('DB_URL'))
    c = conn.cursor()

    # Fetch all events from the database
    c.execute('SELECT id, name, remind_days, reminder_time, time FROM events ORDER BY id')
    events = c.fetchall()

    # The rest of your code...
    local_tz = pytz.timezone('Etc/GMT-3')
    # Get the current time
    now = datetime.now(pytz.UTC).astimezone(local_tz)
    current_hour = now.hour
    current_minute = now.minute

    # Track if any reminder was sent in this cycle
    reminder_sent = False

    # Flag to track if all afternoon events have reached max remind days
    all_afternoon_reached_max = True

    # Process afternoon reminders first
    for event in events:
        event_id, event_name, remind_days, reminder_time, event_time = event

        # Split event_time into hour and minute
        event_hour, event_minute = map(int, event_time.split(':'))

        # Only proceed if it's time to send reminders
        if current_hour == event_hour and current_minute == event_minute:
            if reminder_time == "afternoon" and remind_days < MAX_REMIND_DAYS:
                success = send_message(event_name)
                if success:
                    # Increment the remind_days for the current event
                    c.execute('UPDATE events SET remind_days = remind_days + 1 WHERE id = %s', (event_id,))
                    print(f"Sent afternoon reminder for {event_name}. Day {remind_days + 1}/{MAX_REMIND_DAYS}")
                    reminder_sent = True
                    break

            elif reminder_time == "morning" and current_hour == event_hour and current_minute == event_minute: 
                success = send_message(event_name)
                if success:
                    # Increment the remind_days for the morning event
                    c.execute('UPDATE events SET remind_days = remind_days + 1 WHERE id = %s', (event_id,))
                    print(f"Sent morning reminder for {event_name}. Day {remind_days + 1}")
                    reminder_sent = True
                    break

        # Check if afternoon reminders have reached the max limit
        if reminder_time == "afternoon" and remind_days < MAX_REMIND_DAYS:
            all_afternoon_reached_max = False

    # If no afternoon reminders were sent and all afternoon events reached the max remind days
    if not reminder_sent and all_afternoon_reached_max:
        # Reset only afternoon reminders
        c.execute('UPDATE events SET remind_days = 0 WHERE reminder_time = %s', ("afternoon",))
        print("All afternoon events have been reminded the maximum times. Resetting counters for afternoon reminders.")
        # After reset, send the first reminder again
        c.execute('SELECT id, name FROM events WHERE reminder_time = %s ORDER BY id LIMIT 1', ("afternoon",))
        first_afternoon_event = c.fetchone()
        if first_afternoon_event:
            send_message(first_afternoon_event[1])
            c.execute('UPDATE events SET remind_days = remind_days + 1 WHERE id = %s', (first_afternoon_event[0],))
            print(f"Sent first afternoon reminder for {first_afternoon_event[1]} after reset.")

    # Commit changes and close the connection
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
