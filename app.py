
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
import docx
import os
import uuid

# ---------------- APP SETUP ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# ---------------- DATABASE ----------------
# ---------------- DATABASE ----------------
database_url = os.environ.get("DATABASE_URL")

if not database_url:
    raise Exception("DATABASE_URL is missing. Set it in Render Environment Variables.")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)



# ---------------- FOLDERS ----------------
UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")
SUBMISSION_FOLDER = os.path.join(app.root_path, "submissions")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SUBMISSION_FOLDER, exist_ok=True)

# ---------------- MODELS ----------------
class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    rollno = db.Column(db.String(20), unique=True)
    branch = db.Column(db.String(50))
    year = db.Column(db.String(10))
    section = db.Column(db.String(10))
    phone = db.Column(db.String(15))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    filename = db.Column(db.String(200))
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
    filename = db.Column(db.String(200))
    plagiarism = db.Column(db.Float)
    marks = db.Column(db.Integer)

    student = db.relationship("Student", backref="submissions")

# ---------------- PLAGIARISM ----------------
def extract_text(path):
    if path.endswith(".txt"):
        return open(path, "r", errors="ignore").read()

    if path.endswith(".pdf"):
        reader = PdfReader(path)
        return " ".join(page.extract_text() or "" for page in reader.pages)

    if path.endswith(".docx"):
        doc = docx.Document(path)
        return " ".join(p.text for p in doc.paragraphs)

    return ""


def plagiarism_percent(t1, t2):
    s1 = set(t1.lower().split())
    s2 = set(t2.lower().split())
    if not s1 or not s2:
        return 0
    return round(len(s1 & s2) / len(s1 | s2) * 100, 2)


def check_plagiarism(new_file, student, assignment_id):
    new_text = extract_text(new_file)
    subs = Submission.query.filter_by(
        assignment_id=assignment_id,
        year=student.year,
        branch=student.branch,
        section=student.section
    ).all()

    max_score = 0
    for s in subs:
        old_path = os.path.join(SUBMISSION_FOLDER, s.filename)
        if os.path.exists(old_path):
            old_text = extract_text(old_path)
            max_score = max(max_score, plagiarism_percent(new_text, old_text))

    return max_score

# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("student_login"))

# ---------------- STUDENT ----------------
@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        if Student.query.filter_by(email=request.form["email"]).first():
            return render_template(
                "student_register.html",
                error="Email already registered. Please login."
            )

        s = Student(
            name=request.form["name"],
            rollno=request.form["rollno"],
            branch=request.form["branch"],
            year=request.form["year"],
            section=request.form["section"],
            phone=request.form["phone"],
            email=request.form["email"],
            password=generate_password_hash(request.form["password"])
        )
        db.session.add(s)
        db.session.commit()
        return redirect(url_for("student_login"))

    return render_template("student_register.html")


@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        print("FORM DATA:", request.form)

        student = Student.query.filter_by(email=request.form["email"]).first()
        print("STUDENT FOUND:", student)

        if student and check_password_hash(student.password, request.form["password"]):
            session["student_id"] = student.id
            return redirect(url_for("student_dashboard"))

        return render_template(
            "student_login.html",
            error="Invalid email or password"
        )

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
        student=student,
        assignments=assignments,
        submissions=submissions,
        today=datetime.today(),
        datetime=datetime
    )


@app.route("/student/submit/<int:assignment_id>", methods=["POST"])
def student_submit(assignment_id):
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    file = request.files.get("file")
    if not file or file.filename == "":
        return "No file selected"

    student = Student.query.get(session["student_id"])
    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    path = os.path.join(SUBMISSION_FOLDER, filename)
    file.save(path)

    plagiarism = check_plagiarism(path, student, assignment_id)

    sub = Submission(
        student_id=student.id,
        assignment_id=assignment_id,
        year=student.year,
        branch=student.branch,
        section=student.section,
        filename=filename,
        plagiarism=plagiarism
    )
    db.session.add(sub)
    db.session.commit()

    return redirect(url_for("student_dashboard"))
@app.route("/student/logout")
def student_logout():
    session.pop("student_id", None)
    return redirect(url_for("student_login"))


# ---------------- TEACHER ----------------
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
            session["teacher_id"] = t.id
            return redirect(url_for("teacher_dashboard"))
    return render_template("teacher_login.html")


@app.route("/teacher/dashboard")
def teacher_dashboard():
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    teacher = Teacher.query.get(session["teacher_id"])
    assignments = Assignment.query.all()
    return render_template("teacher_dashboard.html", teacher=teacher, assignments=assignments)


@app.route("/teacher/upload", methods=["POST"])
def teacher_upload():
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    file = request.files["file"]
    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    a = Assignment(
        title=request.form["title"],
        filename=filename,
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


@app.route("/teacher/pending/<int:assignment_id>")
def teacher_pending(assignment_id):
    assignment = Assignment.query.get(assignment_id)

    all_students = Student.query.filter_by(
        year=assignment.year,
        branch=assignment.branch,
        section=assignment.section
    ).all()

    submitted_ids = [s.student_id for s in Submission.query.filter_by(assignment_id=assignment_id).all()]
    pending = [s for s in all_students if s.id not in submitted_ids]

    return render_template("teacher_pending.html", students=pending, assignment=assignment)

# ---------------- DOWNLOAD ----------------
@app.route("/download/assignment/<filename>")
def download_assignment(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route("/download/submission/<path:filename>", endpoint="download_submission")
def download_submission(filename):
    if "student_id" not in session and "teacher_id" not in session:
        abort(403)

    file_path = os.path.join(SUBMISSION_FOLDER, filename)

    if not os.path.exists(file_path):
        abort(404)

    return send_from_directory(
        SUBMISSION_FOLDER,
        filename,
        as_attachment=True
    )


# ---------------- RUN ----------------
with app.app_context():
    db.create_all()
    print("✅ DATABASE READY")
