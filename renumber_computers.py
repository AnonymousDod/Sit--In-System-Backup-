from app import app, db
from models import Computer

def renumber_computers():
    with app.app_context():
        labs = [
            'Laboratory 524',
            'Laboratory 526',
            'Laboratory 528',
            'Laboratory 530',
            'Laboratory 542',
            'Laboratory 544',
            'Laboratory 517'
        ]
        for lab in labs:
            computers = Computer.query.filter_by(laboratory_unit=lab).order_by(Computer.id).all()
            for idx, computer in enumerate(computers, start=1):
                computer.computer_number = f"PC-{idx:02d}"
        db.session.commit()
        print("All computers renumbered to PC-01 ... PC-50 per lab.")

if __name__ == "__main__":
    renumber_computers() 