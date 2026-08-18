import asyncio
from app.rag.quiz_generator import generate_quiz_for_section

async def test_quiz_gen():
    print("Testing generate_quiz_for_section on 'math-10-1'...")
    try:
        quiz = await generate_quiz_for_section(
            section_id="math-10-1",
            user_id="usr_test_123",
            focus_topic=None,
            difficulty="medium",
            num_questions=5,
            topic_id="math-10-1"
        )
        print("Quiz result:", quiz)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_quiz_gen())
