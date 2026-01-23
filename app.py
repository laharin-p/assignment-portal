


from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import cloudinary, cloudinary.uploader
import os
from datetime import datetime

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
    __tablename__ = "teacher"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


class Student(db.Model):
    __tablename__ = "student"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


class Assignment(db.Model):
    __tablename__ = "assignment"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    year = db.Column(db.String(20))
    branch = db.Column(db.String(50))
    section = db.Column(db.String(20))
    due_date = db.Column(db.Date)
    file_url = db.Column(db.String(500))

# ---------------- CREATE TABLES ----------------
with app.app_context():
    db.create_all()

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return redirect("/student/login")

# ================= STUDENT =================
@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        if Student.query.filter_by(email=email).first():
            return render_template("student_register.html", error="Email already exists")

        student = Student(name=name, email=email, password=password)
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
        return redirect("/student/login")
    assignments = Assignment.query.all()
    return render_template("student_dashboard.html", assignments=assignments)


@app.route("/student/logout")
def student_logout():
    session.pop("student_id", None)
    return redirect(url_for("student_login"))

# ================= TEACHER =================
@app.route("/teacher/register", methods=["GET", "POST"])
def teacher_register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        if Teacher.query.filter_by(email=email).first():
            return render_template("teacher_register.html", error="Email already exists")

        teacher = Teacher(name=name, email=email, password=password)
        db.session.add(teacher)
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
            return redirect("/teacher/dashboard")
        return render_template("teacher_login.html", error="Invalid login")
    return render_template("teacher_login.html")


@app.route("/teacher/dashboard")
def teacher_dashboard():
    if "teacher_id" not in session:
        return redirect("/teacher/login")
    teacher = Teacher.query.get(session["teacher_id"])
    assignments = Assignment.query.all()
    return render_template("teacher_dashboard.html", teacher=teacher, assignments=assignments)


@app.route("/teacher/upload", methods=["POST"])
def teacher_upload():
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    title = request.form["title"]
    year = request.form["year"]
    branch = request.form["branch"]
    section = request.form["section"]
    due_date = datetime.strptime(request.form["due_date"], "%Y-%m-%d").date()
    file = request.files.get("file")

    if not file or file.filename == "":
        return "No file uploaded", 400

    filename = secure_filename(file.filename)

    upload = cloudinary.uploader.upload(
        file,
        resource_type="raw",
        public_id=filename
    )

    assignment = Assignment(
        title=title,
        year=year,
        branch=branch,
        section=section,
        due_date=due_date,
        file_url=upload["secure_url"]
    )

    db.session.add(assignment)
    db.session.commit()

    return redirect(url_for("teacher_dashboard"))


@app.route("/teacher/logout")
def teacher_logout():
    session.pop("teacher_id", None)
    return redirect(url_for("teacher_login"))

# ---------------- START ----------------
if __name__ == "__main__":
    app.run(debug=True)
