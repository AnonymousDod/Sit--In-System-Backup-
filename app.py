from flask import Flask, render_template, request, redirect, url_for, flash, session as flask_session, send_from_directory, jsonify, send_file, abort
from flask_sqlalchemy import SQLAlchemy
import os
from werkzeug.utils import secure_filename
from models import db, User, Feedback, Announcement, Reservation, Session, Computer
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from functools import wraps
import csv
import xml.etree.ElementTree as ET
from io import StringIO, BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import secrets

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in flask_session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in flask_session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('index'))
        user = User.query.filter_by(id_number=flask_session['user_id']).first()
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
app.config['UPLOAD_FOLDER'] = 'static/uploads/resources'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['ALLOWED_EXTENSIONS'] = {
    'image': {'png', 'jpg', 'jpeg', 'gif'},
    'video': {'mp4', 'webm', 'ogg'},
    'document': {'pdf', 'doc', 'docx', 'xls', 'xlsx'}  # Added document types
}

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
db.init_app(app)

def init_db():
    with app.app_context():
        try:
            # Create tables if they don't exist
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
                    is_admin=True,
                    points=0  # Initialize points for admin
                )
                db.session.add(admin)
                db.session.commit()
                print("Admin user created successfully!")
        except Exception as e:
            print(f"Error initializing database: {str(e)}")
            db.session.rollback()

# Available courses and year levels
COURSES = [
    'BS Computer Science',
    'BS Information Technology',
    'BS Information Systems',
    'BS Computer Engineering',
    'BS Electronics Engineering'
]

YEAR_LEVELS = ['1st Year', '2nd Year', '3rd Year', '4th Year', '5th Year']

def allowed_file(filename, file_type):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS'][file_type]

@app.route('/')
def index():
    if 'user_id' in flask_session:
        user = User.query.filter_by(id_number=flask_session['user_id']).first()
        if user and user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('home'))
    return render_template('index.html', courses=COURSES, year_levels=YEAR_LEVELS)

@app.route('/home')
def home():
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    if not user:
        flask_session.pop('user_id', None)  # Clear invalid session
        flash('User not found. Please log in again.', 'error')
        return redirect(url_for('index'))
    
    if user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    # Only show rejected reservation notifications once immediately after login
    if flask_session.pop('show_rejected_notifs', False):
        rejected_reservations = Reservation.query.filter_by(user_id=user.id, status='rejected').order_by(Reservation.date.desc()).all()
        for reservation in rejected_reservations:
            flash(f"Your reservation for {reservation.laboratory_unit} on {reservation.date.strftime('%Y-%m-%d')} at {reservation.time} was rejected.", 'warning')
    
    active_announcements = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).all()
    labs = [
        'Laboratory 517', 'Laboratory 524', 'Laboratory 526',
        'Laboratory 528', 'Laboratory 530', 'Laboratory 542', 'Laboratory 544'
    ]
    today = date.today().strftime('%Y-%m-%d')
    return render_template('home.html', user=user, announcements=active_announcements, labs=labs, today=today)

@app.route('/user/session-history')
@login_required
def user_session_history():
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
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
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    # Notify admin if there are new pending reservations
    pending_count = Reservation.query.filter_by(status='pending').count()
    if pending_count > 0:
        flash(f'There are {pending_count} pending reservation(s) awaiting your approval.', 'info')
    
    # Get statistics for admin dashboard
    total_users = User.query.filter_by(is_admin=False).count()  # Exclude admin users from count
    active_sessions = Session.query.filter_by(status='active').count()  # Count active sessions instead of reservations
    total_reservations = Reservation.query.count()
    completed_sessions = Session.query.filter_by(status='completed').count()  # Add completed sessions count
    
    # Define the new purpose categories
    purpose_categories = [
        'C Programming',
        'Java Programming',
        'Python Programming',
        'C# Programming',
        'Database',
        'Digital logic & Design',
        'Embedded Systems & IOT',
        'System Integration & Architecture',
        'Computer Application',
        'Project Management',
        'IT Trends',
        'Technopreneurship',
        'Capstone Project'
    ]
    # Get all completed sessions
    completed_sessions_qs = Session.query.filter_by(status='completed').all()
    # Count by category
    purpose_counts = {cat: 0 for cat in purpose_categories}
    for lab_session in completed_sessions_qs:
        if lab_session.purpose in purpose_categories:
            purpose_counts[lab_session.purpose] += 1
    # Remove categories with zero count
    filtered_purpose_counts = {k: v for k, v in purpose_counts.items() if v > 0}
    purpose_data = {
        'labels': list(filtered_purpose_counts.keys()),
        'data': list(filtered_purpose_counts.values())
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
        flask_session['user_id'] = user.id_number
        flask_session['show_rejected_notifs'] = True  # Set flag to show rejected notifications after login
        flash('Login successful!', 'success')
        if user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('home'))
    else:
        flash('Invalid ID number or password', 'error')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    flask_session.pop('user_id', None)
    flask_session.pop('rejected_notifs_shown', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    
    if request.method == 'POST':
        # Handle file upload
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename and allowed_file(file.filename, 'image'):
                filename = secure_filename(f"{flask_session['user_id']}_{file.filename}")
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
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('home'))
    
    try:
        rating = request.form.get('rating')
        feedback_text = request.form.get('feedback_text')
        session_id = request.form.get('session_id')
        
        if not rating or not feedback_text:
            flash('Please fill in all fields', 'error')
            return redirect(url_for('home'))
        
        # Create new feedback
        new_feedback = Feedback(
            user_id=user.id,
            rating=int(rating),
            feedback_text=feedback_text,
            timestamp=datetime.utcnow(),
            session_id=session_id if session_id else None
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
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    # Get all feedbacks with user information
    feedbacks = Feedback.query.join(User).order_by(Feedback.timestamp.desc()).all()
    
    return render_template('admin_feedback.html', feedbacks=feedbacks)

@app.route('/admin/feedback/<int:feedback_id>/mark-read', methods=['POST'])
def mark_feedback_read(feedback_id):
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
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
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
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
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
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
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
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
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
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
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    admin = User.query.filter_by(id_number=flask_session['user_id']).first()
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
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    admin = User.query.filter_by(id_number=flask_session['user_id']).first()
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

@app.route('/admin/users/search/<id_number>')
@login_required
@admin_required
def admin_search_user(id_number):
    user = User.query.filter_by(id_number=id_number).first()
    if user and not user.is_admin:
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'id_number': user.id_number,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'course': user.course,
                'year_level': user.year_level
            }
        })
    else:
        return jsonify({'success': False, 'message': 'Student not found.'})

class LabResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    link = db.Column(db.String(500))
    file_path = db.Column(db.String(500))  # Store the path to uploaded file
    file_type = db.Column(db.String(50))   # Store the type of file (image/video)
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
    
    # Handle file upload
    file_path = None
    file_type = None
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            # Determine file type
            file_ext = file.filename.rsplit('.', 1)[1].lower()
            if file_ext in app.config['ALLOWED_EXTENSIONS']['image']:
                file_type = 'image'
            elif file_ext in app.config['ALLOWED_EXTENSIONS']['video']:
                file_type = 'video'
            elif file_ext in app.config['ALLOWED_EXTENSIONS']['document']:
                file_type = 'document'
            else:
                flash('Invalid file type. Please upload an image, video, or document file (PDF, Word, Excel).', 'error')
                return redirect(url_for('admin_resources'))
            
            # Save file
            filename = secure_filename(f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
            file_path = os.path.join('uploads', 'resources', filename).replace('\\', '/')
            file.save(os.path.join(app.static_folder, 'uploads', 'resources', filename))
    
    resource = LabResource(
        name=name,
        description=description,
        link=link,
        file_path=file_path,
        file_type=file_type
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
        # Delete the file if it exists
        if resource.file_path:
            file_path = os.path.join(app.static_folder, resource.file_path)
            if os.path.exists(file_path):
                os.remove(file_path)
        
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
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    reservations = Reservation.query.filter_by(user_id=user.id).order_by(Reservation.date.desc(), Reservation.time.desc()).all()
    return render_template('user_reservations.html', reservations=reservations)

@app.route('/get_available_pcs/<laboratory>')
@login_required
def get_available_pcs(laboratory):
    try:
        # Get all vacant PCs in the selected laboratory
        computers = Computer.query.filter_by(
            laboratory_unit=laboratory,
            status='vacant'
        ).order_by(Computer.computer_number).all()
        
        return jsonify({
            'success': True,
            'pcs': [pc.to_dict() for pc in computers]
        })
    except Exception as e:
        print(f"Error fetching PCs: {str(e)}")  # Log the error for debugging
        return jsonify({
            'success': False,
            'message': 'Error fetching available PCs'
        }), 500

@app.route('/submit_reservation', methods=['POST'])
@login_required
def submit_reservation():
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('home'))
    
    try:
        date_val = request.form.get('date')
        time_val = request.form.get('time')
        purpose = request.form.get('purpose')
        laboratory_unit = request.form.get('laboratory_unit')
        pc_id = request.form.get('computer_id')
        print('DEBUG FORM VALUES:', date_val, time_val, purpose, laboratory_unit, pc_id)
        date = datetime.strptime(date_val, '%Y-%m-%d').date() if date_val else None
        # FIX: Extract start time from '8:00-9:00' format
        start_time_str = time_val.split('-')[0] if time_val else None
        time = datetime.strptime(start_time_str.strip(), '%H:%M').time() if start_time_str else None
        if not all([date, time, purpose, laboratory_unit, pc_id]):
            flash('Please fill in all fields', 'error')
            print('DEBUG: Missing field(s)')
            return redirect(url_for('home'))
        # Prevent duplicate reservation: block if user has a pending or approved reservation for any future date/time
        existing_res = Reservation.query.filter(
            Reservation.user_id == user.id,
            Reservation.status.in_(['pending', 'approved']),
            Reservation.date >= datetime.now().date()
        ).first()
        if existing_res:
            flash('You already have a pending or approved reservation. Please wait for it to be processed before making another.', 'error')
            return redirect(url_for('home'))
        # Check if the selected PC is available
        computer = Computer.query.get(pc_id)
        print('DEBUG: Computer object:', computer)
        if not computer or computer.status != 'vacant':
            flash('The selected PC is not available', 'error')
            print('DEBUG: PC not available or not found')
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
            print('DEBUG: Existing reservation found')
            return redirect(url_for('home'))
        # Create new reservation
        new_reservation = Reservation(
            user_id=user.id,
            date=date,
            time=time,
            purpose=purpose,
            laboratory_unit=laboratory_unit,
            computer_id=pc_id
        )
        # Update computer status to reserved
        computer.status = 'reserved'
        try:
            db.session.add(new_reservation)
            db.session.commit()
            flash('Reservation submitted successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while submitting reservation', 'error')
            print(f"Error submitting reservation: {str(e)}")
        # Redirect to admin reservations if admin, else home
        if user.is_admin:
            return redirect(url_for('admin_reservations'))
        else:
            return redirect(url_for('home'))
    except Exception as e:
        flash('An error occurred while submitting reservation', 'error')
        print(f"Error submitting reservation: {str(e)}")
        return redirect(url_for('home'))

@app.route('/admin/reservations')
@login_required
@admin_required
def admin_reservations():
    # Get all reservations with user information, ordered by date and time, only pending and approved
    reservations = Reservation.query.join(User).filter(Reservation.status.in_(['pending', 'approved'])).order_by(Reservation.date.desc(), Reservation.time.desc()).all()
    # Calculate statistics
    stats = {
        'total': Reservation.query.filter(Reservation.status.in_(['pending', 'approved'])).count(),
        'active': Reservation.query.filter_by(status='approved').count(),
        'pending': Reservation.query.filter_by(status='pending').count()
    }
    # Pass the lab schedule for template use
    schedule = None
    if 'get_lab_schedule' in globals():
        schedule = get_lab_schedule()
    return render_template('admin_reservations.html', reservations=reservations, stats=stats, schedule=schedule)

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
            # --- Automatically start session for student ---
            user = User.query.get(reservation.user_id)
            computer = Computer.query.get(reservation.computer_id)
            if not computer:
                return jsonify({'success': False, 'message': 'Computer not found'}), 404
            if computer.status not in ['vacant', 'reserved']:
                return jsonify({'success': False, 'message': 'Computer is not available'}), 400
            if computer.status == 'reserved':
                # Only block if reserved by another user
                active_reservation = Reservation.query.filter_by(
                    computer_id=computer.id,
                    status='approved'
                ).first()
                if active_reservation and active_reservation.user_id != user.id and reservation.id != active_reservation.id:
                    return jsonify({'success': False, 'message': 'Computer is reserved by another user'}), 400
            if user.remaining_sessions <= 0:
                return jsonify({'success': False, 'message': 'User has no remaining sessions'}), 400
            session_obj = Session(
                user_id=reservation.user_id,
                purpose=reservation.purpose,
                laboratory_unit=reservation.laboratory_unit,
                computer_id=reservation.computer_id,
                start_time=datetime.utcnow()
            )
            computer.status = 'occupied'
            user.remaining_sessions -= 1
            db.session.add(session_obj)
            db.session.delete(reservation)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Reservation approved and session started for student!'})
        else:
            # If rejected, mark as rejected instead of deleting
            reservation.status = 'rejected'
            db.session.commit()
            return jsonify({'success': True, 'message': 'Reservation rejected.'})
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
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
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
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    if not user or not user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('admin_sessions'))
    
    data = request.get_json()
    id_number = data.get('id_number')
    purpose = data.get('purpose')
    laboratory_unit = data.get('laboratory_unit')
    pc_id = data.get('pc_id')
    
    if not all([id_number, purpose, laboratory_unit, pc_id]):
        flash('Missing required fields.', 'error')
        return redirect(url_for('admin_sessions'))
    
    # Find user by ID number
    student = User.query.filter_by(id_number=id_number).first()
    if not student:
        flash('User not found.', 'error')
        return redirect(url_for('admin_sessions'))

    # Prevent sit-in for admin users
    if student.is_admin:
        flash('Admin users are not allowed to sit in.', 'error')
        return redirect(url_for('admin_sessions'))

    # Prevent sit-in if user has a pending reservation
    pending_res = Reservation.query.filter_by(user_id=student.id, status='pending').first()
    if pending_res:
        flash('User has a pending reservation. Cannot start a new sit-in session.', 'error')
        return redirect(url_for('admin_sessions'))

    # Prevent sit-in if user has an active session
    active_session = Session.query.filter_by(user_id=student.id, status='active').first()
    if active_session:
        flash('User already has an active session. Cannot start a new sit-in session.', 'error')
        return redirect(url_for('admin_sessions'))
    
    # Check if user has remaining sessions
    if student.remaining_sessions <= 0:
        flash('User has no remaining sessions.', 'error')
        return redirect(url_for('admin_sessions'))

    # Check if the selected PC is available
    computer = Computer.query.get(pc_id)
    if not computer or computer.status != 'vacant':
        flash('The selected PC is not available.', 'error')
        return redirect(url_for('admin_sessions'))
    
    # Create new session
    session_obj = Session(
        user_id=student.id,
        purpose=purpose,
        laboratory_unit=laboratory_unit,
        computer_id=pc_id
    )
    
    try:
        # Decrement remaining sessions
        student.remaining_sessions -= 1
        # Set computer to occupied
        computer.status = 'occupied'
        db.session.add(session_obj)
        db.session.commit()
        flash('Session started successfully!', 'success')
        return redirect(url_for('admin_sessions'))
    except Exception as e:
        db.session.rollback()
        flash('Error starting session: ' + str(e), 'error')
        return redirect(url_for('admin_sessions'))

