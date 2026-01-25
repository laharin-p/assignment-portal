
from flask import Flask, render_template, request, redirect, session, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary, cloudinary.uploader
import os
from datetime import datetime, date
import hashlib
import requests

# ---------------- APP ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

# ---------------- DATABASE ----------------
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---------------- CLOUDINARY ----------------
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)

# ---------------- MODELS ----------------
class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    roll_no = db.Column(db.String(20), unique=True)
    branch = db.Column(db.String(20))
    year = db.Column(db.String(10))
    section = db.Column(db.String(10))
    phone = db.Column(db.String(15))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    year = db.Column(db.String(20))
    branch = db.Column(db.String(50))
    section = db.Column(db.String(20))
    due_date = db.Column(db.Date)
    file_url = db.Column(db.String(500))


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"))
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"))
    file_url = db.Column(db.String(500))
    file_hash = db.Column(db.String(64))
    submitted_on = db.Column(db.Date)
    plagiarism_score = db.Column(db.Float, default=0)

    assignment = db.relationship("Assignment")
    student = db.relationship("Student")


with app.app_context():
    db.create_all()

# ---------------- FILE VIEW ----------------
@app.route("/file")
def open_file():
    url = request.args.get("url")
    if not url:
        return "File not found", 404

    r = requests.get(url, stream=True)
    return Response(
        r.iter_content(1024),
        content_type=r.headers.get("Content-Type", "application/octet-stream"),
        headers={"Content-Disposition": "inline"}
    )

# ---------------- PLAGIARISM ----------------
def calculate_hash(file):
    file.stream.seek(0)
    content = file.stream.read()
    file.stream.seek(0)
    return hashlib.sha256(content).hexdigest()


def plagiarism_check(assignment_id, file_hash):
    existing = Submission.query.filter_by(
        assignment_id=assignment_id,
        file_hash=file_hash
    ).first()

    return 95.0 if existing else 5.0

# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("student_login"))

# ================= STUDENT =================

@app.route("/student/register", methods=["GET","POST"])
def student_register():

    if "student_id" in session:
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":

        exists = Student.query.filter(
            (Student.email == request.form["email"]) |
            (Student.roll_no == request.form["rollno"])
        ).first()

        if exists:
            flash("Student already exists","danger")
            return redirect(url_for("student_register"))

        student = Student(
            name=request.form["name"],
            roll_no=request.form["rollno"],
            branch=request.form["branch"],
            year=request.form["year"],
            section=request.form["section"],
            phone=request.form["phone"],
            email=request.form["email"],
            password=generate_password_hash(request.form["password"])
        )

        db.session.add(student)
        db.session.commit()

        session.clear()
        session["student_id"] = student.id
        session["student_name"] = student.name

        flash("Registered & logged in successfully","success")
        return redirect(url_for("student_dashboard"))

    return render_template("student_register.html")


@app.route("/student/login", methods=["GET","POST"])
def student_login():

    if "student_id" in session:
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":

        student = Student.query.filter_by(
            email=request.form["email"]
        ).first()

        if student and check_password_hash(
            student.password, request.form["password"]
        ):
            session.clear()
            session["student_id"] = student.id
            session["student_name"] = student.name
            return redirect(url_for("student_dashboard"))

        flash("Invalid credentials","danger")

    return render_template("student_login.html")


# ================= STUDENT DASHBOARD =================

