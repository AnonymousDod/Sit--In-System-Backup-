from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
from werkzeug.utils import secure_filename
from models import db, User, Feedback, Announcement
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

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
    active_reservations = 0  # You'll implement this with actual reservations
    total_reservations = 0  # You'll implement this with actual reservations
    
    # Sample announcements (you'll implement this with a database model later)
    announcements = [
        {
            'title': 'System Maintenance',
            'content': 'The laboratory system will undergo maintenance on Saturday.',
            'type': 'Normal',
            'timestamp': 'Apr 11, 02:59 AM'
        },
        {
            'title': 'New Laboratory Rules',
            'content': 'Please check the updated laboratory rules and guidelines.',
            'type': 'Normal',
            'timestamp': 'Apr 10, 10:30 AM'
        }
    ]
    
    return render_template('admin_dashboard.html',
                         total_users=total_users,
                         active_reservations=active_reservations,
                         total_reservations=total_reservations,
                         announcements=announcements)

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

if __name__ == '__main__':
    init_db()  # Initialize database and create admin user
    app.run(debug=True) 