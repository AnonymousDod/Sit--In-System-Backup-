from app import app, db

with app.app_context():
    try:
        db.engine.execute('ALTER TABLE feedback ADD COLUMN session_id INTEGER')
        print("Added session_id column to feedback table.")
    except Exception as e:
        print(f"Migration failed: {e}") 