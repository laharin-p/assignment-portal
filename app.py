


from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import cloudinary, cloudinary.uploader
import os
from datetime import datetime, date

# ---------------- APP ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-secret")

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
    email = db.Column(db.String(100), unique=True)
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
    submitted_on = db.Column(db.Date)
    plagiarism_score = db.Column(db.Float)
    marks = db.Column(db.Float)   # 🔥 NEW (OUT OF 5)

    assignment = db.relationship("Assignment")
    student = db.relationship("Student")

# ---------------- CREATE TABLES ----------------
with app.app_context():
    db.create_all()

# ---------------- PLAGIARISM (DUMMY) ----------------
def fake_plagiarism_check(filename):
    return 12.5  # you can replace later with real logic


# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return redirect("/student/login")

# ================= STUDENT =================
@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        student = Student(
            name=request.form["name"],
            email=request.form["email"],
            password=generate_password_hash(request.form["password"])
        )
        db.session.add(student)
        db.session.commit()
        return redirect(url_for("student_login"))
    return render_template("student_register.html")


@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        s = Student.query.filter_by(email=request.form["email"]).first()
        if s and check_password_hash(s.password, request.form["password"]):
            session.clear()
            session["student_id"] = s.id
            return redirect("/student/dashboard")
        return render_template("student_login.html", error="Invalid login")
    return render_template("student_login.html")


@app.route("/student/dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    assignments = Assignment.query.all()
    submissions = Submission.query.filter_by(student_id=session["student_id"]).all()

    submission_map = {s.assignment_id: s for s in submissions}

    return render_template(
        "student_dashboard.html",
        assignments=assignments,
        submissions=submission_map,
        today=date.today()
    )



@app.route("/student/submit/<int:assignment_id>", methods=["POST"])
def submit_assignment(assignment_id):
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    assignment = Assignment.query.get_or_404(assignment_id)

    if date.today() > assignment.due_date:
        return "Deadline crossed", 403

    file = request.files["file"]
    upload = cloudinary.uploader.upload(file, resource_type="raw")

    submission = Submission(
        student_id=session["student_id"],
        assignment_id=assignment_id,
        file_url=upload["secure_url"],
        submitted_on=date.today(),
        plagiarism_score=fake_plagiarism_check(file.filename)
    )

    db.session.add(submission)
    db.session.commit()
    return redirect(url_for("student_dashboard"))


@app.route("/student/delete/<int:submission_id>", methods=["POST"])
def delete_submission(submission_id):
    submission = Submission.query.get_or_404(submission_id)

    if submission.student_id != session.get("student_id"):
        return "Unauthorized", 403

    if date.today() > submission.assignment.due_date:
        return "Deadline crossed", 403

    db.session.delete(submission)
    db.session.commit()
    return redirect(url_for("student_dashboard"))


@app.route("/student/logout")
def student_logout():
    session.clear()
    return redirect(url_for("student_login"))

# ================= TEACHER =================
@app.route("/teacher/login", methods=["GET", "POST"])
def teacher_login():
    if request.method == "POST":
        t = Teacher.query.filter_by(email=request.form["email"]).first()
        if t and check_password_hash(t.password, request.form["password"]):
            session.clear()
            session["teacher_id"] = t.id
            return redirect("/teacher/dashboard")
    return render_template("teacher_login.html")


@app.route("/teacher/dashboard")
def teacher_dashboard():
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    assignments = Assignment.query.all()
    students = Student.query.all()

    pending = {}
    for a in assignments:
        submitted_ids = [
            s.student_id for s in Submission.query.filter_by(assignment_id=a.id)
        ]
        pending[a.id] = [s for s in students if s.id not in submitted_ids]

    return render_template(
        "teacher_dashboard.html",
        assignments=assignments,
        pending=pending,
        today=date.today()
    )




@app.route("/teacher/upload", methods=["POST"])
def teacher_upload():
    file = request.files["file"]
    upload = cloudinary.uploader.upload(file, resource_type="raw")

    assignment = Assignment(
        title=request.form["title"],
        year=request.form["year"],
        branch=request.form["branch"],
        section=request.form["section"],
        due_date=datetime.strptime(request.form["due_date"], "%Y-%m-%d").date(),
        file_url=upload["secure_url"]
    )

    db.session.add(assignment)
    db.session.commit()
    return redirect(url_for("teacher_dashboard"))
@app.route("/teacher/submissions/<int:assignment_id>", methods=["GET", "POST"])
def teacher_submissions(assignment_id):
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    assignment = Assignment.query.get_or_404(assignment_id)

    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()

    # Handle marks submission
    if request.method == "POST":
        submission_id = request.form["submission_id"]
        marks = float(request.form["marks"])

        if marks > 5:
            return "Marks cannot exceed 5", 400

        sub = Submission.query.get(submission_id)
        sub.marks = marks
        db.session.commit()
        return redirect(request.url)

    return render_template(
        "teacher_submissions.html",
        assignment=assignment,
        submissions=submissions
    )



@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    return redirect(url_for("teacher_login"))
