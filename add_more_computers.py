from app import app, db
from models import Computer

labs = [
    'Laboratory 524',
    'Laboratory 526',
    'Laboratory 528',
    'Laboratory 530',
    'Laboratory 542',
    'Laboratory 544',
    'Laboratory 517'
]

with app.app_context():
    added = 0
    for lab in labs:
        for i in range(11, 51):
            computer_number = f"{lab.split()[1]}-{i:02d}"
            # Only add if it doesn't already exist
            if not Computer.query.filter_by(computer_number=computer_number, laboratory_unit=lab).first():
                computer = Computer(
                    computer_number=computer_number,
                    laboratory_unit=lab,
                    status='vacant'
                )
                db.session.add(computer)
                added += 1
    db.session.commit()
    print(f"Added {added} new computers.") 