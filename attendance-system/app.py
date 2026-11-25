"""Student Attendance Management System - separate student and teacher portals."""
import csv
import io
import os
import random
import sqlite3
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "college.db")
THRESHOLD = 75                                   # minimum attendance % required
IST = timezone(timedelta(hours=5, minutes=30))   # edit window follows Indian time

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

STUDENT_PASSWORD = "student123"
TEACHER_PASSWORD = "teacher123"

SUBJECTS = ["Data Structures", "Algorithms", "Database Systems", "Operating Systems",
            "Computer Networks", "Software Engineering", "Web Technologies",
            "Machine Learning", "Discrete Mathematics", "Python Programming"]
TEACHERS = ["Dr. Ramesh Kumar", "Prof. Sunita Rao", "Dr. Anil Verma", "Prof. Kavitha Reddy",
            "Dr. Suresh Babu", "Prof. Meena Iyer", "Dr. Prakash Nair", "Prof. Lakshmi Devi",
            "Dr. Vikram Singh", "Prof. Anjali Gupta"]
STUDENTS = ["Aarav Sharma", "Ananya Reddy", "Rohan Gupta", "Priya Nair", "Karthik Rao",
            "Sneha Patel", "Arjun Mehta", "Divya Iyer", "Rahul Verma", "Ishita Singh",
            "Vivek Kumar", "Meghana Das", "Aditya Joshi", "Pooja Menon", "Sai Teja",
            "Neha Kapoor", "Harsha Vardhan", "Swathi Reddy", "Manoj Yadav", "Tanvi Desai"]


def today():
    return datetime.now(IST).date()


def pct(present, total):
    return round(100 * present / total, 1) if total else 0.0


