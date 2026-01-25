
from flask import Flask, render_template, request, redirect, session, url_for, flash, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary, cloudinary.uploader
import os
from datetime import datetime, date
import hashlib
import requests
import mimetypes
from urllib.parse import urlparse

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
    plagiarism_score = db.Column(db.Float, default=0)

    assignment = db.relationship("Assignment")
    student = db.relationship("Student")

with app.app_context():
    db.create_all()

# ---------------- IMPROVED FILE HANDLING ----------------
@app.route("/file")
def open_file():
    """Improved file handler that works on all devices"""
    url = request.args.get("url")
    if not url:
        flash("File URL not provided", "danger")
        return redirect(request.referrer or url_for('student_dashboard'))
    
    try:
        # Parse the URL to get filename
        parsed_url = urlparse(url)
        filename = parsed_url.path.split("/")[-1]
        file_extension = filename.split('.')[-1].lower() if '.' in filename else ''
        
        # Comprehensive MIME type mapping
        mime_type_map = {
            # Documents
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'txt': 'text/plain',
            'rtf': 'application/rtf',
            'odt': 'application/vnd.oasis.opendocument.text',
            
            # Spreadsheets
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'ods': 'application/vnd.oasis.opendocument.spreadsheet',
            
            # Presentations
            'ppt': 'application/vnd.ms-powerpoint',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'odp': 'application/vnd.oasis.opendocument.presentation',
            
            # Images
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'bmp': 'image/bmp',
            'svg': 'image/svg+xml',
            'webp': 'image/webp',
            
            # Archives
            'zip': 'application/zip',
            'rar': 'application/x-rar-compressed',
            '7z': 'application/x-7z-compressed',
            'tar': 'application/x-tar',
            'gz': 'application/gzip',
            
            # Code/Text
            'html': 'text/html',
            'htm': 'text/html',
            'css': 'text/css',
            'js': 'application/javascript',
            'json': 'application/json',
            'xml': 'application/xml',
            'csv': 'text/csv',
            
            # Audio/Video (if you allow these)
            'mp3': 'audio/mpeg',
            'mp4': 'video/mp4',
            'avi': 'video/x-msvideo',
            'mov': 'video/quicktime',
            'wav': 'audio/wav',
        }
        
        # Get MIME type
        mime_type = mime_type_map.get(file_extension)
        if not mime_type:
            # Try to guess from mimetypes module
            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type:
                # Default to octet-stream
                mime_type = 'application/octet-stream'
        
        # Get disposition from query parameter
        disposition = request.args.get("disposition", "inline")
        
        # For mobile optimization - certain files should always download
        mobile_download_types = ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar']
        user_agent = request.headers.get('User-Agent', '').lower()
        is_mobile = any(m in user_agent for m in ['mobile', 'android', 'iphone', 'ipad', 'ipod'])
        
        if is_mobile and file_extension in mobile_download_types:
            disposition = "download"
        
        # Fetch the file from Cloudinary with timeout
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, stream=True, timeout=30, headers=headers)
        response.raise_for_status()
        
        # Create Flask response
        flask_response = Response(
            response.iter_content(chunk_size=8192),
            content_type=mime_type,
            headers={
                'Content-Disposition': f'{disposition}; filename="{filename}"',
                'Cache-Control': 'public, max-age=86400',  # Cache for 24 hours
                'Access-Control-Allow-Origin': '*',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        
        # Copy relevant headers from Cloudinary response
        for header in ['Content-Length', 'Last-Modified', 'ETag']:
            if header in response.headers:
                flask_response.headers[header] = response.headers[header]
        
        return flask_response
        
    except requests.exceptions.RequestException as e:
        flash(f"Error accessing file: {str(e)}", "danger")
        return redirect(request.referrer or url_for('student_dashboard'))
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "danger")
        return redirect(request.referrer or url_for('student_dashboard'))

# ---------------- ALTERNATIVE SIMPLE FILE ROUTE ----------------
@app.route("/direct_file")
def direct_file():
    """Simple redirect to Cloudinary - works on most devices"""
    url = request.args.get("url")
    if not url:
        return "File URL not provided", 400
    return redirect(url)

# ---------------- PLAGIARISM ----------------
def calculate_hash(file):
    file.stream.seek(0)
    content = file.stream.read()
    file.stream.seek(0)
    return hashlib.sha256(content).hexdigest()

def plagiarism_check(assignment_id, file_hash):
    existing = Submission.query.filter_by(
        assignment_id=assignment_id,
        file_hash=file_hash
    ).first()
    return 95.0 if existing else 5.0

# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("student_login"))

# ================= STUDENT =================
@app.route("/student/register", methods=["GET","POST"])
def student_register():
    if "student_id" in session:
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":
        # Normalize email for case-insensitive comparison
        email = request.form["email"].strip().lower()
        roll_no = request.form["rollno"].strip()
        
        exists = Student.query.filter(
            (Student.email == email) |
            (Student.roll_no == roll_no)
        ).first()
        if exists:
            flash("Student already exists","danger")
            return redirect(url_for("student_register"))

        student = Student(
            name=request.form["name"].strip(),
            roll_no=roll_no,
            branch=request.form["branch"].strip().upper(),
            year=str(request.form["year"]).strip().upper(),
            section=request.form["section"].strip().upper(),
            phone=request.form["phone"].strip(),
            email=email,
            password=generate_password_hash(request.form["password"])
        )
        db.session.add(student)
        db.session.commit()

        session.clear()
        session["student_id"] = student.id
        session["student_name"] = student.name

        flash("Registered & logged in successfully","success")
        return redirect(url_for("student_dashboard"))

    return render_template("student_register.html")

@app.route("/student/login", methods=["GET","POST"])
def student_login():
    if "student_id" in session:
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        
        if not email or not password:
            flash("Email and password are required", "danger")
            return redirect(url_for("student_login"))
            
        student = Student.query.filter_by(email=email).first()
        if student and check_password_hash(student.password, password):
            session.clear()
            session["student_id"] = student.id
            session["student_name"] = student.name
            return redirect(url_for("student_dashboard"))

        flash("Invalid credentials", "danger")
        return redirect(url_for("student_login"))

    return render_template("student_login.html")

# ================= STUDENT DASHBOARD =================
@app.route("/student/dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    student = Student.query.get(session["student_id"])

    # Case-insensitive query for assignments
    assignments = Assignment.query.filter(
        db.func.lower(Assignment.year) == db.func.lower(student.year),
        db.func.lower(Assignment.branch) == db.func.lower(student.branch),
        db.func.lower(Assignment.section) == db.func.lower(student.section)
    ).all()

    submissions = Submission.query.filter_by(student_id=student.id).all()
    submitted_map = {s.assignment_id: s for s in submissions}

    today = date.today()
    available_assignments = []
    submitted_assignments = []

    for a in assignments:
        days_left = (a.due_date - today).days

        if days_left < 0:
            color = "red"
            can_upload = False
        elif days_left <= 2:
            color = "orange"
            can_upload = True
        else:
            color = "green"
            can_upload = True

        if a.id in submitted_map:
            s = submitted_map[a.id]
            submitted_assignments.append({
                "assignment": a,
                "submitted_on": s.submitted_on,
                "file_url": s.file_url,
                "plagiarism_score": s.plagiarism_score or 0,
                "days_left": days_left,
                "color": color,
                "submission_id": s.id
            })
        else:
            available_assignments.append({
                "assignment": a,
                "days_left": days_left,
                "color": color,
                "can_upload": can_upload
            })

    return render_template(
        "student_dashboard.html",
        student=student,
        available_assignments=available_assignments,
        submitted_assignments=submitted_assignments,
        current_date=today
    )

@app.route("/student/submit/<int:assignment_id>", methods=["POST"])
def submit_assignment(assignment_id):
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    assignment = Assignment.query.get_or_404(assignment_id)

    if assignment.due_date < date.today():
        flash("Deadline crossed","danger")
        return redirect(url_for("student_dashboard"))

    if Submission.query.filter_by(student_id=session["student_id"], assignment_id=assignment_id).first():
        flash("Already submitted","warning")
        return redirect(url_for("student_dashboard"))

    file = request.files.get("file")
    if not file:
        flash("No file selected","danger")
        return redirect(url_for("student_dashboard"))

    file_hash = calculate_hash(file)
    score = plagiarism_check(assignment_id, file_hash)

    upload = cloudinary.uploader.upload(file, resource_type="raw", use_filename=True, unique_filename=True)

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

    flash("Submitted successfully","success")
    return redirect(url_for("student_dashboard"))

@app.route("/student/delete_submission/<int:submission_id>", methods=["POST"])
def delete_submission(submission_id):
    if "student_id" not in session:
        return redirect(url_for("student_login"))

    submission = Submission.query.get_or_404(submission_id)
    if submission.student_id != session["student_id"]:
        flash("Unauthorized","danger")
        return redirect(url_for("student_dashboard"))

    # Delete from Cloudinary
    public_id = submission.file_url.split("/")[-1].split(".")[0]
    try:
        cloudinary.uploader.destroy(public_id, resource_type="raw")
    except:
        pass

    db.session.delete(submission)
    db.session.commit()
    flash("Submission deleted successfully","success")
    return redirect(url_for("student_dashboard"))

@app.route("/student/logout")
def student_logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for("student_login"))

# ================= TEACHER ROUTES =================
@app.route("/teacher/register", methods=["GET","POST"])
def teacher_register():
    if "teacher_id" in session:
        return redirect(url_for("teacher_dashboard"))

    if request.method == "POST":
        email = request.form["email"].strip().lower()
        
        if Teacher.query.filter_by(email=email).first():
            flash("Teacher already exists","danger")
            return redirect(url_for("teacher_register"))

        teacher = Teacher(
            name=request.form["name"].strip(),
            email=email,
            password=generate_password_hash(request.form["password"])
        )
        db.session.add(teacher)
        db.session.commit()
        flash("Teacher registered","success")
        return redirect(url_for("teacher_login"))

    return render_template("teacher_register.html")

@app.route("/teacher/login", methods=["GET","POST"])
def teacher_login():
    if "teacher_id" in session:
        return redirect(url_for("teacher_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        
        if not email or not password:
            flash("Email and password are required", "danger")
            return redirect(url_for("teacher_login"))
            
        teacher = Teacher.query.filter_by(email=email).first()
        if teacher and check_password_hash(teacher.password, password):
            session.clear()
            session["teacher_id"] = teacher.id
            session["teacher_name"] = teacher.name
            return redirect(url_for("teacher_dashboard"))
        
        flash("Invalid credentials", "danger")
        return redirect(url_for("teacher_login"))

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
        submitted_ids = [s.student_id for s in Submission.query.filter_by(assignment_id=a.id).all()]
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
        flash("No file uploaded","danger")
        return redirect(url_for("teacher_dashboard"))

    upload = cloudinary.uploader.upload(file, resource_type="raw", use_filename=True, unique_filename=True)

    assignment = Assignment(
        title=request.form["title"].strip(),
        year=str(request.form["year"]).strip().upper(),
        branch=request.form["branch"].strip().upper(),
        section=request.form["section"].strip().upper(),
        due_date=datetime.strptime(request.form["due_date"], "%Y-%m-%d").date(),
        file_url=upload["secure_url"]
    )
    db.session.add(assignment)
    db.session.commit()
    flash("Assignment uploaded","success")
    return redirect(url_for("teacher_dashboard"))

@app.route("/teacher/submissions/<int:assignment_id>")
def teacher_submissions(assignment_id):
    if "teacher_id" not in session:
        return redirect(url_for("teacher_login"))

    assignment = Assignment.query.get_or_404(assignment_id)
    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()

    return render_template(
        "teacher_submissions.html",
        assignment=assignment,
        submissions=submissions,
        current_date=date.today()
    )

@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for("teacher_login"))

# ---------------- DEBUG ROUTES ----------------
@app.route("/debug/assignments")
def debug_assignments():
    """Temporary route to check all assignments in database"""
    all_assignments = Assignment.query.all()
    result = []
    for a in all_assignments:
        result.append({
            "id": a.id,
            "title": a.title,
            "year": a.year,
            "branch": a.branch,
            "section": a.section,
            "due_date": str(a.due_date)
        })
    return jsonify(result)

# ---------------- RUN APP ----------------
if __name__ == "__main__":
    app.run(debug=True)