
from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary, cloudinary.uploader
import os
from datetime import datetime, date
import hashlib

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
    plagiarism_score = db.Column(db.Float)
    marks = db.Column(db.Float)

    assignment = db.relationship("Assignment")
    student = db.relationship("Student")

# ---------------- CREATE TABLES ----------------
with app.app_context():
    db.create_all()

# ---------------- PLAGIARISM SYSTEM ----------------
def calculate_hash(file):
    file.seek(0)
    content = file.read()
    file.seek(0)
    return hashlib.sha256(content).hexdigest()

def plagiarism_check(assignment_id, file_hash):
    existing = Submission.query.filter_by(
        assignment_id=assignment_id,
        file_hash=file_hash
    ).first()

    if existing:
        return 95.0   # copied
    return 5.0        # safe

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return redirect(url_for("student_login"))

# ================= STUDENT =================
@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        if Student.query.filter(
            (Student.email == request.form["email"]) |
            (Student.roll_no == request.form["rollno"])
        ).first():
            return render_template("student_register.html", error="Roll number or Email already exists")

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

        session["student_id"] = student.id
        session["student_name"] = student.name
        return redirect(url_for("student_dashboard"))

    return render_template("student_register.html")

@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        student = Student.query.filter_by(email=request.form["email"]).first()
        if student and check_password_hash(student.password, request.form["password"]):
            session.clear()
            session["student_id"] = student.id
            session["student_name"] = student.name
            return redirect(url_for("student_dashboard"))

        flash("Invalid email or password", "danger")

    return render_template("student_login.html")

@app.route("/student/dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    return render_template(
        "student_dashboard.html",
        assignments=Assignment.query.all(),
        submissions=Submission.query.filter_by(student_id=session["student_id"]).all(),
        current_date=date.today()
    )

@app.route("/student/submit/<int:assignment_id>", methods=["POST"])
def submit_assignment(assignment_id):
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    file = request.files.get("file")
    if not file or file.filename == "":
        flash("No file selected", "danger")
        return redirect(url_for("student_dashboard"))

    if Submission.query.filter_by(
        student_id=session["student_id"],
        assignment_id=assignment_id
    ).first():
        flash("Assignment already submitted", "warning")
        return redirect(url_for("student_dashboard"))

    file_hash = calculate_hash(file)
    score = plagiarism_check(assignment_id, file_hash)

    upload = cloudinary.uploader.upload(file, resource_type="raw")

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

    flash(f"Assignment submitted | Plagiarism: {score}%", "success")
    return redirect(url_for("student_dashboard"))

@app.route("/student/logout")
def student_logout():
    session.clear()
    return redirect(url_for("student_login"))

# ================= TEACHER =================
@app.route("/teacher/register", methods=["GET", "POST"])
def teacher_register():
    if request.method == "POST":
        if Teacher.query.filter_by(email=request.form["email"]).first():
            flash("Teacher already exists", "danger")
            return redirect(url_for("teacher_login"))

        teacher = Teacher(
            name=request.form["name"],
            email=request.form["email"],
            password=generate_password_hash(request.form["password"])
        )
        db.session.add(teacher)
        db.session.commit()
        return redirect(url_for("teacher_login"))

    return render_template("teacher_register.html")

@app.route("/teacher/login", methods=["GET", "POST"])
def teacher_login():
    if request.method == "POST":
        teacher = Teacher.query.filter_by(email=request.form["email"]).first()
        if teacher and check_password_hash(teacher.password, request.form["password"]):
            session.clear()
            session["teacher_id"] = teacher.id
            return redirect(url_for("teacher_dashboard"))

        flash("Invalid credentials", "danger")

    return render_template("teacher_login.html")

@app.route("/teacher/dashboard")
def teacher_dashboard():
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    assignments = Assignment.query.all()
    students = Student.query.all()

    pending = {}
    submissions_map = {}

    for a in assignments:
        subs = Submission.query.filter_by(assignment_id=a.id).all()
        submitted_ids = [s.student_id for s in subs]

        pending[a.id] = [s for s in students if s.id not in submitted_ids]
        submissions_map[a.id] = subs

    return render_template(
        "teacher_dashboard.html",
        teacher=Teacher.query.get(session["teacher_id"]),
        assignments=assignments,
        pending=pending,
        submissions_map=submissions_map,
        current_date=date.today()
    )

@app.route("/teacher/submissions/<int:assignment_id>")
def teacher_submissions(assignment_id):
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    assignment = Assignment.query.get_or_404(assignment_id)
    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()

    return render_template(
        "teacher_submissions.html",
        assignment=assignment,
        submissions=submissions
    )

@app.route("/teacher/upload", methods=["POST"])
def teacher_upload():
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    file = request.files.get("file")
    if not file:
        flash("No file uploaded", "danger")
        return redirect(url_for("teacher_dashboard"))

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
    flash("Assignment uploaded successfully", "success")
    return redirect(url_for("teacher_dashboard"))

@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    return redirect(url_for("teacher_login"))

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)