@app.route('/admin/sessions/<int:session_id>/end', methods=['POST'])
@login_required
def end_session(session_id):
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    if not user or not user.is_admin:
        return jsonify({'error': 'Access denied. Admin privileges required.'}), 403
    
    lab_session = Session.query.get_or_404(session_id)
    
    if lab_session.status == 'completed':
        return jsonify({'error': 'Session already completed'}), 400
    
    try:
        # Get the computer associated with the session
        computer = Computer.query.get(lab_session.computer_id)
        if computer:
            # Update computer status back to vacant
            computer.status = 'vacant'
        # Check if awarding a point
        award_point = False
        if request.is_json:
            data = request.get_json()
            award_point = data.get('award_point', False)
        elif 'award_point' in request.form:
            award_point = request.form.get('award_point') == 'true'
        lab_session.status = 'completed'
        lab_session.end_time = datetime.utcnow()
        # Award a point if requested
        if award_point:
            student = User.query.get(lab_session.user_id)
            if student:
                student.points += 1
        db.session.commit()
        msg = 'Session ended successfully'
        if award_point:
            msg += ' and point awarded'
        return jsonify({'message': msg}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/sessions/<int:session_id>', methods=['DELETE'])
@login_required
def delete_session(session_id):
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
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
        # Get the user and computer
        user = User.query.get(reservation.user_id)
        computer = Computer.query.get(reservation.computer_id)
        
        if not computer:
            return jsonify({
                'success': False,
                'message': 'Computer not found'
            }), 404
        
        # Check if computer is available (either vacant or reserved by this user)
        if computer.status not in ['vacant', 'reserved']:
            return jsonify({
                'success': False,
                'message': 'Computer is not available'
            }), 400
        
        # If computer is reserved, verify it's reserved by this user
        if computer.status == 'reserved':
            active_reservation = Reservation.query.filter_by(
                computer_id=computer.id,
                status='approved'
            ).first()
            if not active_reservation or active_reservation.user_id != user.id:
                return jsonify({
                    'success': False,
                    'message': 'Computer is reserved by another user'
                }), 400
        
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
            computer_id=reservation.computer_id,
            start_time=datetime.utcnow()
        )
        
        # Update computer status to occupied
        computer.status = 'occupied'
        
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
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    return render_template('admin_reports.html')