# ---------- database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,          -- roll no (student) / employee id (teacher)
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('student','teacher')),
            name TEXT NOT NULL,
            class_name TEXT,                        -- students only
            subject_id INTEGER REFERENCES subjects(id)  -- teachers only
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('Present','Absent')),
            UNIQUE (student_id, subject_id, day)
        );
    """)
    if not db.execute("SELECT 1 FROM users").fetchone():
        seed(db)
    db.commit()
    db.close()


def seed(db):
    """10 teachers (one per subject), 20 students, and ~3 weeks of sample attendance."""
    rng = random.Random(42)
    t_hash = generate_password_hash(TEACHER_PASSWORD)
    s_hash = generate_password_hash(STUDENT_PASSWORD)
    subject_ids = []
    for name in SUBJECTS:
        subject_ids.append(db.execute("INSERT INTO subjects (name) VALUES (?)", (name,)).lastrowid)
    for i, (name, sid) in enumerate(zip(TEACHERS, subject_ids), start=1):
        db.execute("INSERT INTO users (username,password_hash,role,name,subject_id) VALUES (?,?,?,?,?)",
                   (f"T{i:02d}", t_hash, "teacher", name, sid))
    student_ids = []
    for i, name in enumerate(STUDENTS, start=1):
        cls = "CSE-A" if i <= 10 else "CSE-B"
        student_ids.append(db.execute(
            "INSERT INTO users (username,password_hash,role,name,class_name) VALUES (?,?,?,?,?)",
            (f"S{i:03d}", s_hash, "student", name, cls)).lastrowid)
    chance = {sid: (0.62 if idx in (3, 8, 14, 17) else rng.uniform(0.82, 0.97))
              for idx, sid in enumerate(student_ids)}
    days = [today() - timedelta(days=n) for n in range(1, 22)]
    days = [d for d in days if d.weekday() < 5]
    for sub in subject_ids:
        for d in days:
            if rng.random() > 0.65:          # not every subject meets every day
                continue
            for sid in student_ids:
                status = "Present" if rng.random() < chance[sid] else "Absent"
                db.execute("INSERT INTO attendance (student_id,subject_id,day,status) VALUES (?,?,?,?)",
                           (sid, sub, d.isoformat(), status))


# ---------- auth helpers ----------
def current_user():
    if "uid" not in session:
        return None
    if not hasattr(g, "user"):
        g.user = get_db().execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone()
    return g.user


@app.context_processor
def inject_user():
    return {"me": current_user(), "threshold": THRESHOLD}


def login_required(role=None):
    def deco(view):
        @wraps(view)
        def wrapped(*a, **kw):
            u = current_user()
            if not u:
                return redirect(url_for("login", role=role or "student"))
            if role and u["role"] != role:
                abort(403)
            return view(*a, **kw)
        return wrapped
    return deco


@app.errorhandler(403)
def forbidden(_e):
    return render_template("message.html", title="Access denied",
                           text="You don't have permission to view this page."), 403


@app.route("/")
def home():
    u = current_user()
    if u:
        return redirect(url_for("teacher_dashboard" if u["role"] == "teacher" else "student_home"))
    return render_template("home.html")


@app.route("/<role>/login", methods=["GET", "POST"])
def login(role):
    if role not in ("student", "teacher"):
        abort(404)
    if request.method == "POST":
        row = get_db().execute("SELECT * FROM users WHERE username=? AND role=?",
                               (request.form["username"].strip().upper(), role)).fetchone()
        if row and check_password_hash(row["password_hash"], request.form["password"]):
            session.clear()
            session["uid"] = row["id"]
            return redirect(url_for("home"))
        flash("Invalid ID or password.", "error")
    return render_template("login.html", role=role)


@app.route("/<role>/register", methods=["GET", "POST"])
def register(role):
    if role not in ("student", "teacher"):
        abort(404)
    db = get_db()
    if request.method == "POST":
        f = request.form
        name, uid = f["name"].strip(), f["username"].strip().upper()
        pw = f["password"]
        if not name or not uid:
            flash("Name and ID are required.", "error")
        elif len(pw) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif pw != f["confirm"]:
            flash("Passwords do not match.", "error")
        else:
            try:
                if role == "student":
                    cls = f["class_name"].strip().upper() or "CSE-A"
                    cur = db.execute("INSERT INTO users (username,password_hash,role,name,class_name) "
                                     "VALUES (?,?,?,?,?)", (uid, generate_password_hash(pw), role, name, cls))
                else:
                    subj = f["subject"].strip().title()
                    if not subj:
                        flash("Subject is required.", "error")
                        return render_template("register.html", role=role)
                    db.execute("INSERT OR IGNORE INTO subjects (name) VALUES (?)", (subj,))
                    sid = db.execute("SELECT id FROM subjects WHERE name=?", (subj,)).fetchone()[0]
                    cur = db.execute("INSERT INTO users (username,password_hash,role,name,subject_id) "
                                     "VALUES (?,?,?,?,?)", (uid, generate_password_hash(pw), role, name, sid))
                db.commit()
                session.clear()
                session["uid"] = cur.lastrowid
                flash("Registration successful. Welcome!", "ok")
                return redirect(url_for("home"))
            except sqlite3.IntegrityError:
                flash(f"ID {uid} is already registered.", "error")
    return render_template("register.html", role=role)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ---------- shared queries ----------
def subject_stats(student_id):
    rows = get_db().execute("""
        SELECT sub.id, sub.name,
               (SELECT group_concat(t.name, ', ') FROM users t WHERE t.subject_id=sub.id) AS teacher,
               COUNT(a.id) AS total,
               COALESCE(SUM(a.status='Present'), 0) AS present
        FROM subjects sub LEFT JOIN attendance a ON a.subject_id=sub.id AND a.student_id=?
        GROUP BY sub.id ORDER BY sub.name""", (student_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["percent"] = pct(d["present"], d["total"])
        out.append(d)
    return out


def get_student_or_403(sid):
    """A student may only open their own profile; any teacher may open any student's."""
    u = current_user()
    if u["role"] == "student" and u["id"] != sid:
        abort(403)
    s = get_db().execute("SELECT * FROM users WHERE id=? AND role='student'", (sid,)).fetchone()
    if not s:
        abort(404)
    return s


