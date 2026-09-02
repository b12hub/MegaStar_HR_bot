from datetime import datetime
from typing import Dict, Any
from db.models import CandidateApplication

def calculate_objective_score(app: CandidateApplication) -> int:
    """
    Calculates the objective score (0 to 110 max) for a candidate application
    based on multiple-choice attributes.
    """
    score = 0

    # 1. Age Bracket
    # birth_date is stored as string (e.g. 'YYYY-MM-DD' or similar)
    if app.birth_date:
        try:
            # Try parsing various common date formats
            birth_dt = None
            for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
                try:
                    birth_dt = datetime.strptime(app.birth_date, fmt)
                    break
                except ValueError:
                    continue
            
            if birth_dt:
                today = datetime.today()
                age = today.year - birth_dt.year - ((today.month, today.day) < (birth_dt.month, birth_dt.day))
                if 20 <= age <= 35:
                    score += 15
                elif 18 <= age <= 19 or 36 <= age <= 45:
                    score += 10
                else:
                    score += 5
            else:
                score += 5
        except Exception:
            score += 5  # default points if date parsing fails
    else:
        score += 5

    # 2. Work Experience Years
    # work_experience_years is Optional[str]
    if app.work_experience_years:
        try:
            years = int(app.work_experience_years)
            if years >= 3:
                score += 15
            elif 1 <= years <= 2:
                score += 10
            else:
                score += 5
        except Exception:
            score += 5
    else:
        score += 5

    # 3. Uzbek Language Level
    if app.uz_lang_level:
        lvl = app.uz_lang_level.lower()
        if "mukammal" in lvl:
            score += 15
        elif "o'rtacha" in lvl or "ortacha" in lvl:
            score += 10
        else:
            score += 5
    else:
        score += 5

    # 4. Russian Language Level
    if app.rus_lang_level:
        lvl = app.rus_lang_level.lower()
        if "mukammal" in lvl:
            score += 15
        elif "o'rtacha" in lvl or "ortacha" in lvl:
            score += 10
        else:
            score += 5
    else:
        score += 5

    # 5. English Language Level
    if app.eng_lang_level:
        lvl = app.eng_lang_level.lower()
        if "mukammal" in lvl:
            score += 10
        elif "o'rtacha" in lvl or "ortacha" in lvl:
            score += 5
        else:
            score += 0
    else:
        score += 0

    # 6. Computer Level
    if app.computer_level:
        lvl = app.computer_level.lower()
        if "ekspert" in lvl or "tajribali" in lvl:
            score += 15
        elif "o'rtacha" in lvl or "ortacha" in lvl:
            score += 10
        else:
            score += 5
    else:
        score += 5

    # 7. Has Car
    if app.has_car is True or str(app.has_car).lower() in ("ha", "true", "1", "yes", "on"):
        score += 10
    else:
        score += 5

    # 8. Is Convicted
    if app.is_convicted is False or str(app.is_convicted).lower() in ("yo'q", "yoq", "false", "0", "no", "off"):
        score += 15
    elif app.is_convicted is True or str(app.is_convicted).lower() in ("ha", "true", "1", "yes", "on"):
        score -= 10
    else:
        score += 15  # default if not specified

    return score


def calculate_base_score(candidate_data: Dict[str, Any]) -> int:
    """
    Calculates a deterministic base score based on candidate attributes.
    Expects a dictionary with keys: age, experience_years, has_license, languages.
    """
    score = 0

    # 1. Age bracket scoring
    age = candidate_data.get("age")
    if isinstance(age, int):
        if 18 <= age <= 25:
            score += 5
        elif 26 <= age <= 35:
            score += 10

    # 2. Experience scoring
    experience = candidate_data.get("experience_years")
    if isinstance(experience, (int, float)):
        if 1 <= experience < 3:
            score += 10
        elif experience >= 3:
            score += 20

    # 3. Driver's License
    has_license = candidate_data.get("has_license")
    if isinstance(has_license, bool) and has_license:
        score += 5

    # 4. Language skills
    languages = candidate_data.get("languages", [])
    if isinstance(languages, list):
        # Convert to lowercase for safe matching
        langs_lower = [lang.lower() for lang in languages]
        if "russian" in langs_lower:
            score += 5
        if "english" in langs_lower:
            score += 5

    return score

