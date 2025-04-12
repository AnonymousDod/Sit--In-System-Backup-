from app import app, db
from models import User

def add_missing_columns():
    with app.app_context():
        # Add is_active column if it doesn't exist
        try:
            db.engine.execute('ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE')
            print("Added is_active column to users table")
        except Exception as e:
            print(f"Column is_active may already exist: {str(e)}")
        
        # Add remaining_sessions column if it doesn't exist
        try:
            db.engine.execute('ALTER TABLE users ADD COLUMN remaining_sessions INTEGER DEFAULT 30')
            print("Added remaining_sessions column to users table")
        except Exception as e:
            print(f"Column remaining_sessions may already exist: {str(e)}")
        
        db.session.commit()

if __name__ == '__main__':
    add_missing_columns() 