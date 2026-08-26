from sqlmodel import Session, select
from db.database import engine
from db.models import Branch

branches_data = [
    {"name": "Izza – Showroom", "address": "+998 78 777 77 00"},
    {"name": "Malika bozori, A3-do'kon", "address": "+998 78 777 77 00"},
    {"name": "O'rikzor bozori, 5-blok, C15-do'kon", "address": "+998 78 777 77 00"},
    {"name": "O'rikzor bozori, 5-blok, 60-do'kon", "address": "+998 78 777 77 00"},
    {"name": "Abusaxiy bozori, E111-do'kon", "address": "+998 78 777 77 00"},
    {"name": "Shahrisabz filiali", "address": "+998 78 777 77 00"},
    {"name": "Namangan filiali", "address": "+998 78 777 77 00"},
    {"name": "Buxoro filiali", "address": "+998 78 777 77 00"},
    {"name": "Qarshi filiali", "address": "+998 78 777 77 00"},
    {"name": "Outlet", "address": "+998 78 777 77 00"}
]

def seed_branches():
    with Session(engine) as session:
        for b in branches_data:
            existing = session.exec(select(Branch).where(Branch.name == b["name"])).first()
            if not existing:
                branch = Branch(name=b["name"], address=b["address"])
                session.add(branch)
        session.commit()
        print("Barcha filiallar bazaga muvaffaqiyatli qo'shildi!")

if __name__ == "__main__":
    seed_branches()