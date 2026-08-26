import json
import os
from typing import Any, Dict
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
    """
    Generates 2 hard-skill questions and 2 soft-skill situational questions in Uzbek language
    for the provided vacancy title and description using gpt-4o-mini.
    Calculates exact token costs.
    """
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
