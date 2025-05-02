from app import app, db
from models import User
from werkzeug.security import generate_password_hash

def init_database():
    with app.app_context():
        # Drop all tables and recreate them
        db.drop_all()
        db.create_all()
        
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
            points=0
        )
        db.session.add(admin)
        db.session.commit()
        print("Database initialized successfully!")

if __name__ == '__main__':
    init_database() 