@app.route('/admin/export/<report_type>/<format_type>', methods=['POST'])
@login_required
@admin_required
def export_report(report_type, format_type):
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
    end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
    lab_room = request.form.get('lab_room')
    purpose = request.form.get('purpose')
    
    # Get data based on report type, with filters
    if report_type == 'user_activity':
        query = Session.query.filter(
            Session.start_time >= start_date,
            Session.end_time <= end_date
        )
        if lab_room:
            query = query.filter(Session.laboratory_unit == lab_room)
        if purpose:
            query = query.filter(Session.purpose == purpose)
        sessions = query.all()
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
        title = "User Activity Report"
       
    elif report_type == 'lab_usage':
        query = Session.query.filter(
            Session.start_time >= start_date,
            Session.end_time <= end_date
        )
        if lab_room:
            query = query.filter(Session.laboratory_unit == lab_room)
        if purpose:
            query = query.filter(Session.purpose == purpose)
        sessions = query.all()
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
        title = "Laboratory Usage Report"
        description = "This report shows the laboratory usage in the system during the selected date range."
    elif report_type == 'statistics':
        query = Session.query.filter(
            Session.start_time >= start_date,
            Session.end_time <= end_date
        )
        if lab_room:
            query = query.filter(Session.laboratory_unit == lab_room)
        if purpose:
            query = query.filter(Session.purpose == purpose)
        total_sessions = query.count()
        active_sessions = query.filter(Session.status == 'active').count()
        completed_sessions = query.filter(Session.status == 'completed').count()
        purpose_stats = db.session.query(
            Session.purpose,
            db.func.count(Session.id).label('count')
        ).filter(
            Session.start_time >= start_date,
            Session.end_time <= end_date
        )
        if lab_room:
            purpose_stats = purpose_stats.filter(Session.laboratory_unit == lab_room)
        if purpose:
            purpose_stats = purpose_stats.filter(Session.purpose == purpose)
        purpose_stats = purpose_stats.group_by(Session.purpose).all()
        data = {
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
            'completed_sessions': completed_sessions,
            'purpose_stats': [(purpose, count) for purpose, count in purpose_stats]
        }
        title = "Statistics Report"
        description = "This report shows the statistics of the system during the selected date range."
    else:
        flash('Invalid report type', 'error')
        return redirect(url_for('session_history'))
    
    # Generate report in requested format
    if format_type == 'pdf':
        return generate_pdf_report(data, title)
    elif format_type == 'csv':
        return generate_csv_report(data, title)
    elif format_type == 'xml':
        return generate_xml_report(data, title)
    else:
        flash('Invalid format type', 'error')
        return redirect(url_for('session_history'))

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
    elements.append(Paragraph(title, styles['Title']))
    elements.append(Spacer(1, 12))
    # Table data
    if isinstance(data, list):
        if data:
            table_data = [list(data[0].keys())]
            for row in data:
                table_data.append(list(row.values()))
        else:
            # If no data, show headers and a 'No data' row
            table_data = [['No data available']]
        table = Table(table_data, repeatRows=1)
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ])
        table.setStyle(style)
        elements.append(table)
    elif isinstance(data, dict):
        # For statistics report
        stats_table = [
            ['Metric', 'Value'],
            ['Total Sessions', str(data['total_sessions'])],
            ['Active Sessions', str(data['active_sessions'])],
            ['Completed Sessions', str(data['completed_sessions'])]
        ]
        table = Table(stats_table, repeatRows=1)
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ])
        table.setStyle(style)
        elements.append(table)
        elements.append(Spacer(1, 20))
        # Purpose statistics
        if 'purpose_stats' in data:
            elements.append(Paragraph('Purpose Statistics', styles['Heading2']))
            elements.append(Spacer(1, 12))
            purpose_data = [['Purpose', 'Count']] + data['purpose_stats']
            purpose_table = Table(purpose_data, repeatRows=1)
            purpose_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ])
            purpose_table.setStyle(purpose_style)
            elements.append(purpose_table)
            elements.append(Spacer(1, 20))
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
    # Predefined laboratory units with specific room numbers
    laboratories = [
        'Laboratory 524',
        'Laboratory 526',
        'Laboratory 528',
        'Laboratory 530',
        'Laboratory 542',
        'Laboratory 544',
        'Laboratory 517'
    ]
    
    # Get computers for each laboratory
    computers = Computer.query.order_by(Computer.laboratory_unit, Computer.computer_number).all()
    
    # If no computers exist, create default computers for each laboratory
    if not computers:
        for lab in laboratories:
            # Add 50 computers to each laboratory
            for i in range(1, 51):
                computer = Computer(
                    computer_number=f"PC-{i:02d}",  # e.g., "PC-01", "PC-02", etc.
                    laboratory_unit=lab,
                    status='vacant'  # Default status is vacant
                )
                db.session.add(computer)
        
        try:
            db.session.commit()
            flash('Default computers have been added to all laboratories', 'success')
            # Refresh the computers list after adding defaults
            computers = Computer.query.order_by(Computer.laboratory_unit, Computer.computer_number).all()
        except Exception as e:
            db.session.rollback()
            flash('Error adding default computers', 'error')
    
    return render_template('admin_computers.html', 
                         computers=computers,
                         laboratories=laboratories)

