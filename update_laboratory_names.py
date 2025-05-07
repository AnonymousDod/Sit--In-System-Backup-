from app import app, db
from models import Computer

# Map old names to new names
lab_name_map = {
    "Laboratory 524 - Programming Lab": "Laboratory 524",
    "Laboratory 526 - Networking Lab": "Laboratory 526",
    "Laboratory 528 - Hardware Lab": "Laboratory 528",
    "Laboratory 530 - Multimedia Lab": "Laboratory 530",
    "Laboratory 542 - Research Lab": "Laboratory 542",
    "Laboratory 544 - Project Lab": "Laboratory 544",
    "Laboratory 517 - Special Lab": "Laboratory 517"
}

with app.app_context():
    updated = 0
    for old, new in lab_name_map.items():
        computers = Computer.query.filter_by(laboratory_unit=old).all()
        for computer in computers:
            computer.laboratory_unit = new
            updated += 1
    db.session.commit()
    print(f"Updated {updated} computer records.") 