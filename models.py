from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    id_number = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50), nullable=False)
    course = db.Column(db.String(100), nullable=False)
    year_level = db.Column(db.String(20), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    profile_image = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    remaining_sessions = db.Column(db.Integer, default=30)
    points = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sessions = db.relationship('Session', backref='user', lazy=True)
    reservations = db.relationship('Reservation', backref='user', lazy=True)
    feedback = db.relationship('Feedback', backref='user', lazy=True)
    sessions_awarded_for_points = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<User {self.id_number}>'

    def to_dict(self):
        return {
            'id': self.id,
            'id_number': self.id_number,
            'email': self.email,
            'first_name': self.first_name,
            'middle_name': self.middle_name,
            'last_name': self.last_name,
            'course': self.course,
            'year_level': self.year_level,
            'profile_image': self.profile_image,
            'is_admin': self.is_admin
        }

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    feedback_text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    session_id = db.Column(db.Integer, db.ForeignKey('session.id'), nullable=True)
    session = db.relationship('Session', backref='feedbacks', foreign_keys=[session_id])

class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='Normal')  # Normal, Important, Urgent
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Announcement {self.title}>'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'type': self.type,
            'created_at': self.created_at.strftime('%b %d, %Y %I:%M %p'),
            'is_active': self.is_active
        }

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    purpose = db.Column(db.String(100), nullable=False)
    laboratory_unit = db.Column(db.String(50), nullable=False)
    computer_id = db.Column(db.Integer, db.ForeignKey('computers.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='active')  # active, completed
    is_manual = db.Column(db.Boolean, default=False)  # True if created by admin manually

    # Add relationship to Computer model
    computer = db.relationship('Computer', backref='sessions')

    def __repr__(self):
        return f'<Session {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'purpose': self.purpose,
            'laboratory_unit': self.laboratory_unit,
            'computer_id': self.computer_id,
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M'),
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M') if self.end_time else None,
            'status': self.status,
            'is_manual': self.is_manual
        }

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    purpose = db.Column(db.String(100), nullable=False)
    laboratory_unit = db.Column(db.String(50), nullable=False)
    computer_id = db.Column(db.Integer, db.ForeignKey('computers.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Add relationship to Computer model
    computer = db.relationship('Computer', backref='reservations')

    def __repr__(self):
        return f'<Reservation {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'date': self.date.strftime('%Y-%m-%d'),
            'time': self.time.strftime('%H:%M'),
            'purpose': self.purpose,
            'laboratory_unit': self.laboratory_unit,
            'computer_id': self.computer_id,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M')
        }

class Computer(db.Model):
    __tablename__ = 'computers'
    id = db.Column(db.Integer, primary_key=True)
    computer_number = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='vacant')  # vacant, occupied, maintenance
    laboratory_unit = db.Column(db.String(100), nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('computer_number', 'laboratory_unit', name='uix_pc_lab'),)
    
    def __repr__(self):
        return f'<Computer {self.computer_number}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'computer_number': self.computer_number,
            'status': self.status,
            'laboratory_unit': self.laboratory_unit,
            'last_updated': self.last_updated.strftime('%Y-%m-%d %H:%M:%S')
        }

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Null for admin/global
    user = db.relationship('User', backref='notifications', foreign_keys=[user_id])
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    for_admin = db.Column(db.Boolean, default=False)  # True for admin notifications
    lab = db.Column(db.String(100), nullable=True)
    pc = db.Column(db.String(100), nullable=True) 