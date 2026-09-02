from __future__ import annotations

from sqlmodel import Session, select

from db.database import engine
from db.models import Branch, Vacancy


VACANCIES = [
    {
        "title": "Senior Python Backend Developer",
        "department": "IT & AI",
        "branch": "Toshkent",
        "region": "Toshkent",
        "category": "Backend",
        "description": "FastAPI, PostgreSQL va async xizmatlar ustida ishlash, API va integratsiyalarni takomillashtirish.",
        "hard_skill_q1": "FastAPI va Pydantic yordamida qanday API arxitekturasi tuzasiz?",
        "hard_skill_q2": "Asinxron ishlov berish va DB connection pool management bo'yicha tajribangiz qanday?",
        "soft_skill_q1": "Jamoada kelishmovchilik yuzaga kelganda muammolarni qanday hal qilasiz?",
        "soft_skill_q2": "Muddatga rioya qilishda prioritizatsiyani qanday belgilaysiz?",
    },
    {
        "title": "Frontend Developer",
        "department": "IT & AI",
        "branch": "Samarqand",
        "region": "Samarqand",
        "category": "Frontend",
        "description": "Tailwind, JavaScript va responsive UI komponentlar ustida ishlash.",
        "hard_skill_q1": "Responsive dizayn va accessibility tamoyillarini qayerda qo'llaysiz?",
        "hard_skill_q2": "State management va API integratsiya jarayonini qanday boshqarasiz?",
        "soft_skill_q1": "Fikrlar farq qilganda qanday konstruktiv muloqot qilasiz?",
        "soft_skill_q2": "Deadline yaqinlashganda ishlarni qanday prioritetlashtirasiz?",
    },
    {
        "title": "AI/ML Engineer",
        "department": "IT & AI",
        "branch": "Toshkent",
        "region": "Toshkent",
        "category": "AI",
        "description": "LLM, prompt pipelines va ML xizmatlarini ishlab chiqish va integratsiya qilish.",
        "hard_skill_q1": "Prompt engineering va eval metrics qanday ishlaydi?",
        "hard_skill_q2": "Model monitoring va drift kuzatuvi uchun nima qilish kerak?",
        "soft_skill_q1": "Eksperimental natijalar noaniq bo'lganda qanday qaror qabul qilasiz?",
        "soft_skill_q2": "Katta ma'lumotlar va model xizmatlarini prodga tayyorlashda qanday yondashasiz?",
    },
    {
        "title": "Data Analyst",
        "department": "IT & AI",
        "branch": "Farg'ona",
        "region": "Farg'ona",
        "category": "Analytics",
        "description": "Metrika, KPI dashboards va biznes nutqini SQL/BI orqali hamkorlarga yetkazish.",
        "hard_skill_q1": "SQL so'rovlarini tashkil qilishda qanday optimizatsiya qilasiz?",
        "hard_skill_q2": "Metrikani tanlash va dashboard dizaynida qaysi tamoyillar muhim?",
        "soft_skill_q1": "Biznes ehtiyojlarini tushunishda qanday savollar berasiz?",
        "soft_skill_q2": "Ma'lumotlarning ishonchliligini tekshirishda qanday yondashasiz?",
    },
    {
        "title": "Savdo Sotuv Menejeri",
        "department": "Sales & Retail",
        "branch": "Buxoro",
        "region": "Buxoro",
        "category": "Sales",
        "description": "Mijozlar bilan ishlash, savdo reja va ko'rsatkichlar ustida ishlash.",
        "hard_skill_q1": "Savdo maqsadlarini rejalashtirishda qanday yondashasiz?",
        "hard_skill_q2": "Mijozlar bilan ishlashda qanday effektli yakuniy savdo strategiyasi qo'llaysiz?",
        "soft_skill_q1": "Mijozdan rad javob kelganda qanday munosabatda bo'lasiz?",
        "soft_skill_q2": "Jamoada maqsadlar bir-biriga mos kelmasa qanday harakat qilasiz?",
    },
    {
        "title": "Filial Mudiri",
        "department": "Sales & Retail",
        "branch": "Toshkent",
        "region": "Toshkent",
        "category": "Operations",
        "description": "Filial faoliyatini boshqarish, xodimlar va KPI natijalarini nazorat qilish.",
        "hard_skill_q1": "Filial maqsadlarini ishlash ko'rsatkichlari bilan qanday bog'layapsiz?",
        "hard_skill_q2": "Xodimlar samaradorligini baholashda qaysi ko'rsatkichlar muhim?",
        "soft_skill_q1": "Muvaffaqiyatsizlik bo'lganda jamoani motivatsiya qilish usullarini qanday qo'llaysiz?",
        "soft_skill_q2": "Resurs cheklangan holatlarda prioritizatsiya qanday bo'ladi?",
    },
    {
        "title": "Kassa Operatori",
        "department": "Sales & Retail",
        "branch": "Samarqand",
        "region": "Samarqand",
        "category": "Retail",
        "description": "Kassa va mijozlarga xizmat ko'rsatish bo'yicha ishlash, hisob-kitoblarni yuritish.",
        "hard_skill_q1": "Kassa hisobi va oylik hisobotlarni qanday yuritishni bilasiz?",
        "hard_skill_q2": "Mijoz bilan tezkor muammolarni hal qilishda qanday yondashasiz?",
        "soft_skill_q1": "Qaytariladigan muammolar bo'lganda qanday tinch va ijobiy munosabatda bo'lasiz?",
        "soft_skill_q2": "Xavfsizlik va ish qoidalariga rioya qilishdagi mas'uliyatlaringiz?",
    },
    {
        "title": "Sotuv Maslahatchisi",
        "department": "Sales & Retail",
        "branch": "Andijon",
        "region": "Andijon",
        "category": "Sales",
        "description": "Mijozlar bilan konsultatsiya va mahsulotlar bo'yicha savdo ko'nikmalarini qo'llash.",
        "hard_skill_q1": "Mijoz ehtiyojini aniqlashda qanday savollar berasiz?",
        "hard_skill_q2": "Mahsulotni sotuvga moslashtirishda qaysi faktorlarga e'tibor berasiz?",
        "soft_skill_q1": "Mijozning qarshilik ko'rsatgan holatida nima qilasiz?",
        "soft_skill_q2": "Sotuv natijasini yomon bo'lganda qanday o'rganish va yaxshilashga harakat qilasiz?",
    },
    {
        "title": "HR Biznes Hamkor",
        "department": "HR & Admin",
        "branch": "Toshkent",
        "region": "Toshkent",
        "category": "HR",
        "description": "HR jarayonlari, ishga qabul qilish va bo'limlar bilan ishlash.",
        "hard_skill_q1": "Ishga qabul jarayonini qanday tashkil qilasiz?",
        "hard_skill_q2": "Intervyu va tanlov bosqichlarida qanday me'yorlarga e'tibor berasiz?",
        "soft_skill_q1": "Konfidensial ma'lumotlar bilan ishlashda qanday ehtiyot bo'lasiz?",
        "soft_skill_q2": "Ko'p so'rovli va tezkor ish muhitida qanday faoliyat ko'rasiz?",
    },
    {
        "title": "Rekruter",
        "department": "HR & Admin",
        "branch": "Toshkent",
        "region": "Toshkent",
        "category": "Recruitment",
        "description": "Kandidatlarga qarash, tanlov va kompaniya ehtiyojlariga javob beruvchi jarayonlarni boshqarish.",
        "hard_skill_q1": "Kandidate profilini va tajribasini qanday baholayapsiz?",
        "hard_skill_q2": "Candidate funnelni optimallashtirishda qaysi ko'rsatkichlar muhim?",
        "soft_skill_q1": "Kandidatlarga nolil munosabatda ishonch uyg'otasizmi?",
        "soft_skill_q2": "Ko'p kiruvchi xavflar va vaqt bosimi ostida qanday ishlaysiz?",
    },
    {
        "title": "Bosh Buxgalter",
        "department": "HR & Admin",
        "branch": "Toshkent",
        "region": "Toshkent",
        "category": "Finance",
        "description": "Hisob-kitob, byudjet va ichki nazorat tizimini yuritish.",
        "hard_skill_q1": "Hisob va operatsion xarajatlarni nazorat qilishda qanday yondashasiz?",
        "hard_skill_q2": "Buxgalteriya tizimi va reporting jarayonlarini qanday boshqarasiz?",
        "soft_skill_q1": "Katta ma'lumotli vaziyatlarda qaysi xususiyatlar muhim?",
        "soft_skill_q2": "Jamoa ichida qo'shimcha axborot almashinuvini qanday tashkil qilasiz?",
    },
    {
        "title": "Mijozlarga Xizmat Ko'rsatish Mutaxassisi",
        "department": "Operations",
        "branch": "Namangan",
        "region": "Namangan",
        "category": "Customer Service",
        "description": "Mijozlarga xizmat ko'rsatish, muammolarni hal qilish va operatsion jarayonlarni yengillashtirish.",
        "hard_skill_q1": "Mijoz muammosini tezda aniqlash va yechimga olib kelishda qanday yondashasiz?",
        "hard_skill_q2": "CRM va xizmat ko'rsatish kanallarini qanday samarali ishlatasiz?",
        "soft_skill_q1": "Qisqa va qizg'in muloqotda hissiy intellektni qanday qo'llaysiz?",
        "soft_skill_q2": "Mijozlar shikoyatlari bilan ishlashda qanday muvozanat saqlaysiz?",
    },
    {
        "title": "Logistika Koordinatori",
        "department": "Operations",
        "branch": "Toshkent",
        "region": "Toshkent",
        "category": "Logistics",
        "description": "Yetkazib berish, buyurtma monitoringi va ta'minot zanjirini nazorat qilish.",
        "hard_skill_q1": "Logistika jadvalini rejalashtirishda qaysi parametrlar muhim?",
        "hard_skill_q2": "Buyurtma kechikishlarida qaysi nazorat mexanizmlarini qo'llaysiz?",
        "soft_skill_q1": "Ko'p tomonlama muammolarni qanday boshqarasiz?",
        "soft_skill_q2": "Jamoa va etkazib beruvchilar bilan muloqotda qanday muvozanat yaratib borasiz?",
    },
]


