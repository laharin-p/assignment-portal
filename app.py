
from flask import Flask, render_template, request, redirect, session, url_for, flash, Response,send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary, cloudinary.uploader
import os
from datetime import datetime, date
import hashlib
import requests
import tempfile


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
    

    assignment = db.relationship("Assignment")
    student = db.relationship("Student")

# ---------------- CREATE TABLES ----------------
with app.app_context():
    db.create_all()

# ---------------- FILE PROXY ----------------


# ---------------- FILE PROXY FOR PDF ----------------
@app.route("/file")
def open_file():
    url = request.args.get("url")
    if not url:
        return "File not found", 404

    r = requests.get(url, stream=True)
    if r.status_code != 200:
        return "File not accessible", 404

    # Save the PDF to a temporary file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    for chunk in r.iter_content(chunk_size=8192):
        if chunk:
            tmp.write(chunk)
    tmp.flush()

    # Serve as PDF with correct headers
    return send_file(
        tmp.name,
        mimetype="application/pdf",
        as_attachment=True,  # Forces the app to recognize as a downloadable PDF
        download_name=url.split("/")[-1]
    )
   
# ---------------- PLAGIARISM ----------------
def plagiarism_check(assignment_id, new_file_content):
    old_submissions = Submission.query.filter_by(assignment_id=assignment_id).all()

    if not old_submissions:
        return 0.0   # First submission → no plagiarism

    new_words = set(new_file_content.lower().split())

    highest_score = 0

    for sub in old_submissions:
        try:
            response = requests.get(sub.file_url)
            old_content = response.text.lower()
            old_words = set(old_content.split())

            common_words = new_words.intersection(old_words)

            if len(new_words) > 0:
                similarity = (len(common_words) / len(new_words)) * 100
                highest_score = max(highest_score, similarity)

        except:
            continue

    return round(highest_score, 2)
# ---------------- HOME ----------------
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
            return render_template("student_register.html", error="Already exists")

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
        flash("Invalid credentials", "danger")
    return render_template("student_login.html")

@app.route("/student/dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    student = Student.query.get(session["student_id"])  # logged-in student

    return render_template(
        "student_dashboard.html",
        student=student,
        assignments=Assignment.query.all(),
        submissions=Submission.query.filter_by(student_id=session["student_id"]).all(),
        current_date=date.today()
    )

@app.route("/student/submit/<int:assignment_id>", methods=["POST"])
def submit_assignment(assignment_id):
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    file = request.files.get("file")
    if not file:
        flash("No file selected", "danger")
        return redirect(url_for("student_dashboard"))

    file_content = file.read().decode(errors="ignore")
    file.seek(0)

    score = plagiarism_check(assignment_id, file_content)

    file_hash = calculate_hash(file)
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
    flash("Assignment submitted successfully", "success")
    return redirect(url_for("student_dashboard"))

@app.route("/student/delete_submission/<int:submission_id>", methods=["POST"])
def delete_submission(submission_id):
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    submission = Submission.query.get_or_404(submission_id)

    # Security: only owner can delete
    if submission.student_id != session["student_id"]:
        flash("Not allowed", "danger")
        return redirect(url_for("student_dashboard"))

    # Delete from Cloudinary
    try:
        public_id = submission.file_url.split("/")[-1].split(".")[0]
        cloudinary.uploader.destroy(public_id, resource_type="raw")
    except:
        pass

    # Delete from DB
    db.session.delete(submission)
    db.session.commit()

    flash("Submission deleted", "success")
    return redirect(url_for("student_dashboard"))

@app.route("/student/logout")
def student_logout():
    session.clear()
    return redirect(url_for("student_login"))

# ================= TEACHER =================
# Teacher Registration Route
@app.route('/teacher/register', methods=['GET', 'POST'])
def teacher_register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        # Check if teacher already exists
        existing_teacher = Teacher.query.filter_by(email=email).first()
        if existing_teacher:
            flash('Email already registered', 'danger')
            return redirect(url_for('teacher_register'))

        # Hash the password and create new teacher
        hashed_password = generate_password_hash(password)
        new_teacher = Teacher(name=name, email=email, password=hashed_password)
        db.session.add(new_teacher)
        db.session.commit()

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('teacher_login'))

    # GET request – show registration form
    return render_template('teacher_register.html')

@app.route("/teacher/login", methods=["GET", "POST"])
def teacher_login():
    if request.method == "POST":
        teacher = Teacher.query.filter_by(email=request.form["email"]).first()
        if teacher and check_password_hash(teacher.password, request.form["password"]):
            session.clear()
            session["teacher_id"] = teacher.id
            session["teacher_name"] = teacher.name
            return redirect(url_for("teacher_dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("teacher_login.html")

@app.route("/teacher/dashboard")
def teacher_dashboard():
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    teacher = Teacher.query.get(session["teacher_id"])  # logged-in teacher
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
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    file = request.files.get("file")
    if not file:
        flash("No file uploaded", "danger")
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
        due_date=datetime.strptime(request.form["due_date"], "%Y-%m-%d").date(),
        file_url=upload["secure_url"]
    )

    db.session.add(assignment)
    db.session.commit()
    flash("Assignment uploaded", "success")
    return redirect(url_for("teacher_dashboard"))

@app.route('/teacher/submissions/<int:assignment_id>')
def teacher_submissions(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()

    return render_template(
        'teacher_submissions.html',
        assignment=assignment,
        submissions=submissions,
        current_date=date.today()
    )
@app.route('/teacher/pending/<int:assignment_id>')
def pending_students(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # All students
    all_students = Student.query.all()
    
    # Students who submitted
    submitted_students_ids = [
        sub.student_id for sub in Submission.query.filter_by(assignment_id=assignment_id).all()
    ]
    
    # Pending students = all - submitted
    pending_students = [s for s in all_students if s.id not in submitted_students_ids]

    return render_template(
        'teacher_pending.html',
        assignment=assignment,
        pending_students=pending_students
    )
@app.route("/teacher/delete_assignment/<int:assignment_id>", methods=["POST"])
def delete_assignment(assignment_id):
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    assignment = Assignment.query.get_or_404(assignment_id)

    # Delete assignment file from Cloudinary
    try:
        public_id = assignment.file_url.split("/")[-1].split(".")[0]
        cloudinary.uploader.destroy(public_id, resource_type="raw")
    except:
        pass

    # Also delete all submissions under it
    Submission.query.filter_by(assignment_id=assignment.id).delete()

    db.session.delete(assignment)
    db.session.commit()

    flash("Assignment deleted", "success")
    return redirect(url_for("teacher_dashboard"))
@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    return redirect(url_for("teacher_login"))

if __name__ == "__main__":
    app.run(debug=True)