@app.route("/student/dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    student = Student.query.get(session["student_id"])

    # Fetch assignments for the student's year, branch, section
    assignments = Assignment.query.filter_by(
        year=student.year,
        branch=student.branch,
        section=student.section
    ).all()

    # Fetch submissions by this student
    submissions = Submission.query.filter_by(student_id=student.id).all()
    submitted_map = {s.assignment_id: s for s in submissions}

    today = date.today()
    available_assignments = []
    submitted_assignments = []

    for a in assignments:
        days_left = (a.due_date - today).days

        if days_left < 0:
            color = "red"
            can_upload = False
        elif days_left <= 2:
            color = "orange"
            can_upload = True
        else:
            color = "green"
            can_upload = True

        if a.id in submitted_map:
            s = submitted_map[a.id]
            submitted_assignments.append({
                "assignment": a,
                "submitted_on": s.submitted_on,
                "file_url": s.file_url,
                "plagiarism_score": s.plagiarism_score or 0,  # prevent UndefinedError
                "days_left": days_left,
                "color": color
            })
        else:
            available_assignments.append({
                "assignment": a,
                "days_left": days_left,
                "color": color,
                "can_upload": can_upload
            })

    return render_template(
        "student_dashboard.html",
        student=student,
        available_assignments=available_assignments,
        submitted_assignments=submitted_assignments,
        current_date=today
    )


@app.route("/student/submit/<int:assignment_id>", methods=["POST"])
def submit_assignment(assignment_id):

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    assignment = Assignment.query.get_or_404(assignment_id)

    if assignment.due_date < date.today():
        flash("Deadline crossed","danger")
        return redirect(url_for("student_dashboard"))

    if Submission.query.filter_by(
        student_id=session["student_id"],
        assignment_id=assignment_id
    ).first():
        flash("Already submitted","warning")
        return redirect(url_for("student_dashboard"))

    file = request.files.get("file")

    if not file:
        flash("No file selected","danger")
        return redirect(url_for("student_dashboard"))

    file_hash = calculate_hash(file)
    score = plagiarism_check(assignment_id, file_hash)

    upload = cloudinary.uploader.upload(
        file,
        resource_type="raw",
        use_filename=True,
        unique_filename=True
    )

    submission = Submission(
        student_id=session["student_id"],
        assignment_id=assignment_id,
        file_url=upload["secure_url"],
        file_hash=file_hash,
        submitted_on=date.today(),
        plagiarism_score=score
    )

    db.session.add(submission)
    db.session.commit()

    flash("Submitted successfully","success")
    return redirect(url_for("student_dashboard"))


@app.route("/student/logout")
def student_logout():
    session.pop("student_id", None)
    session.pop("student_name", None)
    flash("Logged out successfully", "info")
    return redirect(url_for("student_login"))

# ================= TEACHER =================
@app.route("/teacher/register", methods=["GET","POST"])
def teacher_register():

    if "teacher_id" in session:
        return redirect(url_for("teacher_dashboard"))

    if request.method == "POST":

        if Teacher.query.filter_by(email=request.form["email"]).first():
            flash("Teacher already exists","danger")
            return redirect(url_for("teacher_register"))

        teacher = Teacher(
            name=request.form["name"],
            email=request.form["email"],
            password=generate_password_hash(request.form["password"])
        )

        db.session.add(teacher)
        db.session.commit()

        flash("Teacher registered","success")
        return redirect(url_for("teacher_login"))

    return render_template("teacher_register.html")


@app.route("/teacher/login", methods=["GET","POST"])
def teacher_login():

    if "teacher_id" in session:
        return redirect(url_for("teacher_dashboard"))

    if request.method == "POST":

        teacher = Teacher.query.filter_by(
            email=request.form["email"]
        ).first()

        if teacher and check_password_hash(
            teacher.password, request.form["password"]
        ):
            session.clear()
            session["teacher_id"] = teacher.id
            session["teacher_name"] = teacher.name
            return redirect(url_for("teacher_dashboard"))

        flash("Invalid credentials","danger")

    return render_template("teacher_login.html")


@app.route("/teacher/dashboard")
def teacher_dashboard():

    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    teacher = Teacher.query.get(session["teacher_id"])
    assignments = Assignment.query.all()
    students = Student.query.all()

    pending = {}

    for a in assignments:

        submitted_ids = [
            s.student_id for s in Submission.query.filter_by(
                assignment_id=a.id
            ).all()
        ]

        pending[a.id] = [
            s for s in students if s.id not in submitted_ids
        ]

    return render_template(
        "teacher_dashboard.html",
        teacher=teacher,
        assignments=assignments,
        pending=pending,
        current_date=date.today()
    )


@app.route("/teacher/upload", methods=["POST"])
def teacher_upload():

    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    file = request.files.get("file")

    if not file:
        flash("No file uploaded","danger")
        return redirect(url_for("teacher_dashboard"))

    upload = cloudinary.uploader.upload(
        file,
        resource_type="raw",
        use_filename=True,
        unique_filename=True
    )

    assignment = Assignment(
        title=request.form["title"],
        year=request.form["year"],
        branch=request.form["branch"],
        section=request.form["section"],
        due_date=datetime.strptime(
            request.form["due_date"], "%Y-%m-%d"
        ).date(),
        file_url=upload["secure_url"]
    )

    db.session.add(assignment)
    db.session.commit()

    flash("Assignment uploaded","success")
    return redirect(url_for("teacher_dashboard"))


@app.route("/teacher/submissions/<int:assignment_id>")
def teacher_submissions(assignment_id):

    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    assignment = Assignment.query.get_or_404(assignment_id)

    submissions = Submission.query.filter_by(
        assignment_id=assignment_id
    ).all()

    return render_template(
        "teacher_submissions.html",
        assignment=assignment,
        submissions=submissions,
        current_date=date.today()
    )


@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for("teacher_login"))


if __name__ == "__main__":
    app.run(debug=True)