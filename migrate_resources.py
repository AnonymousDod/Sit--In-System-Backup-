from app import app, db
import sqlite3
import os

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

def fix_resource_file_paths():
    from app import db, LabResource
    import os
    
    with app.app_context():
        resources = LabResource.query.all()
        changed = 0
        for resource in resources:
            if resource.file_path:
                fixed_path = resource.file_path.replace('\\', '/')
                if not fixed_path.startswith('uploads/resources/'):
                    filename = os.path.basename(fixed_path)
                    fixed_path = f'uploads/resources/{filename}'
                full_path = os.path.join('static', 'uploads', 'resources', os.path.basename(fixed_path))
                if os.path.exists(full_path):
                    if resource.file_path != fixed_path:
                        resource.file_path = fixed_path
                        changed += 1
        if changed > 0:
            db.session.commit()
            print(f"Fixed {changed} resource file_path entries.")
        else:
            print("No file_path entries needed fixing.")

if __name__ == '__main__':
    migrate_resources()
    fix_resource_file_paths() 