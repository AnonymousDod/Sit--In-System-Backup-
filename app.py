from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
import os
from werkzeug.utils import secure_filename
from models import db, User, Feedback, Announcement, Reservation, Session, Computer
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import csv
import xml.etree.ElementTree as ET
from io import StringIO, BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('index'))
        user = User.query.filter_by(id_number=session['user_id']).first()
        if not user or not user.is_admin:
            flash('Unauthorized access. Admin privileges required.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure secret key

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///student_portal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
db.init_app(app)

def init_db():
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Check if admin user exists
        admin = User.query.filter_by(id_number='admin').first()
        if not admin:
            # Create admin user
            admin = User(
                id_number='admin',
                email='admin@admin.com',
                first_name='Admin',
                middle_name='',
                last_name='User',
                course='N/A',
                year_level='N/A',
                password=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully!")

# Available courses and year levels
COURSES = [
    'BS Computer Science',
    'BS Information Technology',
    'BS Information Systems',
    'BS Computer Engineering',
    'BS Electronics Engineering'
]

YEAR_LEVELS = ['1st Year', '2nd Year', '3rd Year', '4th Year', '5th Year']

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    if 'user_id' in session:
        user = User.query.filter_by(id_number=session['user_id']).first()
        if user and user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('home'))
    return render_template('index.html', courses=COURSES, year_levels=YEAR_LEVELS)

@app.route('/home')
def home():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user:
        session.pop('user_id', None)  # Clear invalid session
        flash('User not found. Please log in again.', 'error')
        return redirect(url_for('index'))
    
    if user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    active_announcements = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).all()
    return render_template('home.html', user=user, announcements=active_announcements)

@app.route('/user/session-history')
@login_required
def user_session_history():
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('home'))
    
    # Get all completed sessions for the user, ordered by end time
    sessions = Session.query.filter_by(user_id=user.id, status='completed').order_by(Session.end_time.desc()).all()
    
    # Calculate total hours spent in sessions
    total_hours = sum((session.end_time - session.start_time).total_seconds() / 3600 for session in sessions)
    
    return render_template('user_session_history.html', 
                         sessions=sessions,
                         total_hours=round(total_hours, 2),
                         remaining_sessions=user.remaining_sessions)

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    # Get statistics for admin dashboard
    total_users = User.query.filter_by(is_admin=False).count()  # Exclude admin users from count
    active_sessions = Session.query.filter_by(status='active').count()  # Count active sessions instead of reservations
    total_reservations = Reservation.query.count()
    completed_sessions = Session.query.filter_by(status='completed').count()  # Add completed sessions count
    
    # Get purpose statistics for the chart
    purpose_stats = db.session.query(
        Session.purpose,
        db.func.count(Session.id).label('count')
    ).filter(Session.status == 'completed').group_by(Session.purpose).all()
    
    # Convert to dictionary format for the chart
    purpose_data = {
        'labels': [purpose for purpose, _ in purpose_stats],
        'data': [count for _, count in purpose_stats]
    }
    
    # Get announcements from database
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    
    # Get all users for the users container
    users = User.query.filter_by(is_admin=False).order_by(User.last_name).all()
    
    # Get recent reservations (last 5) with user information
    recent_reservations = Reservation.query.join(User).order_by(Reservation.date.desc(), Reservation.time.desc()).limit(5).all()
    
    return render_template('admin_dashboard.html',
                         total_users=total_users,
                         active_reservations=active_sessions,  # Pass active sessions count
                         total_reservations=total_reservations,
                         completed_sessions=completed_sessions,  # Pass completed sessions count
                         announcements=announcements,
                         users=users,
                         recent_reservations=recent_reservations,
                         purpose_data=purpose_data)  # Add purpose data for the chart

@app.route('/login', methods=['POST'])
def login():
    id_number = request.form.get('username')
    password = request.form.get('password')
    
    user = User.query.filter_by(id_number=id_number).first()
    
    if user and check_password_hash(user.password, password):
        session['user_id'] = user.id_number
        flash('Login successful!', 'success')
        if user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('home'))
    else:
        flash('Invalid ID number or password', 'error')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    
    if request.method == 'POST':
        # Handle file upload
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{session['user_id']}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                user.profile_image = filename
        
        # Update user information
        user.email = request.form.get('email')
        user.first_name = request.form.get('first_name')
        user.middle_name = request.form.get('middle_name')
        user.last_name = request.form.get('last_name')
        user.course = request.form.get('course')
        user.year_level = request.form.get('year_level')
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('home'))
    
    return render_template('profile.html', user=user, courses=COURSES, year_levels=YEAR_LEVELS)

