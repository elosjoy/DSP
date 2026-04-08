import sqlite3
import random
from datetime import date, timedelta

DB = "habit.db"
TARGET_EMAIL = "demouwe@gmail.com"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

user = conn.execute(
    "SELECT id, email FROM users WHERE LOWER(email)=?",
    (TARGET_EMAIL.lower(),)
).fetchone()

if not user:
    print("User not found:", TARGET_EMAIL)
    print("Make sure the account exists in the app first.")
    exit()

user_id = user["id"]
print("Generating data for:", user["email"])

habits = conn.execute(
    "SELECT id FROM habits WHERE user_id=?",
    (user_id,)
).fetchall()

habit_ids = [h["id"] for h in habits]

if not habit_ids:
    print("No habits found. Log in once so default habits are created.")
    exit()

for i in range(14):

    d = (date.today() + timedelta(days=i)).isoformat()

    habit_score = random.randint(0, len(habit_ids))

    if habit_score >= 2:
        screen_minutes = random.randint(60,150)
        valence = random.randint(1,2)
        energy = random.randint(0,2)

    elif habit_score == 1:
        screen_minutes = random.randint(120,240)
        valence = random.randint(0,1)
        energy = random.randint(-1,1)

    else:
        screen_minutes = random.randint(240,420)
        valence = random.randint(-2,0)
        energy = random.randint(-2,0)

    conn.execute(
        """
        INSERT OR REPLACE INTO affect_entries
        (user_id,entry_date,valence,energy)
        VALUES (?,?,?,?)
        """,
        (user_id,d,valence,energy)
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO screen_time_entries
        (user_id,entry_date,minutes)
        VALUES (?,?,?)
        """,
        (user_id,d,screen_minutes)
    )

    done_habits = random.sample(habit_ids, habit_score)

    for hid in habit_ids:

        done = 1 if hid in done_habits else 0

        conn.execute(
            """
            INSERT OR REPLACE INTO habit_logs
            (user_id,habit_id,entry_date,done)
            VALUES (?,?,?,?)
            """,
            (user_id,hid,d,done)
        )

conn.commit()
conn.close()

print("Test data successfully created for", TARGET_EMAIL)