@app.route('/admin/computers/add', methods=['POST'])
@login_required
@admin_required
def add_computer():
    computer_number = request.form.get('computer_number')
    laboratory_unit = request.form.get('laboratory_unit')
    
    if not computer_number or not laboratory_unit:
        flash('Computer number and laboratory unit are required', 'error')
        return redirect(url_for('admin_computers'))
    
    # Validate computer number format
    if not computer_number.startswith('PC-') or not computer_number[3:].isdigit():
        flash('Computer number must be in format: PC-01, PC-02, etc.', 'error')
        return redirect(url_for('admin_computers'))
    
    # Check if computer number already exists in the same laboratory
    if Computer.query.filter_by(computer_number=computer_number, laboratory_unit=laboratory_unit).first():
        flash('This PC number already exists in this laboratory', 'error')
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

@app.route('/admin/add-points', methods=['GET'])
@app.route('/admin/users/<int:user_id>/add-points', methods=['GET', 'POST'])
@login_required
@admin_required
def add_points(user_id=None):
    if request.method == 'GET':
        if user_id is None:
            # Show list of all non-admin users
            users = User.query.filter_by(is_admin=False).order_by(User.last_name).all()
            return render_template('add_points.html', users=users)
        else:
            # Show form for specific user
            user = User.query.get_or_404(user_id)
            return render_template('add_points.html', user=user)
    
    # Handle POST request
    points = request.form.get('points', type=int)
    
    if points is None or points <= 0:
        return jsonify({
            'success': False,
            'message': 'Please provide a valid number of points'
        }), 400
    
    try:
        user = User.query.get_or_404(user_id)
        user.points += points
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Added {points} points to {user.first_name} {user.last_name}',
            'new_points': user.points
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error adding points: {str(e)}'
        }), 500

@app.route('/admin/leaderboard')
@login_required
@admin_required
def leaderboard():
    # Get all non-admin users with points greater than 0, ordered by points in descending order
    users = User.query.filter(
        User.is_admin == False,
        User.points > 0
    ).order_by(User.points.desc()).all()
    # Calculate sit-in count for each user
    user_sitin_counts = {}
    from models import Session
    awarded_users = []
    for user in users:
        sitin_count = Session.query.filter_by(user_id=user.id, status='completed').count()
        user_sitin_counts[user.id] = sitin_count
        # Award sessions for every 3 points, but only if not already awarded
        sessions_to_award = user.points // 3 - (user.sessions_awarded_for_points or 0)
        if sessions_to_award > 0:
            user.remaining_sessions += sessions_to_award
            user.sessions_awarded_for_points = (user.sessions_awarded_for_points or 0) + sessions_to_award
            awarded_users.append(f"{user.first_name} {user.last_name} (+{sessions_to_award} session{'s' if sessions_to_award > 1 else ''})")
    if awarded_users:
        db.session.commit()
        flash(f"Awarded extra session(s) to: {', '.join(awarded_users)} (for every 3 points)", 'success')
    # Sort users by points, then by sit-in count
    users = sorted(users, key=lambda u: (u.points, user_sitin_counts[u.id]), reverse=True)
    return render_template('leaderboard.html', users=users, user_sitin_counts=user_sitin_counts)

