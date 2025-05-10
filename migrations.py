from app import app, db
from models import User, Reservation

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
        
        # Add points column if it doesn't exist
        try:
            db.engine.execute('ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0')
            print("Added points column to users table")
        except Exception as e:
            print(f"Column points may already exist: {str(e)}")
        
        db.session.commit()

def migrate():
    with app.app_context():
        # Add computer_id column to reservation table
        try:
            # Create a temporary table with the new schema
            db.engine.execute('''
                CREATE TABLE reservation_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    time TIME NOT NULL,
                    purpose VARCHAR(100) NOT NULL,
                    laboratory_unit VARCHAR(50) NOT NULL,
                    computer_id INTEGER NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (computer_id) REFERENCES computers (id)
                )
            ''')

            # Copy data from old table to new table
            db.engine.execute('''
                INSERT INTO reservation_new (id, user_id, date, time, purpose, laboratory_unit, status, created_at)
                SELECT id, user_id, date, time, purpose, laboratory_unit, status, created_at
                FROM reservation
            ''')

            # Drop old table
            db.engine.execute('DROP TABLE reservation')

            # Rename new table to original name
            db.engine.execute('ALTER TABLE reservation_new RENAME TO reservation')

            print("Migration completed successfully!")
        except Exception as e:
            print(f"Error during migration: {str(e)}")
            # Rollback changes if something goes wrong
            db.engine.execute('DROP TABLE IF EXISTS reservation_new')

def migrate_sessions():
    with app.app_context():
        try:
            # Create a temporary table with the new schema
            db.engine.execute('''
                CREATE TABLE session_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    purpose VARCHAR(100) NOT NULL,
                    laboratory_unit VARCHAR(50) NOT NULL,
                    computer_id INTEGER NOT NULL,
                    start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    end_time DATETIME,
                    status VARCHAR(20) DEFAULT 'active',
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (computer_id) REFERENCES computers (id)
                )
            ''')

            # Copy data from old table to new table
            db.engine.execute('''
                INSERT INTO session_new (id, user_id, purpose, laboratory_unit, start_time, end_time, status)
                SELECT id, user_id, purpose, laboratory_unit, start_time, end_time, status
                FROM session
            ''')

            # Drop old table
            db.engine.execute('DROP TABLE session')

            # Rename new table to original name
            db.engine.execute('ALTER TABLE session_new RENAME TO session')

            print("Sessions migration completed successfully!")
        except Exception as e:
            print(f"Error during sessions migration: {str(e)}")
            # Rollback changes if something goes wrong
            db.engine.execute('DROP TABLE IF EXISTS session_new')

def add_total_points_column():
    with app.app_context():
        try:
            db.engine.execute('ALTER TABLE users ADD COLUMN total_points INTEGER DEFAULT 0')
            print("Added total_points column to users table")
        except Exception as e:
            print(f"Column total_points may already exist: {str(e)}")

def add_sessions_awarded_for_points_column():
    with app.app_context():
        try:
            db.engine.execute('ALTER TABLE users ADD COLUMN sessions_awarded_for_points INTEGER DEFAULT 0')
            print("Added sessions_awarded_for_points column to users table")
        except Exception as e:
            print(f"Column sessions_awarded_for_points may already exist: {str(e)}")

def migrate_computer_unique_constraint():
    with app.app_context():
        # Create new table with correct constraints
        db.engine.execute('''
            CREATE TABLE computers_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                computer_number VARCHAR(20) NOT NULL,
                status VARCHAR(20) DEFAULT 'vacant',
                laboratory_unit VARCHAR(100) NOT NULL,
                last_updated DATETIME,
                UNIQUE(computer_number, laboratory_unit)
            )
        ''')
        # Copy data
        db.engine.execute('''
            INSERT INTO computers_new (id, computer_number, status, laboratory_unit, last_updated)
            SELECT id, computer_number, status, laboratory_unit, last_updated FROM computers
        ''')
        # Drop old table
        db.engine.execute('DROP TABLE computers')
        # Rename new table
        db.engine.execute('ALTER TABLE computers_new RENAME TO computers')
        print('Migration complete: unique constraint is now on (computer_number, laboratory_unit)')

def add_lab_pc_to_notification():
    with app.app_context():
        try:
            db.engine.execute('ALTER TABLE notification ADD COLUMN lab VARCHAR(100)')
            print("Added lab column to notification table")
        except Exception as e:
            print(f"Column lab may already exist: {str(e)}")
        try:
            db.engine.execute('ALTER TABLE notification ADD COLUMN pc VARCHAR(100)')
            print("Added pc column to notification table")
        except Exception as e:
            print(f"Column pc may already exist: {str(e)}")

def add_is_manual_to_sessions():
    with app.app_context():
        try:
            db.engine.execute('ALTER TABLE session ADD COLUMN is_manual BOOLEAN DEFAULT FALSE')
            print("Added is_manual column to session table")
        except Exception as e:
            print(f"Column is_manual may already exist: {str(e)}")

if __name__ == '__main__':
    add_missing_columns()
    migrate()
    migrate_sessions()
    add_total_points_column()
    add_sessions_awarded_for_points_column()
    migrate_computer_unique_constraint()
    add_lab_pc_to_notification()
    add_is_manual_to_sessions() 