def seed_vacancies_if_needed() -> None:
    with Session(engine) as session:
        existing_count = session.exec(select(Vacancy)).all()
        if len(existing_count) >= 5:
            return

        for item in VACANCIES:
            branch = session.exec(select(Branch).where(Branch.name == item["branch"])).first()
            if not branch:
                branch = Branch(name=item["branch"], address=f"{item['region']} shahar markazi")
                session.add(branch)
                session.commit()
                session.refresh(branch)

            vacancy = session.exec(
                select(Vacancy).where(Vacancy.title == item["title"]).where(Vacancy.branch_id == branch.id)
            ).first()
            if vacancy:
                continue

            session.add(
                Vacancy(
                    title=item["title"],
                    department=item["department"],
                    branch=item["branch"],
                    region=item["region"],
                    category=item["category"],
                    description=item["description"],
                    branch_id=branch.id,
                    hard_skill_q1=item["hard_skill_q1"],
                    hard_skill_q2=item["hard_skill_q2"],
                    soft_skill_q1=item["soft_skill_q1"],
                    soft_skill_q2=item["soft_skill_q2"],
                    generated_hard_skill_q1=item["hard_skill_q1"],
                    generated_hard_skill_q2=item["hard_skill_q2"],
                    generated_soft_skill_q1=item["soft_skill_q1"],
                    generated_soft_skill_q2=item["soft_skill_q2"],
                    is_active=True,
                )
            )

        session.commit()