@app.route('/user/activity-history')
@login_required
def user_activity_history():
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('home'))
    
    # Get all completed sessions for the user
    completed_sessions = Session.query.filter_by(
        user_id=user.id,
        status='completed'
    ).order_by(Session.end_time.desc()).all()
    
    # Get all past reservations (completed or rejected)
    past_reservations = Reservation.query.filter(
        Reservation.user_id == user.id,
        Reservation.status.in_(['completed', 'rejected'])
    ).order_by(Reservation.date.desc(), Reservation.time.desc()).all()
    
    # Calculate statistics
    total_hours = sum((session.end_time - session.start_time).total_seconds() / 3600 for session in completed_sessions)
    total_sessions = len(completed_sessions)
    total_reservations = len(past_reservations)
    
    stats = {
        'total_hours': round(total_hours, 2),
        'total_sessions': total_sessions,
        'total_reservations': total_reservations,
        'remaining_sessions': user.remaining_sessions
    }
    
    return render_template('history.html',
                         sessions=completed_sessions,
                         reservations=past_reservations,
                         stats=stats)

# Store the schedule in a global variable for demo edit functionality
SCHEDULE_DATA = None

@app.route('/admin/lab-schedule', methods=['GET'])
@login_required
@admin_required
def admin_lab_schedule():
    global SCHEDULE_DATA
    labs = [
        'Laboratory 517', 'Laboratory 524', 'Laboratory 526',
        'Laboratory 528', 'Laboratory 530', 'Laboratory 542', 'Laboratory 544'
    ]
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    times = [
        '7:00-8:00', '8:00-9:00', '9:00-10:00', '10:00-11:00',
        '11:00-12:00', '12:00-1:00', '1:00-2:00', '2:00-3:00', '3:00-4:00'
    ]
    # Initialize or use global schedule
    if SCHEDULE_DATA is None:
        SCHEDULE_DATA = {lab: {day: {time: None for time in times} for day in days} for lab in labs}
        SCHEDULE_DATA['Laboratory 517']['Monday']['8:00-9:00'] = {'course': 'BIOLOG', 'instructor': 'M. Magsino'}
        SCHEDULE_DATA['Laboratory 517']['Tuesday']['8:00-9:00'] = {'course': 'COMP PROG', 'instructor': 'M. Magsino'}
        SCHEDULE_DATA['Laboratory 524']['Wednesday']['9:00-10:00'] = {'course': 'PHYSICS', 'instructor': 'J. Santos'}
        SCHEDULE_DATA['Laboratory 526']['Thursday']['10:00-11:00'] = {'course': 'CHEMISTRY', 'instructor': 'A. Cruz'}
    selected_lab = request.args.get('lab', labs[0])
    return render_template(
        'lab_schedule.html',
        labs=labs,
        selected_lab=selected_lab,
        days=days,
        times=times,
        schedule=SCHEDULE_DATA
    )

@app.route('/admin/lab-schedule/edit', methods=['POST'])
@login_required
@admin_required
def edit_lab_schedule():
    global SCHEDULE_DATA
    lab = request.form['lab']
    day = request.form['day']
    time = request.form['time']
    course = request.form['course']
    instructor = request.form['instructor']
    # Update the schedule in memory
    if SCHEDULE_DATA and lab in SCHEDULE_DATA and day in SCHEDULE_DATA[lab] and time in SCHEDULE_DATA[lab][day]:
        SCHEDULE_DATA[lab][day][time] = {'course': course, 'instructor': instructor}
        flash('Schedule updated!', 'success')
    else:
        flash('Invalid schedule update.', 'error')
    return redirect(url_for('admin_lab_schedule', lab=lab))

