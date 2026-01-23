
from datetime import datetime, date
from flask import (
    Flask, render_template, request, redirect,
    session, url_for, abort
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary
import cloudinary.uploader
import os

# ---------------- APP SETUP ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")

# ---------------- DATABASE ----------------
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---------------- CLOUDINARY ----------------
cloudinary.config(
    cloud_name=os.environ.get("CLOUD_NAME"),
    api_key=os.environ.get("API_KEY"),
    api_secret=os.environ.get("API_SECRET")
)

# ---------------- MODELS ----------------
class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    rollno = db.Column(db.String(50), unique=True, nullable=False)
    branch = db.Column(db.String(20), nullable=False)
    year = db.Column(db.String(10), nullable=False)
    section = db.Column(db.String(10), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    file_url = db.Column(db.Text)
    branch = db.Column(db.String(50))
    year = db.Column(db.String(10))
    section = db.Column(db.String(10))
    due_date = db.Column(db.String(20))


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"))
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"))
    year = db.Column(db.String(10))
    branch = db.Column(db.String(20))
    section = db.Column(db.String(10))
    file_url = db.Column(db.Text)
    plagiarism = db.Column(db.Float, default=0)
    marks = db.Column(db.Integer)

    student = db.relationship("Student", backref="submissions")

# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("student_login"))

# ================= STUDENT =================
@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        name = request.form.get("name")
        rollno = request.form.get("rollno")
        branch = request.form.get("branch")
        year = request.form.get("year")
        section = request.form.get("section")
        phone = request.form.get("phone")
        email = request.form.get("email")
        password = request.form.get("password")

        if not all([name, rollno, branch, year, section, phone, email, password]):
            return render_template("student_register.html", error="All fields are required")

        if Student.query.filter_by(email=email).first():
            return render_template("student_register.html", error="Email already registered")

        if Student.query.filter_by(rollno=rollno).first():
            return render_template("student_register.html", error="Roll number already exists")

        hashed_password = generate_password_hash(password)

        student = Student(
            name=name,
            rollno=rollno,
            branch=branch,
            year=year,
            section=section,
            phone=phone,
            email=email,
            password=hashed_password
        )

        db.session.add(student)
        db.session.commit()

        return redirect("/student/login")

    return render_template("student_register.html")



@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            return "Invalid form data", 400

        student = Student.query.filter_by(email=email).first()

        if student and check_password_hash(student.password, password):
            session["student_id"] = student.id
            return redirect("/student/dashboard")

        return "Invalid email or password", 400

    return render_template("student_login.html")



@app.route("/student/dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    student = Student.query.get(session["student_id"])

    assignments = Assignment.query.filter_by(
        year=student.year,
        branch=student.branch,
        section=student.section
    ).all()

    submissions = Submission.query.filter_by(student_id=student.id).all()

    return render_template(
        "student_dashboard.html",
        assignments=assignments,
        submissions=submissions,
        today=date.today(),
        datetime=datetime
    )


@app.route("/student/submit/<int:assignment_id>", methods=["POST"])
def student_submit(assignment_id):
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    if "file" not in request.files:
        abort(400)

    file = request.files["file"]
    if file.filename == "":
        abort(400)

    student = Student.query.get_or_404(session["student_id"])

    result = cloudinary.uploader.upload(
        file,
        folder="submissions",
        resource_type="raw"
    )

    sub = Submission(
        student_id=student.id,
        assignment_id=assignment_id,
        year=student.year,
        branch=student.branch,
        section=student.section,
        file_url=result["secure_url"]
    )

    db.session.add(sub)
    db.session.commit()

    return redirect(url_for("student_dashboard"))


@app.route("/student/logout")
def student_logout():
    session.clear()
    return redirect(url_for("student_login"))

# ================= TEACHER =================
@app.route("/teacher/register", methods=["GET", "POST"])
def teacher_register():
    if request.method == "POST":
        t = Teacher(
            name=request.form["name"],
            email=request.form["email"],
            password=generate_password_hash(request.form["password"])
        )
        db.session.add(t)
        db.session.commit()
        return redirect(url_for("teacher_login"))

    return render_template("teacher_register.html")


@app.route("/teacher/login", methods=["GET", "POST"])
def teacher_login():
    if request.method == "POST":
        t = Teacher.query.filter_by(email=request.form["email"]).first()
        if t and check_password_hash(t.password, request.form["password"]):
            session.clear()
            session["teacher_id"] = t.id
            return redirect(url_for("teacher_dashboard"))

        return render_template("teacher_login.html", error="Invalid credentials")

    return render_template("teacher_login.html")


@app.route("/teacher/dashboard")
def teacher_dashboard():
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    assignments = Assignment.query.all()
    return render_template("teacher_dashboard.html", assignments=assignments)


@app.route("/teacher/upload", methods=["POST"])
def teacher_upload():
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    if "file" not in request.files:
        abort(400)

    file = request.files["file"]

    result = cloudinary.uploader.upload(
        file,
        folder="assignments",
        resource_type="raw"
    )

    a = Assignment(
        title=request.form["title"],
        file_url=result["secure_url"],
        year=request.form["year"],
        branch=request.form["branch"],
        section=request.form["section"],
        due_date=request.form["due_date"]
    )

    db.session.add(a)
    db.session.commit()

    return redirect(url_for("teacher_dashboard"))


@app.route("/teacher/submissions/<int:assignment_id>", methods=["GET", "POST"])
def teacher_submissions(assignment_id):
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    if request.method == "POST":
        sub = Submission.query.get(request.form["submission_id"])
        sub.marks = int(request.form["marks"])
        db.session.commit()

    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()
    assignment = Assignment.query.get(assignment_id)

    return render_template(
        "teacher_submissions.html",
        submissions=submissions,
        assignment=assignment
    )


@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    return redirect(url_for("teacher_login"))

# ---------------- START ----------------
with app.app_context():
    db.create_all()
    print("✅ DATABASE READY")
