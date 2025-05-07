from app import app, db
from models import Session

# Mapping from old purposes to new categories
purpose_map = {
    'assignment': 'C Programming',
    'project': 'Java Programming',
    'research': 'Python Programming',
    'practice': 'C# Programming',
    # Add more mappings if needed
}

with app.app_context():
    updated = 0
    for old, new in purpose_map.items():
        sessions = Session.query.filter_by(purpose=old).all()
        for s in sessions:
            s.purpose = new
            updated += 1
    db.session.commit()
    print(f"Updated {updated} session records.") 