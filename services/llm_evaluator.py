import json
import os
from typing import Any, Dict , Union
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL or "https://openrouter.ai/api/v1",
)

# Pricing for gpt-4o-mini
# $0.15 per 1,000,000 input tokens, $0.60 per 1,000,000 output tokens
INPUT_COST_PER_MILLION = 0.15
OUTPUT_COST_PER_MILLION = 0.60


class VacancyQuestionsSchema(BaseModel):
    hard_skill_q1: str
    hard_skill_q2: str
    soft_skill_q1: str
    soft_skill_q2: str



async def generate_vacancy_questions(title: str, description: str) -> Dict[str, Any]:
    """Generates vacancy questions..."""

    # 1. ONLY the Question Generation Prompt goes here
    system_prompt = (
        "Siz malakali HR mutaxassisisiz. Berilgan vakansiya lavozimi va tavsifi asosida "
        "nomzodlar uchun O'zbek tilida 2 ta hard-skill (kasbiy ko'nikmalar bo'yicha) va "
        "2 ta soft-skill (vaziyatli/situatsion) savollarini tuzing. "
        "Javobni quyidagi JSON formatida qaytaring:\n"
        "{\n"
        '  "hard_skill_q1": "1-kasbiy savol",\n'
        '  "hard_skill_q2": "2-kasbiy savol",\n'
        '  "soft_skill_q1": "1-vaziyatli savol",\n'
        '  "soft_skill_q2": "2-vaziyatli savol"\n'
        "}"
    )

    user_prompt = f"Vakansiya lavozimi (Title): {title}\nVakansiya tavsifi (Description): {description}"

    response = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=VacancyQuestionsSchema,
        temperature=0.7,
    )

    parsed_questions = response.choices[0].message.parsed
    if parsed_questions is not None:
        questions_dict = parsed_questions.model_dump()
    else:
        # Fallback if raw text returned
        content = response.choices[0].message.content or "{}"
        questions_dict = json.loads(content)

    tokens_input = response.usage.prompt_tokens if response.usage else 0
    tokens_output = response.usage.completion_tokens if response.usage else 0

    cost_usd = (tokens_input * INPUT_COST_PER_MILLION / 1_000_000) + (
        tokens_output * OUTPUT_COST_PER_MILLION / 1_000_000
    )

    return {
        "questions": questions_dict,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "cost_usd": cost_usd,
    }


class EvaluationScoreSchema(BaseModel):
    ai_score: int
    feedback: str

async def evaluate_candidate_answers(answers: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """
    Evaluates candidate answers (dict or string) and returns a score and feedback in Uzbek.
    """
    # Check if answers is already a string (from webapp.py) or a dictionary
    if isinstance(answers, str):
        formatted_answers = answers
    elif isinstance(answers, dict):
        formatted_answers = "\n".join([f"Q: {k}\nA: {v}" for k, v in answers.items()])
    else:
        formatted_answers = str(answers)

    system_prompt = (
        "Siz o'ta qat'iy va shafqatsiz HR baholovchi sun'iy intellektsiz. Vazifangiz nomzodning matnli javoblarini 0 dan 100 gacha baholash.\n\n"
        "QAT'IY QOIDALAR:\n"
        "1. BO'SH YOKI TASODIFIY JAVOBLAR: Bo'sh qoldirilgan javoblar, tasodifiy harflar ('asdfg', 'qwe') yoki ma'nosiz matnlar uchun DARHOL 0 BALL bering.\n"
        "2. SALBIY VA NOADEKVAT JAVOBLAR: Agar nomzod tajribasi yo'qligini aytsa ('bilmayman', 'ishlatmaganman', 'yo'q', 'qilmaganman', 'foydalanmaganman') yoki agressiv/noadekvat javob bersa ('urushaman', 'o'rganmayman', 'xohlamayman'), QAT'IYAN 0 BALL bering.\n"
        "3. QISQA JAVOBLAR: 1-2 so'zdan iborat, lekin ijobiy ma'noli bo'lgan javoblar uchun ko'pi bilan 5 ball bering.\n"
        "4. YUQORI BALL (80-100): Faqatgina savolga to'liq, professional, o'z tajribasini chuqur tushuntirib bergan batafsil javoblargagina qo'yiladi.\n"
        "5. Natija har doim o'zbek tilida qisqa izoh (feedback) bilan qaytsin. Natijani 'ai_score' (butun son) va 'feedback' kalitlarida qaytaring."
    )

    user_prompt = f"Nomzodning savol-javoblari:\n{formatted_answers}"

    try:
        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=EvaluationScoreSchema,
            temperature=0.0,
        )

        parsed_eval = response.choices[0].message.parsed
        if parsed_eval is not None:
            return {
                "ai_score": parsed_eval.ai_score,
                "feedback": parsed_eval.feedback
            }
        else:
            # Fallback parsing if structured output partially fails
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            return {
                "ai_score": int(data.get("ai_score", 0)),
                "feedback": str(data.get("feedback", "Tahlil qilib bo'lmadi"))
            }

    except Exception as e:
        print(f"Error during AI evaluation: {e}")
        return {
            "ai_score": 0,
            "feedback": f"Baholashda xatolik yuz berdi: {str(e)}"
        }