@app.route('/signup', methods=['POST'])
def signup():
    id_number = request.form.get('id_number')
    email = request.form.get('email')
    first_name = request.form.get('first_name')
    middle_name = request.form.get('middle_name')
    last_name = request.form.get('last_name')
    course = request.form.get('course')
    year_level = request.form.get('year_level')
    password = request.form.get('password')
    
    # Check if ID number already exists
    if User.query.filter_by(id_number=id_number).first():
        flash('ID Number already exists', 'error')
        return redirect(url_for('index'))
    
    # Check if email already exists
    if User.query.filter_by(email=email).first():
        flash('Email already exists', 'error')
        return redirect(url_for('index'))
    
    # Create new user
    new_user = User(
        id_number=id_number,
        email=email,
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        course=course,
        year_level=year_level,
        password=generate_password_hash(password),
        profile_image=None,
        is_admin=False  # Default to regular user
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    flash('Account created successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/create_admin', methods=['GET', 'POST'])
def create_admin():
    # This route should only be accessible once to create the initial admin
    if User.query.filter_by(is_admin=True).first():
        flash('Admin already exists', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        admin = User(
            id_number='admin',
            email='admin@admin.com',
            first_name='Admin',
            middle_name='',
            last_name='User',
            course='N/A',
            year_level='N/A',
            password=generate_password_hash('admin123'),  # Change this in production
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        flash('Admin account created successfully', 'success')
        return redirect(url_for('index'))
    
    return '''
        <form method="post">
            <button type="submit">Create Admin Account</button>
        </form>
    '''

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('home'))
    
    try:
        rating = request.form.get('rating')
        feedback_text = request.form.get('feedback_text')
        
        if not rating or not feedback_text:
            flash('Please fill in all fields', 'error')
            return redirect(url_for('home'))
        
        # Create new feedback
        new_feedback = Feedback(
            user_id=user.id,
            rating=int(rating),
            feedback_text=feedback_text,
            timestamp=datetime.utcnow()
        )
        
        db.session.add(new_feedback)
        db.session.commit()
        
        flash('Thank you for your feedback!', 'success')
        
    except Exception as e:
        flash('An error occurred while submitting feedback', 'error')
        print(f"Error submitting feedback: {str(e)}")
    
    return redirect(url_for('home'))

@app.route('/admin/feedback')
def admin_feedback():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    # Get all feedbacks with user information
    feedbacks = Feedback.query.join(User).order_by(Feedback.timestamp.desc()).all()
    
    return render_template('admin_feedback.html', feedbacks=feedbacks)

@app.route('/admin/feedback/<int:feedback_id>/mark-read', methods=['POST'])
def mark_feedback_read(feedback_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    feedback = Feedback.query.get_or_404(feedback_id)
    feedback.is_read = True
    db.session.commit()
    
    flash('Feedback marked as read', 'success')
    return redirect(url_for('admin_feedback'))

@app.route('/admin/feedback/<int:feedback_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_feedback(feedback_id):
    feedback = Feedback.query.get_or_404(feedback_id)
    
    try:
        db.session.delete(feedback)
        db.session.commit()
        flash('Feedback deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting feedback', 'error')
    
    return redirect(url_for('admin_feedback'))

@app.route('/admin/announcements', methods=['GET', 'POST'])
def admin_announcements():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        type = request.form.get('type', 'Normal')
        
        if not title or not content:
            flash('Title and content are required', 'error')
            return redirect(url_for('admin_announcements'))
        
        announcement = Announcement(
            title=title,
            content=content,
            type=type
        )
        
        try:
            db.session.add(announcement)
            db.session.commit()
            flash('Announcement created successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error creating announcement', 'error')
        
        return redirect(url_for('admin_announcements'))
    
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template('admin_announcements.html', announcements=announcements)

@app.route('/admin/announcements/<int:id>/edit', methods=['GET', 'POST'])
def edit_announcement(id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    announcement = Announcement.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            announcement.title = request.form.get('title')
            announcement.content = request.form.get('content')
            announcement.type = request.form.get('type', 'Normal')
            
            db.session.commit()
            
            # Check if it's an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'message': 'Announcement updated successfully!'
                })
            else:
                flash('Announcement updated successfully!', 'success')
                return redirect(url_for('admin_announcements'))
                
        except Exception as e:
            db.session.rollback()
            error_message = str(e)
            # Check if it's an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': f'Error updating announcement: {error_message}'
                }), 400
            else:
                flash(f'Error updating announcement: {error_message}', 'error')
                return redirect(url_for('admin_announcements'))
    
    return render_template('edit_announcement.html', announcement=announcement)

@app.route('/admin/announcements/<int:id>/delete', methods=['POST'])
def delete_announcement(id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    announcement = Announcement.query.get_or_404(id)
    
    try:
        db.session.delete(announcement)
        db.session.commit()
        flash('Announcement deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting announcement', 'error')
    
    return redirect(url_for('admin_announcements'))

@app.route('/admin/announcements/<int:id>/toggle', methods=['POST'])
def toggle_announcement(id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    announcement = Announcement.query.get_or_404(id)
    announcement.is_active = not announcement.is_active
    
    try:
        db.session.commit()
        status = 'activated' if announcement.is_active else 'deactivated'
        flash(f'Announcement {status} successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error updating announcement status', 'error')
    
    return redirect(url_for('admin_announcements'))

@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
def toggle_user_status(user_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    admin = User.query.filter_by(id_number=session['user_id']).first()
    if not admin or not admin.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    
    try:
        db.session.commit()
        status = 'activated' if user.is_active else 'deactivated'
        flash(f'User {status} successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error updating user status', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    admin = User.query.filter_by(id_number=session['user_id']).first()
    if not admin or not admin.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    user = User.query.get_or_404(user_id)
    
    try:
        db.session.delete(user)
        db.session.commit()
        flash('User deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting user', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.filter_by(is_admin=False).order_by(User.last_name).all()
    return render_template('admin_users.html', users=users)

class LabResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    link = db.Column(db.String(500))
    is_enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@app.route('/admin/resources')
@login_required
@admin_required
def admin_resources():
    resources = LabResource.query.all()
    return render_template('admin_resources.html', resources=resources)

@app.route('/admin/resources/add', methods=['POST'])
@login_required
@admin_required
def add_resource():
    name = request.form.get('name')
    description = request.form.get('description', 'None')
    link = request.form.get('link', '-')
    
    if not name:
        flash('Resource name is required', 'error')
        return redirect(url_for('admin_resources'))
    
    resource = LabResource(
        name=name,
        description=description,
        link=link
    )
    
    try:
        db.session.add(resource)
        db.session.commit()
        flash('Resource added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error adding resource', 'error')
    
    return redirect(url_for('admin_resources'))

@app.route('/admin/resources/<int:resource_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_resource(resource_id):
    resource = LabResource.query.get_or_404(resource_id)
    resource.is_enabled = not resource.is_enabled
    
    try:
        db.session.commit()
        status = 'enabled' if resource.is_enabled else 'disabled'
        flash(f'Resource {status} successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error updating resource status', 'error')
    
    return redirect(url_for('admin_resources'))

@app.route('/admin/resources/<int:resource_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_resource(resource_id):
    resource = LabResource.query.get_or_404(resource_id)
    
    try:
        db.session.delete(resource)
        db.session.commit()
        flash('Resource deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting resource', 'error')
    
    return redirect(url_for('admin_resources'))

@app.route('/resources')
@login_required
def user_resources():
    # Only show enabled resources to regular users
    resources = LabResource.query.filter_by(is_enabled=True).all()
    return render_template('user_resources.html', resources=resources)

@app.route('/reservations')
@login_required
def user_reservations():
    user = User.query.filter_by(id_number=session['user_id']).first()
    reservations = Reservation.query.filter_by(user_id=user.id).order_by(Reservation.date.desc(), Reservation.time.desc()).all()
    return render_template('user_reservations.html', reservations=reservations)

@app.route('/submit_reservation', methods=['POST'])
@login_required
def submit_reservation():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('home'))
    
    try:
        date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        time = datetime.strptime(request.form.get('time'), '%H:%M').time()
        purpose = request.form.get('purpose')
        laboratory_unit = request.form.get('laboratory_unit')
        
        if not all([date, time, purpose, laboratory_unit]):
            flash('Please fill in all fields', 'error')
            return redirect(url_for('home'))
        
        # Check for existing reservations at the same time
        existing_reservation = Reservation.query.filter_by(
            date=date,
            time=time,
            laboratory_unit=laboratory_unit,
            status='approved'
        ).first()
        
        if existing_reservation:
            flash('This time slot is already reserved', 'error')
            return redirect(url_for('home'))
        
        # Create new reservation
        new_reservation = Reservation(
            user_id=user.id,
            date=date,
            time=time,
            purpose=purpose,
            laboratory_unit=laboratory_unit
        )
        
        db.session.add(new_reservation)
        db.session.commit()
        
        flash('Reservation submitted successfully!', 'success')
        
    except Exception as e:
        flash('An error occurred while submitting reservation', 'error')
        print(f"Error submitting reservation: {str(e)}")
    
    return redirect(url_for('home'))

@app.route('/admin/reservations')
@login_required
@admin_required
def admin_reservations():
    # Get all reservations with user information, ordered by date and time, excluding completed ones
    reservations = Reservation.query.join(User).filter(Reservation.status != 'completed').order_by(Reservation.date.desc(), Reservation.time.desc()).all()
    
    # Calculate statistics
    stats = {
        'total': Reservation.query.filter(Reservation.status != 'completed').count(),
        'active': Reservation.query.filter_by(status='approved').count(),
        'pending': Reservation.query.filter_by(status='pending').count()
    }
    
    return render_template('admin_reservations.html', reservations=reservations, stats=stats)

@app.route('/admin/reservations/<int:reservation_id>/status', methods=['POST'])
@login_required
@admin_required
def update_reservation_status(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    data = request.get_json()
    new_status = data.get('status')
    
    if new_status not in ['approved', 'rejected']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    
    try:
        # If approving, check for conflicts
        if new_status == 'approved':
            existing_reservation = Reservation.query.filter(
                Reservation.date == reservation.date,
                Reservation.time == reservation.time,
                Reservation.laboratory_unit == reservation.laboratory_unit,
                Reservation.status == 'approved',
                Reservation.id != reservation.id
            ).first()
            
            if existing_reservation:
                return jsonify({
                    'success': False, 
                    'message': 'This time slot is already reserved by another user'
                }), 409
        
        reservation.status = new_status
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Reservation {new_status} successfully!'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error updating reservation status: {str(e)}'
        }), 500

@app.route('/admin/reservations/<int:reservation_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    
    try:
        db.session.delete(reservation)
        db.session.commit()
        flash('Reservation deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting reservation', 'error')
    
    return redirect(url_for('admin_reservations'))

@app.route('/admin/sessions', methods=['GET'])
@login_required
def admin_sessions():
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('home'))
    
    # Get all active sessions
    active_sessions = Session.query.filter_by(status='active').join(User).order_by(Session.start_time.desc()).all()
    
    # Get statistics
    total_sessions = Session.query.count()
    active_sessions_count = Session.query.filter_by(status='active').count()
    completed_sessions_count = Session.query.filter_by(status='completed').count()
    
    stats = {
        'total': total_sessions,
        'active': active_sessions_count,
        'completed': completed_sessions_count
    }
    
    return render_template('admin_sessions.html', sessions=active_sessions, stats=stats)

@app.route('/admin/sessions/start', methods=['POST'])
@login_required
def start_session():
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        return jsonify({'error': 'Access denied. Admin privileges required.'}), 403
    
    data = request.get_json()
    id_number = data.get('id_number')
    purpose = data.get('purpose')
    laboratory_unit = data.get('laboratory_unit')
    
    if not all([id_number, purpose, laboratory_unit]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Find user by ID number
    user = User.query.filter_by(id_number=id_number).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Check if user has remaining sessions
    if user.remaining_sessions <= 0:
        return jsonify({'error': 'User has no remaining sessions'}), 400
    
    # Create new session
    session = Session(
        user_id=user.id,
        purpose=purpose,
        laboratory_unit=laboratory_unit
    )
    
    try:
        # Decrement remaining sessions
        user.remaining_sessions -= 1
        db.session.add(session)
        db.session.commit()
        return jsonify({
            'message': 'Session started successfully',
            'session': session.to_dict(),
            'remaining_sessions': user.remaining_sessions
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/sessions/<int:session_id>/end', methods=['POST'])
@login_required
def end_session(session_id):
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        return jsonify({'error': 'Access denied. Admin privileges required.'}), 403
    
    lab_session = Session.query.get_or_404(session_id)
    
    if lab_session.status == 'completed':
        return jsonify({'error': 'Session already completed'}), 400
    
    try:
        lab_session.status = 'completed'
        lab_session.end_time = datetime.utcnow()
        db.session.commit()
        return jsonify({'message': 'Session ended successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/sessions/<int:session_id>', methods=['DELETE'])
@login_required
def delete_session(session_id):
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        return jsonify({'error': 'Access denied. Admin privileges required.'}), 403
    
    session = Session.query.get_or_404(session_id)
    
    try:
        db.session.delete(session)
        db.session.commit()
        return jsonify({'message': 'Session deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/sessions/start/<int:reservation_id>', methods=['POST'])
@login_required
@admin_required
def start_session_from_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    
    if reservation.status != 'approved':
        return jsonify({
            'success': False,
            'message': 'Cannot start session from unapproved reservation'
        }), 400
    
    try:
        # Get the user
        user = User.query.get(reservation.user_id)
        
        # Check if user has remaining sessions
        if user.remaining_sessions <= 0:
            return jsonify({
                'success': False,
                'message': 'User has no remaining sessions'
            }), 400
        
        # Create new session from reservation
        session = Session(
            user_id=reservation.user_id,
            purpose=reservation.purpose,
            laboratory_unit=reservation.laboratory_unit,
            start_time=datetime.utcnow()
        )
        
        # Decrement remaining sessions
        user.remaining_sessions -= 1
        
        # Delete the reservation after starting the session
        db.session.add(session)
        db.session.delete(reservation)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Session started successfully',
            'remaining_sessions': user.remaining_sessions
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error starting session: {str(e)}'
        }), 500

@app.route('/admin/session-history')
@login_required
@admin_required
def session_history():
    # Get all completed sessions with user information, ordered by end time
    sessions = Session.query.filter_by(status='completed').join(User).order_by(Session.end_time.desc()).all()
    
    # Get statistics
    total_sessions = Session.query.filter_by(status='completed').count()
    total_duration = sum((session.end_time - session.start_time).total_seconds() / 3600 for session in sessions)  # Total hours
    
    stats = {
        'total': total_sessions,
        'total_hours': round(total_duration, 2)
    }
    
    return render_template('session_history.html', sessions=sessions, stats=stats)

@app.route('/admin/users/<int:user_id>/reset-sessions', methods=['POST'])
@login_required
@admin_required
def reset_user_sessions(user_id):
    user = User.query.get_or_404(user_id)
    
    try:
        user.remaining_sessions = 30
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'User sessions reset successfully',
            'remaining_sessions': user.remaining_sessions
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error resetting sessions: {str(e)}'
        }), 500

@app.route('/admin/reports')
def admin_reports():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    return render_template('admin_reports.html')

@app.route('/admin/export/<report_type>/<format_type>', methods=['POST'])
@login_required
@admin_required
def export_report(report_type, format_type):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
    end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
    
    # Get data based on report type
    if report_type == 'user_activity':
        data = get_user_activity_data(start_date, end_date)
        title = "User Activity Report"
    elif report_type == 'lab_usage':
        data = get_lab_usage_data(start_date, end_date)
        title = "Laboratory Usage Report"
    elif report_type == 'statistics':
        data = get_statistics_data(start_date, end_date)
        title = "Statistics Report"
    else:
        flash('Invalid report type', 'error')
        return redirect(url_for('admin_reports'))
    
    # Generate report in requested format
    if format_type == 'pdf':
        return generate_pdf_report(data, title)
    elif format_type == 'csv':
        return generate_csv_report(data, title)
    elif format_type == 'xml':
        return generate_xml_report(data, title)
    else:
        flash('Invalid format type', 'error')
        return redirect(url_for('admin_reports'))

def get_user_activity_data(start_date, end_date):
    # Get user activity data from database
    sessions = Session.query.filter(
        Session.start_time >= start_date,
        Session.end_time <= end_date
    ).all()
    
    data = []
    for session in sessions:
        data.append({
            'user_id': session.user.id_number,
            'name': f"{session.user.first_name} {session.user.last_name}",
            'purpose': session.purpose,
            'start_time': session.start_time.strftime('%Y-%m-%d %H:%M'),
            'end_time': session.end_time.strftime('%Y-%m-%d %H:%M') if session.end_time else 'Ongoing',
            'status': session.status
        })
    return data

def get_lab_usage_data(start_date, end_date):
    # Get laboratory usage data from database
    sessions = Session.query.filter(
        Session.start_time >= start_date,
        Session.end_time <= end_date
    ).all()
    
    data = []
    for session in sessions:
        data.append({
            'laboratory_unit': session.laboratory_unit,
            'purpose': session.purpose,
            'start_time': session.start_time.strftime('%Y-%m-%d %H:%M'),
            'end_time': session.end_time.strftime('%Y-%m-%d %H:%M') if session.end_time else 'Ongoing',
            'status': session.status,
            'user': f"{session.user.first_name} {session.user.last_name}"
        })
    return data

def get_statistics_data(start_date, end_date):
    # Get statistics data from database
    total_sessions = Session.query.filter(
        Session.start_time >= start_date,
        Session.end_time <= end_date
    ).count()
    
    active_sessions = Session.query.filter(
        Session.start_time >= start_date,
        Session.end_time <= end_date,
        Session.status == 'active'
    ).count()
    
    completed_sessions = Session.query.filter(
        Session.start_time >= start_date,
        Session.end_time <= end_date,
        Session.status == 'completed'
    ).count()
    
    purpose_stats = db.session.query(
        Session.purpose,
        db.func.count(Session.id).label('count')
    ).filter(
        Session.start_time >= start_date,
        Session.end_time <= end_date
    ).group_by(Session.purpose).all()
    
    data = {
        'total_sessions': total_sessions,
        'active_sessions': active_sessions,
        'completed_sessions': completed_sessions,
        'purpose_stats': [(purpose, count) for purpose, count in purpose_stats]
    }
    return data

def generate_pdf_report(data, title):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    # Add title
    elements.append(Paragraph(title, styles['Title']))
    elements.append(Spacer(1, 12))
    
    # Create table data
    if isinstance(data, list):
        # For user activity and lab usage reports
        table_data = [list(data[0].keys())]  # Headers
        for row in data:
            table_data.append(list(row.values()))
    else:
        # For statistics report
        table_data = [
            ['Metric', 'Value'],
            ['Total Sessions', str(data['total_sessions'])],
            ['Active Sessions', str(data['active_sessions'])],
            ['Completed Sessions', str(data['completed_sessions'])]
        ]
        elements.append(Paragraph('Purpose Statistics', styles['Heading2']))
        elements.append(Spacer(1, 12))
        purpose_data = [['Purpose', 'Count']] + data['purpose_stats']
        purpose_table = Table(purpose_data)
        purpose_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(purpose_table)
        elements.append(Spacer(1, 20))
    
    # Create main table
    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{title.lower().replace(' ', '_')}.pdf",
        mimetype='application/pdf'
    )

def generate_csv_report(data, title):
    output = StringIO()
    writer = csv.writer(output)
    
    if isinstance(data, list):
        # For user activity and lab usage reports
        writer.writerow(data[0].keys())  # Headers
        for row in data:
            writer.writerow(row.values())
    else:
        # For statistics report
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Total Sessions', data['total_sessions']])
        writer.writerow(['Active Sessions', data['active_sessions']])
        writer.writerow(['Completed Sessions', data['completed_sessions']])
    
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"{title.lower().replace(' ', '_')}.csv",
        mimetype='text/csv'
    )

def generate_xml_report(data, title):
    root = ET.Element('report')
    root.set('title', title)
    
    if isinstance(data, list):
        # For user activity and lab usage reports
        for item in data:
            record = ET.SubElement(root, 'record')
            for key, value in item.items():
                field = ET.SubElement(record, key)
                field.text = str(value)
    else:
        # For statistics report
        stats = ET.SubElement(root, 'statistics')
        ET.SubElement(stats, 'total_sessions').text = str(data['total_sessions'])
        ET.SubElement(stats, 'active_sessions').text = str(data['active_sessions'])
        ET.SubElement(stats, 'completed_sessions').text = str(data['completed_sessions'])
        
        purposes = ET.SubElement(root, 'purposes')
        for purpose, count in data['purpose_stats']:
            purpose_elem = ET.SubElement(purposes, 'purpose')
            ET.SubElement(purpose_elem, 'name').text = purpose
            ET.SubElement(purpose_elem, 'count').text = str(count)
    
    tree = ET.ElementTree(root)
    output = StringIO()
    tree.write(output, encoding='unicode', xml_declaration=True)
    output.seek(0)
    
    return send_file(
        output,
        as_attachment=True,
        download_name=f"{title.lower().replace(' ', '_')}.xml",
        mimetype='application/xml'
    )

@app.route('/admin/computers')
@login_required
@admin_required
def admin_computers():
    # Get unique laboratory units from sessions
    laboratories = db.session.query(Session.laboratory_unit).distinct().all()
    laboratories = [lab[0] for lab in laboratories if lab[0]]  # Filter out None values
    
    # Get computers for each laboratory
    computers = Computer.query.order_by(Computer.laboratory_unit, Computer.computer_number).all()
    
    # Calculate statistics for each laboratory
    laboratory_stats = {}
    for lab in laboratories:
        lab_computers = [c for c in computers if c.laboratory_unit == lab]
        laboratory_stats[lab] = {
            'total': len(lab_computers),
            'vacant': len([c for c in lab_computers if c.status == 'vacant']),
            'occupied': len([c for c in lab_computers if c.status == 'occupied']),
            'maintenance': len([c for c in lab_computers if c.status == 'maintenance'])
        }
    
    return render_template('admin_computers.html', 
                         computers=computers,
                         laboratories=laboratories,
                         laboratory_stats=laboratory_stats)

@app.route('/admin/computers/add', methods=['POST'])
@login_required
@admin_required
def add_computer():
    computer_number = request.form.get('computer_number')
    laboratory_unit = request.form.get('laboratory_unit')
    
    if not computer_number or not laboratory_unit:
        flash('Computer number and laboratory unit are required', 'error')
        return redirect(url_for('admin_computers'))
    
    # Check if computer number already exists
    if Computer.query.filter_by(computer_number=computer_number).first():
        flash('Computer number already exists', 'error')
        return redirect(url_for('admin_computers'))
    
    computer = Computer(
        computer_number=computer_number,
        laboratory_unit=laboratory_unit
    )
    
    try:
        db.session.add(computer)
        db.session.commit()
        flash('Computer added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error adding computer', 'error')
    
    return redirect(url_for('admin_computers'))

@app.route('/admin/computers/<int:computer_id>/update-status', methods=['POST'])
@login_required
@admin_required
def update_computer_status(computer_id):
    computer = Computer.query.get_or_404(computer_id)
    new_status = request.form.get('status')
    
    if new_status not in ['vacant', 'occupied', 'maintenance']:
        flash('Invalid status', 'error')
        return redirect(url_for('admin_computers'))
    
    try:
        computer.status = new_status
        db.session.commit()
        flash('Computer status updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error updating computer status', 'error')
    
    return redirect(url_for('admin_computers'))

@app.route('/admin/computers/<int:computer_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_computer(computer_id):
    computer = Computer.query.get_or_404(computer_id)
    
    try:
        db.session.delete(computer)
        db.session.commit()
        flash('Computer deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting computer', 'error')
    
    return redirect(url_for('admin_computers'))

if __name__ == '__main__':
    init_db()  # Initialize database and create admin user
    app.run(debug=True) 