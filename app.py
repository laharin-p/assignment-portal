
from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary, cloudinary.uploader
import os
from datetime import datetime, date

# ---------------- APP ----------------
app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

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
    submitted_on = db.Column(db.Date)
    plagiarism_score = db.Column(db.Float)
    marks = db.Column(db.Float)

    assignment = db.relationship("Assignment")
    student = db.relationship("Student")

# ---------------- CREATE TABLES ----------------
with app.app_context():
    db.create_all()

# ---------------- PLAGIARISM (DUMMY) ----------------
def fake_plagiarism_check(filename):
    return 12.5

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return redirect(url_for("student_login"))

# ================= STUDENT =================
@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        name = request.form['name']
        roll_no = request.form['rollno']
        branch = request.form['branch']
        year = request.form['year']
        section = request.form['section']
        phone = request.form['phone']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        # Check duplicate roll or email
        existing = Student.query.filter(
            (Student.email == email) | (Student.roll_no == roll_no)
        ).first()

        if existing:
            return render_template('student_register.html', error="Roll number or Email already exists")

        student = Student(
            name=name,
            roll_no=roll_no,
            branch=branch,
            year=year,
            section=section,
            phone=phone,
            email=email,
            password=password
        )

        db.session.add(student)
        db.session.commit()

        # Auto login
        session['student_id'] = student.id
        session['student_name'] = student.name

        flash("Registration successful!", "success")
        return redirect('/student/dashboard')

    return render_template('student_register.html')

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        student = Student.query.filter_by(email=email).first()

        if student and check_password_hash(student.password, password):
            session['student_id'] = student.id
            session['student_name'] = student.name
            return redirect('/student/dashboard')

        flash("Invalid email or password", "danger")

    return render_template('student_login.html')

@app.route("/student/dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    # Fetch all assignments & submissions
    assignments = Assignment.query.all()
    submissions = Submission.query.filter_by(student_id=session["student_id"]).all()
    submission_map = {s.assignment_id: s for s in submissions}

    # Split assignments for cleaner UI
    available_assignments = [a for a in assignments if a.id not in submission_map]
    submitted_assignments = [a for a in assignments if a.id in submission_map]

    return render_template(
        "student_dashboard.html",
        available_assignments=available_assignments,
        submitted_assignments=submitted_assignments,
        submissions=submission_map,
        current_date=date.today()
    )

@app.route("/student/logout")
def student_logout():
    session.clear()
    return redirect(url_for("student_login"))

# ---------------- STUDENT SUBMISSION ----------------
@app.route("/student/submit/<int:assignment_id>", methods=["POST"])
def submit_assignment(assignment_id):
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    if "file" not in request.files:
        flash("No file uploaded", "danger")
        return redirect(url_for("student_dashboard"))

    file = request.files["file"]

    if file.filename == "":
        flash("No file selected", "danger")
        return redirect(url_for("student_dashboard"))

    # Prevent duplicate submission
    existing = Submission.query.filter_by(
        student_id=session["student_id"],
        assignment_id=assignment_id
    ).first()
    if existing:
        flash("Assignment already submitted", "warning")
        return redirect(url_for("student_dashboard"))

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
    flash("Assignment submitted successfully", "success")
    return redirect(url_for("student_dashboard"))

@app.route("/student/delete/<int:submission_id>", methods=["POST"])
def delete_submission(submission_id):
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    sub = Submission.query.get_or_404(submission_id)
    if sub.assignment.due_date >= date.today():
        db.session.delete(sub)
        db.session.commit()
        flash("Submission deleted. You can re-upload.", "success")
    else:
        flash("Cannot delete. Deadline passed.", "danger")

    return redirect(url_for("student_dashboard"))

# ================= TEACHER =================
@app.route("/teacher/register", methods=["GET", "POST"])
def teacher_register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        if Teacher.query.filter_by(email=email).first():
            flash("Teacher already registered", "danger")
            return redirect(url_for("teacher_login"))

        teacher = Teacher(
            name=name,
            email=email,
            password=generate_password_hash(password)
        )

        db.session.add(teacher)
        db.session.commit()
        flash("Registration successful", "success")
        return redirect(url_for("teacher_login"))

    return render_template("teacher_register.html")

@app.route("/teacher/login", methods=["GET", "POST"])
def teacher_login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        t = Teacher.query.filter_by(email=email).first()
        if t and check_password_hash(t.password, password):
            session.clear()
            session["teacher_id"] = t.id
            return redirect(url_for("teacher_dashboard"))

        flash("Invalid credentials", "danger")

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
        submitted_ids = [s.student_id for s in Submission.query.filter_by(assignment_id=a.id)]
        pending[a.id] = [s for s in students if s.id not in submitted_ids]

    return render_template(
        "teacher_dashboard.html",
        teacher=teacher,
        assignments=assignments,
        pending=pending,
        current_date=date.today()
    )

@app.route("/teacher/upload", methods=["POST"])
def teacher_upload():
    if "file" not in request.files:
        flash("No file uploaded", "danger")
        return redirect(url_for("teacher_dashboard"))

    file = request.files["file"]
    upload = cloudinary.uploader.upload(file, resource_type="raw")

    assignment = Assignment(
        title=request.form.get("title"),
        year=request.form.get("year"),
        branch=request.form.get("branch"),
        section=request.form.get("section"),
        due_date=datetime.strptime(request.form.get("due_date"), "%Y-%m-%d").date(),
        file_url=upload["secure_url"]
    )

    db.session.add(assignment)
    db.session.commit()
    flash("Assignment uploaded successfully", "success")
    return redirect(url_for("teacher_dashboard"))

@app.route("/teacher/submissions/<int:assignment_id>", methods=["GET", "POST"])
def teacher_submissions(assignment_id):
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    assignment = Assignment.query.get_or_404(assignment_id)
    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()

    if request.method == "POST":
        sub = Submission.query.get(request.form.get("submission_id"))
        sub.marks = float(request.form.get("marks"))
        db.session.commit()
        flash("Marks updated successfully", "success")
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

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
