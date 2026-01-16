
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

db_path = "C:/Users/lahar/OneDrive/Desktop/assignment_portal/assignment.db"
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("✅ DB CREATED AT:", os.path.abspath(db_path))