@app.route('/admin/export/lab_schedule/<format_type>', methods=['POST'])
@login_required
@admin_required
def export_lab_schedule(format_type):
    global SCHEDULE_DATA
    lab = request.form.get('lab')
    # Ensure SCHEDULE_DATA is initialized
    if SCHEDULE_DATA is None:
        labs = [
            'Laboratory 517', 'Laboratory 524', 'Laboratory 526',
            'Laboratory 528', 'Laboratory 530', 'Laboratory 542', 'Laboratory 544'
        ]
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        times = [
            '7:00-8:00', '8:00-9:00', '9:00-10:00', '10:00-11:00',
            '11:00-12:00', '12:00-1:00', '1:00-2:00', '2:00-3:00', '3:00-4:00'
        ]
        SCHEDULE_DATA = {lab: {day: {time: None for time in times} for day in days} for lab in labs}
        SCHEDULE_DATA['Laboratory 517']['Monday']['8:00-9:00'] = {'course': 'BIOLOG', 'instructor': 'M. Magsino'}
        SCHEDULE_DATA['Laboratory 517']['Tuesday']['8:00-9:00'] = {'course': 'COMP PROG', 'instructor': 'M. Magsino'}
        SCHEDULE_DATA['Laboratory 524']['Wednesday']['9:00-10:00'] = {'course': 'PHYSICS', 'instructor': 'J. Santos'}
        SCHEDULE_DATA['Laboratory 526']['Thursday']['10:00-11:00'] = {'course': 'CHEMISTRY', 'instructor': 'A. Cruz'}
    data = []
    labs = [lab] if lab and lab in SCHEDULE_DATA else list(SCHEDULE_DATA.keys())
    for lab_name in labs:
        for day, timeslots in SCHEDULE_DATA[lab_name].items():
            for time, slot in timeslots.items():
                course = slot['course'] if slot else ''
                instructor = slot['instructor'] if slot else ''
                data.append({
                    'Laboratory': lab_name,
                    'Day': day,
                    'Time': time,
                    'Course': course,
                    'Instructor': instructor
                })
    if format_type == 'csv':
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=['Laboratory', 'Day', 'Time', 'Course', 'Instructor'])
        writer.writeheader()
        for row in data:
            writer.writerow(row)
        output.seek(0)
        return send_file(
            BytesIO(output.getvalue().encode()),
            as_attachment=True,
            download_name='lab_schedule.csv',
            mimetype='text/csv'
        )
    elif format_type == 'xml':
        root = ET.Element('LabSchedule')
        for row in data:
            entry = ET.SubElement(root, 'Entry')
            for key, value in row.items():
                ET.SubElement(entry, key).text = value
        tree = ET.ElementTree(root)
        output = StringIO()
        tree.write(output, encoding='unicode', xml_declaration=True)
        output.seek(0)
        return send_file(
            BytesIO(output.getvalue().encode()),
            as_attachment=True,
            download_name='lab_schedule.xml',
            mimetype='application/xml'
        )
    elif format_type == 'pdf':
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []
        # If exporting all labs, do a table per lab
        labs_to_export = labs
        for lab_name in labs_to_export:
            elements.append(Paragraph('Laboratory Schedule', styles['Title']))
            elements.append(Paragraph(f'Room: {lab_name}', styles['Heading2']))
            elements.append(Spacer(1, 12))
            # Get all days and times
            days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            times = [
                '7:00-8:00', '8:00-9:00', '9:00-10:00', '10:00-11:00',
                '11:00-12:00', '12:00-1:00', '1:00-2:00', '2:00-3:00', '3:00-4:00'
            ]
            # Table header
            table_data = [['Time'] + days]
            # Table rows
            for time in times:
                row = [time]
                for day in days:
                    slot = SCHEDULE_DATA[lab_name][day][time]
                    if slot and slot.get('course'):
                        cell = f"{slot['course']}\n{slot['instructor']}\n{time}"
                    else:
                        cell = 'Vacant Time'
                    row.append(cell)
                table_data.append(row)
            # Create table
            table = Table(table_data, repeatRows=1)
            # Style
            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ])
            # Green background for 'Vacant Time'
            for row_idx in range(1, len(table_data)):
                for col_idx in range(1, len(days)+1):
                    if table_data[row_idx][col_idx] == 'Vacant Time':
                        style.add('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), colors.HexColor('#b9fbc0'))
            table.setStyle(style)
            elements.append(table)
            elements.append(Spacer(1, 24))
        doc.build(elements)
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name='lab_schedule.pdf',
            mimetype='application/pdf'
        )
    else:
        return 'Invalid format', 400

@app.route('/admin/daily-sitin-record')
@login_required
@admin_required
def daily_sitin_record():
    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    end = datetime.combine(today, datetime.max.time())
    sessions = Session.query.filter(
        Session.status == 'completed',
        Session.end_time >= start,
        Session.end_time <= end
    ).order_by(Session.end_time.desc()).all()
    # Serialize only the fields needed for the pie chart
    sessions_json = [{"purpose": s.purpose} for s in sessions]
    return render_template('daily_sitin_record.html', sessions=sessions, sessions_json=sessions_json)

