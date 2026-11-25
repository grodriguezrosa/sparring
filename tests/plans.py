"""Builders for interview plans used by several test files."""

from app.schemas.interview_plan import InterviewPlan, InterviewTopic


def make_topic(title: str = "Testing con pytest", minutes: int = 10) -> InterviewTopic:
    return InterviewTopic(
        title=title,
        requirement="Experiencia con pytest",
        focus="verify_claim",
        importance="high",
        opening_question="¿Cómo organizas los tests de un proyecto?",
        follow_up_questions=["¿Qué es una fixture?"],
        good_answer_signals=["Fixtures y conftest.py"],
        minutes=minutes,
    )


def make_plan(topics: int = 3) -> InterviewPlan:
    return InterviewPlan(
        intro="Hola, vamos a hacer una entrevista técnica de 30 minutos.",
        duration_minutes=30,
        topics=[make_topic(f"Tema {n}") for n in range(1, topics + 1)],
    )
