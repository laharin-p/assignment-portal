


    from datetime import datetime, date
from flask import (
    Flask, render_template, request,
    redirect, session, url_for
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary
import cloudinary.uploader
import os
import logging

# ---------------- APP SETUP ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

logging.basicConfig(level=logging.INFO)

# ---------------- DATABASE ----------------
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///assignment.db")

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
)

# ---------------- MODELS ----------------
class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


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
    title = db.Column(db.String(200), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    year = db.Column(db.String(10), nullable=False)
    branch = db.Column(db.String(20), nullable=False)
    section = db.Column(db.String(10), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"))
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"))
    file_url = db.Column(db.Text, nullable=False)
    plagiarism = db.Column(db.Float, default=0)
    marks = db.Column(db.Integer)

# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("student_login"))

# ================= STUDENT =================
@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        student = Student.query.filter_by(email=request.form["email"]).first()

        if student and check_password_hash(student.password, request.form["password"]):
            session.clear()
            session["student_id"] = student.id
            return redirect(url_for("student_dashboard"))

        return render_template("student_login.html", error="Invalid credentials")

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

    return render_template(
        "student_dashboard.html",
        student=student,
        assignments=assignments
    )


@app.route("/student/logout")
def student_logout():
    session.clear()
    return redirect(url_for("student_login"))

# ================= TEACHER =================
@app.route("/teacher/login", methods=["GET", "POST"])
def teacher_login():
    if request.method == "POST":
        teacher = Teacher.query.filter_by(email=request.form["email"]).first()

        if teacher and check_password_hash(teacher.password, request.form["password"]):
            session.clear()
            session["teacher_id"] = teacher.id
            return redirect(url_for("teacher_dashboard"))

        return render_template("teacher_login.html", error="Invalid credentials")

    return render_template("teacher_login.html")


@app.route("/teacher/dashboard")
def teacher_dashboard():
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    teacher = Teacher.query.get(session["teacher_id"])
    assignments = Assignment.query.order_by(Assignment.due_date.desc()).all()

    # ✅ FIX: pass teacher to template
    return render_template(
        "teacher_dashboard.html",
        teacher=teacher,
        assignments=assignments
    )


@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    return redirect(url_for("teacher_login"))

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