@app.route('/admin/computers/set_all_status', methods=['POST'])
@login_required
@admin_required
def set_all_computer_status():
    data = request.get_json()
    status = data.get('status')
    if status not in ['vacant', 'occupied']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    try:
        Computer.query.update({Computer.status: status})
        db.session.commit()
        return jsonify({'success': True, 'message': f'All PCs set to {status}.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

def is_lab_available(lab_number, date, time):
    """Check if a lab is available at the given date and time."""
    # Convert date to day of week
    day = date.strftime('%A')
    
    # Get the lab schedule
    schedule = get_lab_schedule()
    
    # Check if the lab is scheduled for a class at this time
    if lab_number in schedule and day in schedule[lab_number]:
        if time in schedule[lab_number][day]:
            slot = schedule[lab_number][day][time]
            if slot and slot.get('course'):
                return False
    
    return True

@app.route('/create_sit_in', methods=['POST'])
@login_required
def create_sit_in():
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    if not user or not user.is_admin:
        flash('Unauthorized access', 'error')
        return redirect(url_for('home'))
    
    student_id = request.form.get('student_id')
    lab_number = request.form.get('lab_number')
    pc_number = request.form.get('pc_number')
    purpose = request.form.get('purpose')
    
    # Get current date and time
    now = datetime.now()
    current_time = now.strftime('%I:%M %p')
    
    # Check if lab is available
    if not is_lab_available(lab_number, now, current_time):
        flash('Lab is currently scheduled for a class', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Prevent sit-in for admin users
    student = User.query.filter_by(id_number=student_id).first()
    if student and student.is_admin:
        flash('Admin users are not allowed to sit in.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if student:
        pending_res = Reservation.query.filter_by(user_id=student.id, status='pending').first()
        if pending_res:
            flash('User has a pending reservation. Cannot start a new sit-in session.', 'error')
            return redirect(url_for('admin_dashboard'))
        active_session = Session.query.filter_by(user_id=student.id, status='active').first()
        if active_session:
            flash('User already has an active session. Cannot start a new sit-in session.', 'error')
            return redirect(url_for('admin_dashboard'))
    
    # Create new session
    session = Session(
        student_id=student_id,
        lab_number=lab_number,
        pc_number=pc_number,
        purpose=purpose,
        start_time=now
    )
    
    db.session.add(session)
    db.session.commit()
    
    flash('Sit-in session created successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/reserve', methods=['POST'])
@login_required
def reserve():
    user = User.query.filter_by(id_number=flask_session['user_id']).first()
    lab_number = request.form.get('lab_number')
    pc_number = request.form.get('pc_number')
    date = request.form.get('date')
    time = request.form.get('time')
    
    # Convert date string to datetime object
    reservation_date = datetime.strptime(date, '%Y-%m-%d')
    
    # Check if lab is available
    if not is_lab_available(lab_number, reservation_date, time):
        flash('Lab is scheduled for a class at the selected time', 'error')
        return redirect(url_for('home'))
    
    # Create new reservation
    reservation = Reservation(
        student_id=user.id,
        lab_number=lab_number,
        pc_number=pc_number,
        date=reservation_date,
        time=time,
        status='pending'
    )
    
    db.session.add(reservation)
    db.session.commit()
    
    flash('Reservation request submitted successfully', 'success')
    return redirect(url_for('home'))

@app.route('/check_lab_availability')
@login_required
def check_lab_availability():
    lab = request.args.get('lab')
    date_str = request.args.get('date')
    time = request.args.get('time')
    
    if not all([lab, date_str, time]):
        return jsonify({'error': 'Missing parameters'}), 400
    
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        available = is_lab_available(lab, date, time)
        return jsonify({'available': available})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/get_available_times')
@login_required
def get_available_times():
    lab = request.args.get('laboratory')
    computer_id = request.args.get('computer_id')
    date_str = request.args.get('date')
    if not all([lab, computer_id, date_str]):
        return jsonify({'success': False, 'message': 'Missing parameters'}), 400
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        # Define all possible time slots (should match your system)
        times = [
            '7:00-8:00', '8:00-9:00', '9:00-10:00', '10:00-11:00',
            '11:00-12:00', '12:00-1:00', '1:00-2:00', '2:00-3:00', '3:00-4:00'
        ]
        # Get reservations for this lab, PC, and date
        reserved_times = set(
            r.time.strftime('%H:%M') if hasattr(r.time, 'strftime') else str(r.time)
            for r in Reservation.query.filter_by(laboratory_unit=lab, computer_id=computer_id, date=date_obj).all()
        )
        # Get scheduled classes for this lab and date (day of week)
        day = date_obj.strftime('%A')
        scheduled_times = set()
        schedule = get_lab_schedule() if 'get_lab_schedule' in globals() else None
        if schedule and lab in schedule and day in schedule[lab]:
            for t in times:
                slot = schedule[lab][day][t]
                if slot and slot.get('course'):
                    scheduled_times.add(t)
        # Only return times not reserved and not scheduled
        available_times = [t for t in times if t not in reserved_times and t not in scheduled_times]
        return jsonify({'success': True, 'times': available_times})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# Add this function near the top, after SCHEDULE_DATA is defined

def get_lab_schedule():
    global SCHEDULE_DATA
    return SCHEDULE_DATA

# Replace all current_user references with session-based user lookup
# Example: Replace 'current_user.id' with 'user.id' where user is fetched from session
# (No code output for replacements, as this is a comment for the edit model)

@app.route('/admin/logs')
@login_required
@admin_required
def admin_logs():
    # Fetch all sessions and reservations, join with User and Computer
    sessions = Session.query.join(User).join(Computer).order_by(Session.start_time.desc()).all()
    reservations = Reservation.query.join(User).join(Computer).order_by(Reservation.date.desc(), Reservation.time.desc()).all()
    return render_template('admin_logs.html', sessions=sessions, reservations=reservations)

@app.route('/resources/<int:resource_id>/download')
@login_required
def user_download_resource_file(resource_id):
    resource = LabResource.query.get_or_404(resource_id)
    if not resource.file_path:
        flash('No file available for this resource.', 'error')
        return redirect(url_for('user_resources'))
    filename = resource.file_path.split('/')[-1]
    directory = os.path.join(app.static_folder, 'uploads', 'resources')
    try:
        return send_from_directory(directory, filename, as_attachment=True)
    except Exception as e:
        flash('Error downloading file.', 'error')
        return redirect(url_for('user_resources'))

if __name__ == '__main__':
    init_db()  # Initialize database and create admin user
    app.run(debug=True) 