from app import app, db
import sqlite3

def migrate_resources():
    with app.app_context():
        try:
            # Connect to the SQLite database
            conn = sqlite3.connect('student_portal.db')
            cursor = conn.cursor()
            
            # Add new columns if they don't exist
            cursor.execute("PRAGMA table_info(lab_resource)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'file_path' not in columns:
                cursor.execute("ALTER TABLE lab_resource ADD COLUMN file_path VARCHAR(500)")
                print("Added file_path column")
            
            if 'file_type' not in columns:
                cursor.execute("ALTER TABLE lab_resource ADD COLUMN file_type VARCHAR(50)")
                print("Added file_type column")
            
            # Commit the changes
            conn.commit()
            print("Migration completed successfully!")
            
        except Exception as e:
            print(f"Error during migration: {str(e)}")
            conn.rollback()
        finally:
            conn.close()

if __name__ == '__main__':
    migrate_resources() 