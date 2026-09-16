import re
from typing import Optional
from app.schemas.tutoring import (
    QueryUnderstandingResult,
    ActionPlan,
    UserIntent,
    ActionTypeEnum,
    ResponseTypeEnum,
    RetrievalScopeEnum
)


class QueryFastPath:
    """
    Stage 1b: Deterministic Fast-Path Classifier.
    Evaluates obvious, unambiguous conversational queries (greetings, pleasantries,
    confirmations, farewells, continuation signals) without incurring latency or token cost
    of an LLM call.
    """

    GREETING_PATTERN = re.compile(
        r"^(?:hi|hello|hey|heya|howdy|good\s+(?:morning|afternoon|evening|day)|greetings|hi\s+there|hello\s+there|hey\s+there)\b[!.?]*$",
        re.IGNORECASE
    )

    FAREWELL_PATTERN = re.compile(
        r"^(?:bye|goodbye|see\s+you|cya|take\s+care|farewell|have\s+a\s+good\s+(?:day|night))\b[!.?]*$",
        re.IGNORECASE
    )

    GRATITUDE_PATTERN = re.compile(
        r"^(?:thanks|thank\s+you|thankyou|thx|ty|many\s+thanks|appreciate\s+it|thanks\s+a\s+lot|thank\s+you\s+so\s+much)\b[!.?]*$",
        re.IGNORECASE
    )

    CONFIRMATION_PATTERN = re.compile(
        r"^(?:ok|okay|k|got\s+it|understood|makes\s+sense|sounds\s+good|all\s+good|sure|perfect|great|alright|yes|yeah|yep|yup|no|nope|nah)\b[!.?]*$",
        re.IGNORECASE
    )

    CONTINUATION_PATTERN = re.compile(
        r"^(?:continue|next|go\s+on|proceed|move\s+on|next\s+topic|keep\s+going)\b[!.?]*$",
        re.IGNORECASE
    )

    @classmethod
    def evaluate(
        cls,
        normalized_query: str,
        original_query: str,
        language: str = "en",
        current_subject: Optional[str] = None,
        current_topic: Optional[str] = None
    ) -> Optional[QueryUnderstandingResult]:
        """
        Determines if the query matches a deterministic fast-path pattern.
        Returns QueryUnderstandingResult if matched, otherwise None (send to LLM Analyzer).
        """
        cleaned = normalized_query.strip().lower()

        # 1. Greetings
        if cls.GREETING_PATTERN.match(cleaned):
            action_plan = ActionPlan(
                action=ActionTypeEnum.CASUAL_REPLY.value,
                topic=current_topic,
                retrieval_required=False,
                retrieval_scope=RetrievalScopeEnum.NONE.value,
                response_type=ResponseTypeEnum.DIRECT_ANSWER.value,
                requires_tool=False,
                confidence=0.99,
                execution_strategy="fast_path"
            )
            return QueryUnderstandingResult(
                original_query=original_query,
                normalized_query=normalized_query,
                resolved_query=normalized_query,
                language=language,
                intent=UserIntent.GREETING.value,
                sub_intent="GREETING",
                subject=current_subject,
                topic=current_topic,
                entities=[],
                difficulty="beginner",
                response_type=ResponseTypeEnum.DIRECT_ANSWER.value,
                requires_context=False,
                requires_retrieval=False,
                retrieval_scope=RetrievalScopeEnum.NONE.value,
                retrieval_query=None,
                action=ActionTypeEnum.CASUAL_REPLY.value,
                action_plan=action_plan,
                requires_tool=False,
                confidence=0.99,
                is_fast_path=True
            )

        # 2. Farewells
        if cls.FAREWELL_PATTERN.match(cleaned):
            action_plan = ActionPlan(
                action=ActionTypeEnum.CASUAL_REPLY.value,
                topic=current_topic,
                retrieval_required=False,
                retrieval_scope=RetrievalScopeEnum.NONE.value,
                response_type=ResponseTypeEnum.DIRECT_ANSWER.value,
                requires_tool=False,
                confidence=0.99,
                execution_strategy="fast_path"
            )
            return QueryUnderstandingResult(
                original_query=original_query,
                normalized_query=normalized_query,
                resolved_query=normalized_query,
                language=language,
                intent=UserIntent.CASUAL.value,
                sub_intent="FAREWELL",
                subject=current_subject,
                topic=current_topic,
                entities=[],
                difficulty="beginner",
                response_type=ResponseTypeEnum.DIRECT_ANSWER.value,
                requires_context=False,
                requires_retrieval=False,
                retrieval_scope=RetrievalScopeEnum.NONE.value,
                retrieval_query=None,
                action=ActionTypeEnum.CASUAL_REPLY.value,
                action_plan=action_plan,
                requires_tool=False,
                confidence=0.99,
                is_fast_path=True
            )

        # 3. Gratitude
        if cls.GRATITUDE_PATTERN.match(cleaned):
            action_plan = ActionPlan(
                action=ActionTypeEnum.CASUAL_REPLY.value,
                topic=current_topic,
                retrieval_required=False,
                retrieval_scope=RetrievalScopeEnum.NONE.value,
                response_type=ResponseTypeEnum.DIRECT_ANSWER.value,
                requires_tool=False,
                confidence=0.99,
                execution_strategy="fast_path"
            )
            return QueryUnderstandingResult(
                original_query=original_query,
                normalized_query=normalized_query,
                resolved_query=normalized_query,
                language=language,
                intent=UserIntent.CONFIRMATION.value,
                sub_intent="GRATITUDE",
                subject=current_subject,
                topic=current_topic,
                entities=[],
                difficulty="beginner",
                response_type=ResponseTypeEnum.DIRECT_ANSWER.value,
                requires_context=False,
                requires_retrieval=False,
                retrieval_scope=RetrievalScopeEnum.NONE.value,
                retrieval_query=None,
                action=ActionTypeEnum.CASUAL_REPLY.value,
                action_plan=action_plan,
                requires_tool=False,
                confidence=0.99,
                is_fast_path=True
            )

        # 4. Confirmation / Acknowledgment
        if cls.CONFIRMATION_PATTERN.match(cleaned):
            action_plan = ActionPlan(
                action=ActionTypeEnum.CASUAL_REPLY.value,
                topic=current_topic,
                retrieval_required=False,
                retrieval_scope=RetrievalScopeEnum.NONE.value,
                response_type=ResponseTypeEnum.DIRECT_ANSWER.value,
                requires_tool=False,
                confidence=0.95,
                execution_strategy="fast_path"
            )
            return QueryUnderstandingResult(
                original_query=original_query,
                normalized_query=normalized_query,
                resolved_query=normalized_query,
                language=language,
                intent=UserIntent.CONFIRMATION.value,
                sub_intent="ACKNOWLEDGMENT",
                subject=current_subject,
                topic=current_topic,
                entities=[],
                difficulty="beginner",
                response_type=ResponseTypeEnum.DIRECT_ANSWER.value,
                requires_context=True,
                requires_retrieval=False,
                retrieval_scope=RetrievalScopeEnum.NONE.value,
                retrieval_query=None,
                action=ActionTypeEnum.CASUAL_REPLY.value,
                action_plan=action_plan,
                requires_tool=False,
                confidence=0.95,
                is_fast_path=True
            )

        # 5. Continuation
        if cls.CONTINUATION_PATTERN.match(cleaned):
            action_plan = ActionPlan(
                action=ActionTypeEnum.TEACH_TOPIC.value,
                topic=current_topic,
                retrieval_required=bool(current_topic),
                retrieval_scope=RetrievalScopeEnum.CURRENT_TOPIC.value if current_topic else RetrievalScopeEnum.NONE.value,
                retrieval_query=current_topic or "continue lesson",
                response_type=ResponseTypeEnum.STEP_BY_STEP.value,
                requires_tool=False,
                confidence=0.92,
                execution_strategy="fast_path"
            )
            return QueryUnderstandingResult(
                original_query=original_query,
                normalized_query=normalized_query,
                resolved_query=f"Continue teaching {current_topic}" if current_topic else normalized_query,
                language=language,
                intent=UserIntent.CONTINUE_LEARNING.value,
                sub_intent="CONTINUE",
                subject=current_subject,
                topic=current_topic,
                entities=[current_topic] if current_topic else [],
                difficulty="intermediate",
                response_type=ResponseTypeEnum.STEP_BY_STEP.value,
                requires_context=True,
                requires_retrieval=bool(current_topic),
                retrieval_scope=RetrievalScopeEnum.CURRENT_TOPIC.value if current_topic else RetrievalScopeEnum.NONE.value,
                retrieval_query=current_topic,
                action=ActionTypeEnum.TEACH_TOPIC.value,
                action_plan=action_plan,
                requires_tool=False,
                confidence=0.92,
                is_fast_path=True
            )

        return None