def classes():
    return [r[0] for r in get_db().execute(
        "SELECT DISTINCT class_name FROM users WHERE role='student' ORDER BY class_name")]


# ---------- student portal ----------
@app.route("/student/dashboard")
@login_required("student")
def student_home():
    return redirect(url_for("profile", sid=current_user()["id"]))


@app.route("/profile/<int:sid>")
@login_required()
def profile(sid):
    s = get_student_or_403(sid)
    stats = subject_stats(sid)
    total = sum(x["total"] for x in stats)
    present = sum(x["present"] for x in stats)
    return render_template("profile.html", s=s, stats=stats, overall=pct(present, total),
                           total=total, present=present)


@app.route("/profile/<int:sid>/subject/<int:sub_id>")
@login_required()
def profile_subject(sid, sub_id):
    s = get_student_or_403(sid)
    sub = get_db().execute("SELECT * FROM subjects WHERE id=?", (sub_id,)).fetchone() or abort(404)
    rows = get_db().execute("SELECT day, status FROM attendance WHERE student_id=? AND subject_id=? "
                            "ORDER BY day DESC", (sid, sub_id)).fetchall()
    present = sum(r["status"] == "Present" for r in rows)
    return render_template("subject_detail.html", s=s, sub=sub, rows=rows,
                           present=present, total=len(rows), percent=pct(present, len(rows)))


@app.route("/student/sheet.csv")
@login_required("student")
def student_sheet():
    u = current_user()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Student", u["name"], "Roll No", u["username"], "Class", u["class_name"]])
    w.writerow([])
    w.writerow(["Subject", "Teacher", "Classes Held", "Present", "Absent", "Percent"])
    for x in subject_stats(u["id"]):
        w.writerow([x["name"], x["teacher"] or "", x["total"], x["present"],
                    x["total"] - x["present"], x["percent"]])
    w.writerow([])
    w.writerow(["Date", "Subject", "Status"])
    for r in get_db().execute("""SELECT a.day, sub.name, a.status FROM attendance a
            JOIN subjects sub ON sub.id=a.subject_id WHERE a.student_id=?
            ORDER BY a.day DESC, sub.name""", (u["id"],)):
        w.writerow(list(r))
    return csv_response(buf, f"attendance_{u['username']}.csv")


# ---------- teacher portal ----------
def my_subject():
    return get_db().execute("SELECT * FROM subjects WHERE id=?", (current_user()["subject_id"],)).fetchone()


def subject_students(sub_id, cls=""):
    sql = """SELECT u.id, u.username, u.name, u.class_name,
                    COUNT(a.id) AS total, COALESCE(SUM(a.status='Present'),0) AS present
             FROM users u LEFT JOIN attendance a ON a.student_id=u.id AND a.subject_id=?
             WHERE u.role='student' {w} GROUP BY u.id ORDER BY u.class_name, u.username"""
    w, params = (("AND u.class_name=?", (sub_id, cls)) if cls else ("", (sub_id,)))
    out = []
    for r in get_db().execute(sql.format(w=w), params):
        d = dict(r)
        d["percent"] = pct(d["present"], d["total"])
        out.append(d)
    return out


