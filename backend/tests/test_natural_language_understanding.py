import pytest
from app.tutoring.teaching.interactive_teacher import InteractiveTeacherEngine
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.tutoring.analyzer.feedback_classifier import (
    UserMessageContextClassifier,
    UserMessageClassificationEnum,
)
from app.tutoring.teaching.correction_handler import TeachingCorrectionHandler


class TestNaturalLanguageTopicExtraction:
    def test_exam_clause_with_quantifier(self):
        query = "so tommarow i have exam on self attention, so teach me everything"
        topic, portion = InteractiveTeacherEngine.extract_teach_topic_and_portion(query)
        assert topic.lower() == "self attention"
        assert portion is None

        phrase = QueryUnderstanding.extract_teach_topic(query)
        assert phrase.lower() == "self attention"

    def test_trailing_scope_clause(self):
        query = "teach me everything about self attention"
        topic, portion = InteractiveTeacherEngine.extract_teach_topic_and_portion(query)
        assert topic.lower() == "self attention"
        assert portion is None

        phrase = QueryUnderstanding.extract_teach_topic(query)
        assert phrase.lower() == "self attention"

    def test_prep_clause_with_quantifier(self):
        query = "i have test on decision trees, teach me all of it"
        topic, portion = InteractiveTeacherEngine.extract_teach_topic_and_portion(query)
        assert topic.lower() == "decision trees"

    def test_prefix_colon_clause(self):
        query = "self attention: teach me everything"
        topic, portion = InteractiveTeacherEngine.extract_teach_topic_and_portion(query)
        assert topic.lower() == "self attention"

    def test_standard_teach_query(self):
        query = "teach me Decision Tree"
        topic, portion = InteractiveTeacherEngine.extract_teach_topic_and_portion(query)
        assert topic == "Decision Tree"
        assert portion is None

    def test_portion_within_topic(self):
        query = "Teach me Root Node of Decision Tree"
        topic, portion = InteractiveTeacherEngine.extract_teach_topic_and_portion(query)
        assert topic == "Decision Tree"
        assert portion == "Root Node"

    def test_standalone_quantifier_does_not_become_topic(self):
        query = "teach me everything"
        topic, portion = InteractiveTeacherEngine.extract_teach_topic_and_portion(query)
        assert topic is None

        phrase = QueryUnderstanding.extract_teach_topic(query)
        assert phrase is None


class TestConversationalClarificationClassification:
    def test_everything_means_all_the_topic(self):
        res = UserMessageContextClassifier.classify_message("everything means all the topic")
        assert res.category == UserMessageClassificationEnum.CLARIFICATION_CONTINUATION
        assert res.category != UserMessageClassificationEnum.STATEMENT_EVALUATION

    def test_i_mean_all_topics(self):
        res = UserMessageContextClassifier.classify_message("i mean all the topics")
        assert res.category == UserMessageClassificationEnum.CLARIFICATION_CONTINUATION

    def test_by_everything_i_mean(self):
        res = UserMessageContextClassifier.classify_message("by everything i mean all of it")
        assert res.category == UserMessageClassificationEnum.CLARIFICATION_CONTINUATION

    def test_actual_academic_statement_still_evaluated(self):
        # A true factual assertion about domain concepts should still be STATEMENT_EVALUATION
        res = UserMessageContextClassifier.classify_message("gravity is proportional to mass")
        assert res.category == UserMessageClassificationEnum.STATEMENT_EVALUATION


class TestTrailingQuestionDeduplication:
    def test_trailing_question_not_duplicated(self, monkeypatch):
        # When LLM already asks a concluding question
        monkeypatch.setattr(
            "app.services.llm_service.default_llm_service.generate",
            lambda prompt, system_prompt: "Self attention maps queries and keys. Would you like to begin with how queries and keys are calculated?"
        )
        out = TeachingCorrectionHandler.handle_statement_evaluation(
            user_statement="queries match keys",
            conversation_history=[],
            is_teacher_mode=True
        )
        assert out.count("Would you like") == 1
        assert not out.endswith("**Would you like me to continue to the next subtopic?**")

    def test_statement_evaluation_adds_question_if_missing(self, monkeypatch):
        # When LLM does not ask a concluding question
        monkeypatch.setattr(
            "app.services.llm_service.default_llm_service.generate",
            lambda prompt, system_prompt: "That is correct. Self-attention relates different positions of a single sequence to compute a representation."
        )
        out = TeachingCorrectionHandler.handle_statement_evaluation(
            user_statement="queries match keys",
            conversation_history=[],
            is_teacher_mode=True
        )
        assert out.endswith("**Would you like me to continue to the next subtopic?**")
