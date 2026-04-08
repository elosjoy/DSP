from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "change-this-to-a-random-secret"
DB_PATH = "habit.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS affect_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        entry_date TEXT,
        valence INTEGER,
        energy INTEGER,
        UNIQUE(user_id, entry_date)
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS screen_time_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        entry_date TEXT,
        minutes INTEGER,
        UNIQUE(user_id, entry_date)
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        is_active INTEGER DEFAULT 1
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS habit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        habit_id INTEGER,
        entry_date TEXT,
        done INTEGER
    );
    """)

    conn.commit()
    conn.close()


def require_login():
    return session.get("user_id") is not None


def last_n_dates(n):
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def pearson_corr(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 2:
        return None

    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    mx = sum(xs) / n
    my = sum(ys) / n

    num = sum((x - mx) * (y - my) for x, y in pairs)
    denx = sum((x - mx) ** 2 for x in xs) ** 0.5
    deny = sum((y - my) ** 2 for y in ys) ** 0.5

    if denx == 0 or deny == 0:
        return None

    return round(num / (denx * deny), 3)


# helper labels used in multiple views

def label_valence(v):
    return { -2: 'Very unpleasant', -1: 'Unpleasant', 0: 'Neutral',
             1: 'Pleasant', 2: 'Very pleasant' }.get(v, '')


def label_energy(e):
    return { -2: 'Very low', -1: 'Low', 0: 'Moderate',
             1: 'High', 2: 'Very high' }.get(e, '')

@app.route("/screen-time", methods=["GET", "POST"])
def screen_time():
    if not require_login():
        return redirect(url_for("login"))

    user = session["user_id"]
    entry_date = request.args.get("date") or date.today().isoformat()

    if request.method == "POST":
        raw_hours = request.form.get("hours", "").strip()

        try:
            hours = float(raw_hours)
        except ValueError:
            hours = -1

        if hours < 0 or hours > 24:
            flash("Enter screen time in hours between 0 and 24.")
            return redirect(url_for("screen_time", date=entry_date))

        minutes = int(hours * 60)

        conn = get_db()
        conn.execute("""
            INSERT INTO screen_time_entries (user_id, entry_date, minutes)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, entry_date)
            DO UPDATE SET minutes=excluded.minutes
        """, (user, entry_date, minutes))
        conn.commit()
        conn.close()

        flash(f"Screen time saved for {entry_date}.")
        return redirect(url_for("screen_time", date=entry_date))

    conn = get_db()
    row = conn.execute("""
        SELECT minutes
        FROM screen_time_entries
        WHERE user_id=? AND entry_date=?
    """, (user, entry_date)).fetchone()
    conn.close()

    hours = ""
    if row:
        hours = row["minutes"] / 60

    return render_template("screen_time.html", entry_date=entry_date, hours=hours)

@app.route("/")
def home():
    if require_login():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        try:
            conn = get_db()
            conn.execute("INSERT INTO users (email,password_hash) VALUES (?,?)",
                         (email, password))
            conn.commit()
            conn.close()
        except:
            flash("Email already exists")
            return redirect(url_for("register"))

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?",
                            (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

        flash("Invalid login")

    return render_template("login.html")


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if not require_login():
        return redirect(url_for("login"))

    user = session["user_id"]
    today = date.today().isoformat()

    if request.method == "POST":
        # the template uses a hidden field called `form_type` to indicate
        # which section the user submitted. previously the view looked for
        # `form` and the habits form even pointed at a different endpoint
        # that didn’t exist, causing a BuildError on render. unify everything
        # to `form_type` and handle the three cases here.
        ftype = request.form.get("form_type")

        if ftype == "affect":
            valence = int(request.form["valence"])
            energy = int(request.form["energy"])

            conn = get_db()
            conn.execute("""
            INSERT INTO affect_entries (user_id,entry_date,valence,energy)
            VALUES (?,?,?,?)
            ON CONFLICT(user_id,entry_date)
            DO UPDATE SET valence=excluded.valence,energy=excluded.energy
            """, (user, today, valence, energy))
            conn.commit()
            conn.close()

        elif ftype == "screen":
            hours = float(request.form["hours"])
            minutes = int(hours * 60)

            conn = get_db()
            conn.execute("""
            INSERT INTO screen_time_entries (user_id,entry_date,minutes)
            VALUES (?,?,?)
            ON CONFLICT(user_id,entry_date)
            DO UPDATE SET minutes=excluded.minutes
            """, (user, today, minutes))
            conn.commit()
            conn.close()

        elif ftype == "habits":
            conn = get_db()
            habits = conn.execute(
                "SELECT * FROM habits WHERE user_id=? AND is_active=1",
                (user,)
            ).fetchall()

            for h in habits:
                done = 1 if request.form.get(f"h{h['id']}") else 0
                conn.execute("""
                INSERT INTO habit_logs (user_id,habit_id,entry_date,done)
                VALUES (?,?,?,?)
                """, (user, h["id"], today, done))

            conn.commit()
            conn.close()

    conn = get_db()

    # active habits list used for both today and management links
    habits = conn.execute("""
    SELECT * FROM habits
    WHERE user_id=? AND is_active=1
    """, (user,)).fetchall()

    # today's affect entry
    row = conn.execute(
        "SELECT valence,energy FROM affect_entries WHERE user_id=? AND entry_date=?",
        (user, today)).fetchone()
    today_valence = row["valence"] if row else None
    today_energy = row["energy"] if row else None

    # today's screen time
    row = conn.execute(
        "SELECT minutes FROM screen_time_entries WHERE user_id=? AND entry_date=?",
        (user, today)).fetchone()
    today_screen_hours = row["minutes"]/60 if row else ""

    # recent screen time entries (last 5)
    recent_screen = conn.execute(
        "SELECT entry_date as date, minutes/60.0 as hours"
        " FROM screen_time_entries WHERE user_id=? ORDER BY entry_date DESC LIMIT 5",
        (user,)).fetchall()

    # habits status for today (match existing logs)
    habits_today = []
    for h in habits:
        log = conn.execute(
            "SELECT done FROM habit_logs WHERE user_id=? AND habit_id=? AND entry_date=?",
            (user, h["id"], today)).fetchone()
        habits_today.append({
            "id": h["id"],
            "name": h["name"],
            "done": bool(log["done"]) if log else False
        })

    # recent affect entries and averages
    recent = []
    affects = conn.execute(
        "SELECT entry_date as date, valence, energy FROM affect_entries "
        "WHERE user_id=? ORDER BY entry_date DESC LIMIT 7",
        (user,)).fetchall()
    for r in affects:
        recent.append({
            "date": r["date"],
            "valence": r["valence"],
            "energy": r["energy"],
            "valence_label": label_valence(r["valence"]),
            "energy_label": label_energy(r["energy"])
        })

    all_affects = conn.execute(
        "SELECT valence,energy FROM affect_entries WHERE user_id=?",
        (user,)).fetchall()
    if all_affects:
        avg_valence = sum(a["valence"] for a in all_affects) / len(all_affects)
        avg_energy = sum(a["energy"] for a in all_affects) / len(all_affects)
    else:
        avg_valence = avg_energy = None

    conn.close()

    return render_template(
        "dashboard.html",
        habits=habits,
        today=today,
        today_valence=today_valence,
        today_energy=today_energy,
        today_screen_hours=today_screen_hours,
        recent_screen=recent_screen,
        habits_today=habits_today,
        recent=recent,
        avg_valence=avg_valence,
        avg_energy=avg_energy,
    )


@app.route("/habits", methods=["GET","POST"])
def habits_manage():
    # page used by dashboard link for adding/toggling habits
    if not require_login():
        return redirect(url_for("login"))

    user = session["user_id"]
    conn = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name = request.form.get("name", "").strip()
            if name:
                conn.execute(
                    "INSERT INTO habits (user_id,name) VALUES (?,?)",
                    (user, name)
                )
        elif action == "toggle":
            habit_id = request.form.get("habit_id")
            is_active = int(request.form.get("is_active", "0"))
            conn.execute(
                "UPDATE habits SET is_active=? WHERE id=? AND user_id=?",
                (is_active, habit_id, user)
            )
        conn.commit()

    habits_list = conn.execute(
        "SELECT * FROM habits WHERE user_id=?",
        (user,)
    ).fetchall()
    conn.close()
    return render_template("habits.html", habits=habits_list)


@app.route("/analytics")
def analytics():

    if not require_login():
        return redirect(url_for("login"))

    user = session["user_id"]
    dates = last_n_dates(14)

    conn = get_db()

    affect = conn.execute("""
    SELECT entry_date,valence,energy
    FROM affect_entries
    WHERE user_id=? AND entry_date>=?
    """, (user, dates[0])).fetchall()

    affect_map = {a["entry_date"]: a for a in affect}

    valence = [affect_map[d]["valence"] if d in affect_map else None for d in dates]
    energy = [affect_map[d]["energy"] if d in affect_map else None for d in dates]

    screen = conn.execute("""
    SELECT entry_date,minutes
    FROM screen_time_entries
    WHERE user_id=? AND entry_date>=?
    """, (user, dates[0])).fetchall()

    screen_map = {s["entry_date"]: s["minutes"]/60 for s in screen}

    screen_hours = [screen_map[d] if d in screen_map else None for d in dates]

    habit_score = []

    for d in dates:
        c = conn.execute("""
        SELECT COUNT(*) as c
        FROM habit_logs
        WHERE user_id=? AND entry_date=? AND done=1
        """, (user, d)).fetchone()["c"]
        habit_score.append(c)

    conn.close()

    # no correlations or scatter data; only time series remain
    scatter_screen = []
    scatter_habits = []

    return render_template(
        "analytics.html",
        labels=dates,
        valence=valence,
        energy=energy,
        screen_hours=screen_hours,
        habit_score=habit_score,
        scatter_screen=scatter_screen,
        scatter_habits=scatter_habits
    )


@app.route("/history")
def history():

    if not require_login():
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db()

    rows = conn.execute("""
        SELECT
            a.entry_date,
            a.valence,
            a.energy,
            s.minutes
        FROM affect_entries a
        LEFT JOIN screen_time_entries s
        ON a.user_id = s.user_id AND a.entry_date = s.entry_date
        WHERE a.user_id=?
        ORDER BY a.entry_date DESC
        LIMIT 30
    """, (user_id,)).fetchall()

    conn.close()

    entries = []

    for r in rows:

        hours = None
        if r["minutes"] is not None:
            hours = round(r["minutes"] / 60, 2)

        entries.append({
            "date": r["entry_date"],
            "valence": r["valence"],
            "energy": r["energy"],
            "valence_label": label_valence(r["valence"]),
            "energy_label": label_energy(r["energy"]),
            "screen_hours": hours
        })

    return render_template("history.html", entries=entries)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    # only create database on first run
    import os
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(debug=True)