@app.route("/teacher/dashboard")
@login_required("teacher")
def teacher_dashboard():
    sub = my_subject()
    rows = subject_students(sub["id"])
    sessions = get_db().execute("""SELECT day, SUM(status='Present') AS p, COUNT(*) AS n FROM attendance
            WHERE subject_id=? GROUP BY day ORDER BY day DESC LIMIT 10""", (sub["id"],)).fetchall()
    held = get_db().execute("SELECT COUNT(DISTINCT day) FROM attendance WHERE subject_id=?",
                            (sub["id"],)).fetchone()[0]
    marked_today = get_db().execute("SELECT COUNT(*) FROM attendance WHERE subject_id=? AND day=?",
                                    (sub["id"], today().isoformat())).fetchone()[0] > 0
    avg = round(sum(r["percent"] for r in rows) / len(rows), 1) if rows else 0
    return render_template("teacher_dashboard.html", sub=sub, rows=rows, sessions=sessions,
                           held=held, avg=avg, marked_today=marked_today,
                           low=[r for r in rows if r["total"] and r["percent"] < THRESHOLD],
                           today=today().isoformat())


@app.route("/teacher/students")
@login_required("teacher")
def teacher_students():
    cls = request.args.get("class_name", "")
    sub = my_subject()
    return render_template("teacher_students.html", sub=sub, rows=subject_students(sub["id"], cls),
                           classes=classes(), cls=cls)


@app.route("/teacher/attendance", methods=["GET", "POST"])
@login_required("teacher")
def teacher_attendance():
    db, sub = get_db(), my_subject()
    t = today().isoformat()
    day = request.values.get("day") or t
    try:
        date.fromisoformat(day)
    except ValueError:
        day = t
    cls_list = classes()
    cls = request.values.get("class_name") or (cls_list[0] if cls_list else "")
    editable = (day == t)       # today only: locks automatically after 11:59 PM

    if request.method == "POST":
        if not editable:
            flash("Attendance can only be edited on the same day, before 11:59 PM.", "error")
            return redirect(url_for("teacher_attendance", day=day, class_name=cls))
        for r in db.execute("SELECT id FROM users WHERE role='student' AND class_name=?", (cls,)).fetchall():
            status = "Present" if request.form.get(f"present_{r['id']}") else "Absent"
            db.execute("""INSERT INTO attendance (student_id,subject_id,day,status) VALUES (?,?,?,?)
                          ON CONFLICT(student_id,subject_id,day) DO UPDATE SET status=excluded.status""",
                       (r["id"], sub["id"], day, status))
        db.commit()
        flash(f"Attendance saved for {sub['name']} - {cls} - {day}.", "ok")
        return redirect(url_for("teacher_attendance", day=day, class_name=cls))

    rows = db.execute("""SELECT u.id, u.username, u.name, a.status FROM users u
            LEFT JOIN attendance a ON a.student_id=u.id AND a.subject_id=? AND a.day=?
            WHERE u.role='student' AND u.class_name=? ORDER BY u.username""",
                      (sub["id"], day, cls)).fetchall()
    return render_template("teacher_attendance.html", sub=sub, rows=rows, classes=cls_list,
                           cls=cls, day=day, editable=editable, today=t)


@app.route("/teacher/sheet.csv")
@login_required("teacher")
def teacher_sheet():
    cls = request.args.get("class_name", "")
    sub = my_subject()
    db = get_db()
    days = [r[0] for r in db.execute("SELECT DISTINCT day FROM attendance WHERE subject_id=? ORDER BY day",
                                     (sub["id"],))]
    marks = {(r["student_id"], r["day"]): r["status"] for r in db.execute(
        "SELECT student_id, day, status FROM attendance WHERE subject_id=?", (sub["id"],))}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Subject", sub["name"], "Teacher", current_user()["name"], "Class", cls or "All"])
    w.writerow([])
    w.writerow(["Roll No", "Name", "Class"] + days + ["Present", "Held", "Percent"])
    for s in subject_students(sub["id"], cls):
        w.writerow([s["username"], s["name"], s["class_name"]] +
                   [{"Present": "P", "Absent": "A"}.get(marks.get((s["id"], d)), "-") for d in days] +
                   [s["present"], s["total"], s["percent"]])
    return csv_response(buf, f"attendance_{sub['name'].replace(' ', '_')}.csv")


def csv_response(buf, filename):
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


init_db()

if __name__ == "__main__":
    app.run(debug=True)
