


    from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary, cloudinary.uploader
import os
from datetime import date

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

# ---------------- DATABASE ----------------
DATABASE_URL = os.environ["DATABASE_URL"]
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---------------- CLOUDINARY ----------------
cloudinary.config(
    cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key=os.environ["CLOUDINARY_API_KEY"],
    api_secret=os.environ["CLOUDINARY_API_SECRET"]
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
    due_date = db.Column(db.Date)
    file_url = db.Column(db.String(500))

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return redirect("/student/login")

# -------- STUDENT --------
@app.route("/student/login", methods=["GET","POST"])
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

# -------- TEACHER --------
@app.route("/teacher/login", methods=["GET","POST"])
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
    return render_template(
        "teacher_dashboard.html",
        teacher=teacher,
        assignments=assignments
    )

# ---------------- START ----------------
if __name__ == "__main__":
    app.run()
