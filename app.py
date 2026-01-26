
from flask import Flask, render_template, request, redirect, session, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary, cloudinary.uploader
import os
from datetime import datetime, date
import tempfile
import requests

# ---------------- APP ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

# ---------------- DATABASE ----------------
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# Fix Render postgres URL
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

# ---------------- FILE PROXY (for mobile + download) ----------------
@app.route("/direct_file")
def direct_file():
    file_url = request.args.get("file_url")
    if not file_url:
        return "File not found", 404

    r = requests.get(file_url, stream=True)
    if r.status_code != 200:
        return "File not accessible", 404

    tmp = tempfile.NamedTemporaryFile(delete=False)
    for chunk in r.iter_content(8192):
        if chunk:
            tmp.write(chunk)

    tmp.flush()

    return send_file(
        tmp.name,
        as_attachment=True,
        download_name=file_url.split("/")[-1]
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
    submitted_on = db.Column(db.DateTime)
    plagiarism_score = db.Column(db.Float, default=0)
    marks = db.Column(db.Float)

    assignment = db.relationship("Assignment")
    student = db.relationship("Student")


# ---------------- CREATE TABLES ----------------
with app.app_context():
    db.create_all()


# ---------------- DUMMY PLAGIARISM ----------------
def fake_plagiarism_check(filename):
    return round(5 + (hash(filename) % 60), 2)


# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("student_login"))


# ================= STUDENT =================

@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":

        if Student.query.filter_by(email=request.form["email"]).first():
            flash("Email already registered!", "danger")
            return render_template("student/register.html")

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

        flash("Registration successful! Please login.", "success")
        return redirect(url_for("student_login"))

    return render_template("student/register.html")


@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":

        student = Student.query.filter_by(email=request.form["email"]).first()

        if student and check_password_hash(student.password, request.form["password"]):
            session.clear()
            session["student_id"] = student.id
            return redirect(url_for("student_dashboard"))

        flash("Invalid email or password", "danger")

    return render_template("student/login.html")





@app.route("/student/dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    student = Student.query.get(session["student_id"])

    # Normalize for filtering
    student_branch = student.branch.strip().upper()
    student_year = student.year.strip()
    student_section = student.section.strip().upper()

    assignments = Assignment.query.filter(
        db.func.upper(db.func.trim(Assignment.branch)) == student_branch,
        db.func.trim(Assignment.year) == student_year,
        db.func.upper(db.func.trim(Assignment.section)) == student_section
    ).order_by(Assignment.due_date.asc()).all()

    submissions = Submission.query.filter_by(student_id=student.id).all()

    return render_template(
        "student/dashboard.html",
        student=student,
        assignments=assignments,
        submissions=submissions,
        current_date=date.today()
    )

@app.route("/student/submit/<int:assignment_id>", methods=["POST"])
def submit_assignment(assignment_id):

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    if Submission.query.filter_by(
        student_id=session["student_id"],
        assignment_id=assignment_id
    ).first():
        flash("Assignment already submitted!", "warning")
        return redirect(url_for("student_dashboard"))

    file = request.files.get("file")
    if not file:
        flash("No file selected", "danger")
        return redirect(url_for("student_dashboard"))

    upload = cloudinary.uploader.upload(file, resource_type="raw")

    submission = Submission(
        student_id=session["student_id"],
        assignment_id=assignment_id,
        file_url=upload["secure_url"],
        submitted_on=datetime.now(),
        plagiarism_score=fake_plagiarism_check(file.filename)
    )

    db.session.add(submission)
    db.session.commit()

    flash("Assignment submitted successfully!", "success")
    return redirect(url_for("student_dashboard"))


@app.route("/student/delete/<int:submission_id>", methods=["POST"])
def delete_submission(submission_id):

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    sub = Submission.query.get_or_404(submission_id)

    if sub.assignment.due_date >= date.today():
        db.session.delete(sub)
        db.session.commit()
        flash("Submission deleted. Re-upload allowed.", "success")
    else:
        flash("Deadline passed. Cannot delete.", "danger")

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
            flash("Teacher already exists!", "danger")
            return redirect(url_for("teacher_register"))

        teacher = Teacher(
            name=request.form["name"],
            email=request.form["email"],
            password=generate_password_hash(request.form["password"])
        )

        db.session.add(teacher)
        db.session.commit()

        flash("Registration successful! Please login.", "success")
        return redirect(url_for("teacher_login"))

    return render_template("teacher/register.html")


@app.route("/teacher/login", methods=["GET", "POST"])
def teacher_login():

    if request.method == "POST":

        teacher = Teacher.query.filter_by(email=request.form["email"]).first()

        if teacher and check_password_hash(
            teacher.password, request.form["password"]
        ):
            session.clear()
            session["teacher_id"] = teacher.id
            return redirect(url_for("teacher_dashboard"))

        flash("Invalid credentials", "danger")

    return render_template("teacher/login.html")


@app.route("/teacher/dashboard")
def teacher_dashboard():

    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    assignments = Assignment.query.all()
    students = Student.query.all()

    pending = {}

    for a in assignments:
        submitted = {
            s.student_id for s in Submission.query.filter_by(assignment_id=a.id)
        }
        pending[a.id] = [s for s in students if s.id not in submitted]

    return render_template(
        "teacher/dashboard.html",
        teacher=Teacher.query.get(session["teacher_id"]),
        assignments=assignments,
        pending=pending,
        current_date=date.today()
    )


@app.route("/teacher/submissions/<int:assignment_id>")
def teacher_submissions(assignment_id):

    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    assignment = Assignment.query.get_or_404(assignment_id)
    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()

    return render_template(
        "teacher/submissions.html",
        assignment=assignment,
        submissions=submissions
    )


@app.route("/teacher/upload", methods=["POST"])
def teacher_upload():

    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    file = request.files.get("file")
    if not file:
        flash("No file uploaded!", "danger")
        return redirect(url_for("teacher_dashboard"))

    upload = cloudinary.uploader.upload(file, resource_type="raw")

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

    flash("Assignment uploaded successfully!", "success")
    return redirect(url_for("teacher_dashboard"))


@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    return redirect(url_for("teacher_login"))


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)