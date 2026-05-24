"""AI conversation conductor engine for the compliance chat system.

Orchestrates multi-turn conversations between a user and an LLM-powered
compliance consultant. Retrieves relevant regulatory standards from ChromaDB,
manages conversation history, and extracts structured questionnaire data
when the assessment is complete.

Usage::

    from llm.chat_conductor import ChatConductor
    from llm.client import LLMClient

    conductor = ChatConductor(
        org_type="life_insurer",
        focus="operational risk management",
        llm_client=LLMClient(),
    )
    greeting = conductor.get_initial_message()
    response, is_ready = conductor.process_user_message("We have a framework")
    while not is_ready:
        response, is_ready = conductor.process_user_message(user_input)
    questionnaire, answers = conductor.extract_structured_data()

"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from engine.schemas import Question, QuestionSection, Questionnaire
from llm.client import LLMClient

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_COMPLETION_MARKER = "[ASSESSMENT_READY]"
_MAX_CONVERSATION_TURNS = 30

_ORG_TYPE_KEYWORDS: dict[str, str] = {
    "life insurer": "life_insurer",
    "life reinsurer": "life_reinsurer",
    "reinsurer": "life_reinsurer",
    "friendly society": "friendly_society",
    "superannuation fund": "superannuation_fund",
    "super fund": "superannuation_fund",
    "other": "other",
}

_SYSTEM_PROMPT_TEMPLATE = (
    "You are a warm, professional compliance consultant guiding a {org_type} "
    "through a {focus} assessment.\n\n"
    "YOUR ROLE:\n"
    "- Introduce yourself at the start of the conversation.\n"
    "- Ask about the user's organisation type and assessment focus early.\n"
    "- Confirm your understanding of their context before proceeding.\n"
    "- Ask ONE question at a time, adapting follow-ups based on answers.\n"
    "- Acknowledge the user's answers before moving on.\n"
    "- Keep responses concise: 2-4 sentences plus the next question.\n"
    "- Frame questions positively and reassure uncertain users.\n"
    "- Reference specific standards or clauses when relevant.\n"
    "- Signal completion by including {marker} when you have enough info.\n\n"
    "TONE:\n"
    "- Professional yet approachable — like a trusted advisor.\n"
    "- Never judgmental; users may be uncertain about compliance.\n"
    "- Use Australian English spelling (e.g. 'organise', 'recognise').\n\n"
    "CONVERSATION FLOW:\n"
    "- First message: introduce yourself and ask about their organisation.\n"
    "- Second phase: confirm their context, then start compliance questions.\n"
    "- After that: proceed through relevant compliance topics one at a time.\n"
    "- Once confident the assessment is sufficient, include {marker}.\n"
    "- Do not ask more than {max_turns} questions total.\n\n"
    "STANDARDS CONTEXT:\n"
    "{standards_context}"
)

_EXTRACTION_SYSTEM_PROMPT = (
    "Extract structured question-answer pairs from the following compliance "
    "consultation conversation.\n\n"
    "Return ONLY valid JSON matching this schema:\n"
    "{\n"
    '  "sections": [\n'
    "    {\n"
    '      "title": "Section Name",\n'
    '      "questions": [\n'
    "        {\n"
    '          "id": "unique_id",\n'
    '          "text": "Question text",\n'
    '          "type": "text|boolean|choice",\n'
    '          "source_standard": "Standard name",\n'
    '          "source_clause": "Clause reference",\n'
    '          "confidence": 0.85\n'
    "        }\n"
    "      ]\n"
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- Group questions logically by topic into sections.\n"
    "- Each section must have at least one question.\n"
    "- Generate unique IDs in format: {TOPIC}_{SEQ} (e.g. RISK_MGMT_01).\n"
    "- source_standard and source_clause are REQUIRED for every question.\n"
    "  Use the standard name (e.g. 'CPS 230', 'CPS 220', 'CPS 510', "
    "'CPS 900', 'Privacy Act') and the specific clause or paragraph "
    "reference discussed (e.g. 'Paragraph 27', 'APP 11', 'Section 6'). "
    "If uncertain, use the most likely standard and clause based on "
    "the topic discussed.\n"
    "- Set confidence based on how clearly the conversation covered the topic.\n"
    "- Return ONLY JSON — no markdown, no explanation."
)

_EXTRACTION_ANSWER_PROMPT = (
    "Map the user's answers from the conversation to the questionnaire "
    "questions below.\n\n"
    "Return ONLY valid JSON mapping question_id to the user's answer string.\n\n"
    "Example:\n"
    '{\n'
    '  "RISK_MGMT_01": "Yes, we have a documented framework.",\n'
    '  "DATA_GOVT_02": "Not yet implemented."\n'
    "}\n\n"
    "Rules:\n"
    "- Use the user's actual words or close paraphrase.\n"
    "- If the user did not answer a question, use 'Not answered'.\n"
    "- Return ONLY JSON — no markdown, no explanation."
)


# ------------------------------------------------------------------
# Custom error class
# ------------------------------------------------------------------


class ChatConductorError(Exception):
    """Raised when the chat conductor encounters a failure.

    Attributes:
        message: Human-readable error description.
        cause: The underlying exception, if any.
    """

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        self.cause = cause
        if cause:
            message = f"{message}: {cause}"
        super().__init__(message)


# ------------------------------------------------------------------
# ChatConductor
# ------------------------------------------------------------------


class ChatConductor:
    """Orchestrates multi-turn compliance consultations with an LLM.

    The conductor manages conversation history, retrieves relevant regulatory
    standards from ChromaDB, builds system prompts, and extracts structured
    questionnaire data after the conversation concludes.

    Args:
        org_type: Organisation type (e.g. "life_insurer", "general_insurer").
        focus: Compliance focus area (e.g. "operational risk management").
        llm_client: Optional LLMClient instance. When None, a default client
            is created using settings from llm.client.LLMSettings.
    """

    def __init__(
        self,
        org_type: str,
        focus: str,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.org_type: str = org_type
        self.focus: str = focus
        self._llm_client: LLMClient = llm_client or LLMClient()
        self._messages: list[dict[str, str]] = []
        self._standards: list[dict[str, Any]] = []
        self._standards_retrieved: bool = False

    # -- properties -------------------------------------------------------

    @property
    def messages(self) -> list[dict[str, str]]:
        """The full conversation history."""
        return self._messages

    @property
    def turn_count(self) -> int:
        """Number of user messages exchanged so far."""
        return sum(1 for m in self._messages if m.get("role") == "user")

    # -- standards retrieval ----------------------------------------------

    def _retrieve_standards(self) -> list[dict[str, Any]]:
        """Retrieve relevant regulatory standards from ChromaDB.

        Uses the ``_retrieve_relevant_standards`` helper from
        ``llm.question_generator`` with ``k=5`` to fetch the most relevant
        standard chunks. Results are cached after the first call.

        Returns:
            List of dicts with keys: standard_name, standard_category,
            clause, document, source_url. Returns an empty list on failure.
        """
        if self._standards_retrieved:
            return self._standards

        try:
            from llm.question_generator import _retrieve_relevant_standards

            self._standards = _retrieve_relevant_standards(
                user_input=self.focus,
                organization_type=self.org_type,
                k=5,
            )
        except Exception as exc:
            logger.warning("Standards retrieval failed: %s", exc)
            self._standards = []

        self._standards_retrieved = True
        return self._standards

    def _build_standards_context(self) -> str:
        """Build a text block of retrieved standards for the system prompt.

        Formats each standard chunk as a numbered entry with its name,
        category, clause, and truncated document content.

        Returns:
            Formatted standards context string. Returns a fallback message
            when no standards were retrieved.
        """
        standards = self._retrieve_standards()

        if not standards:
            return "No specific standards retrieved. Use general APRA compliance knowledge."

        parts: list[str] = []
        for i, std in enumerate(standards, 1):
            name = std.get("standard_name", "Unknown Standard")
            category = std.get("standard_category", "")
            clause = std.get("clause", "")
            doc = std.get("document", "")
            truncated = doc[:800] if doc else "No content available."

            parts.append(
                f"Standard {i}: {name} [{category}]\n  Clause: {clause}\n  Content: {truncated}",
            )

        return "\n\n".join(parts)

    def _build_system_prompt(self) -> str:
        """Build the full system prompt for the LLM.

        Combines the system prompt template with the organisation type,
        focus area, and retrieved standards context.

        Returns:
            The fully formatted system prompt string.
        """
        standards_context = self._build_standards_context()

        return _SYSTEM_PROMPT_TEMPLATE.format(
            marker=_COMPLETION_MARKER,
            max_turns=_MAX_CONVERSATION_TURNS,
            org_type=self.org_type,
            focus=self.focus,
            standards_context=standards_context,
        )

    # -- context extraction -----------------------------------------------

    def _extract_context_from_conversation(
        self,
    ) -> tuple[str, str]:
        """Extract org_type and focus from conversation history.

        Scans user messages for keywords matching known organisation type
        codes and focus area descriptions.  Updates self.org_type and
        self.focus if new values are detected.

        Returns:
            Tuple of (org_type, focus) detected from the conversation.
        """
        detected_org_type = self.org_type
        detected_focus = self.focus

        for msg in self._messages:
            if msg.get("role") != "user":
                continue
            text = msg.get("content", "").lower()

            for keyword, value in _ORG_TYPE_KEYWORDS.items():
                if keyword in text:
                    detected_org_type = value
                    break

            if not detected_focus and text.strip():
                detected_focus = text.strip()

        if detected_org_type != self.org_type:
            self.org_type = detected_org_type
        if detected_focus and not self.focus:
            self.focus = detected_focus

        return (self.org_type, self.focus)

    # -- conversation flow ------------------------------------------------

    def get_initial_message(self) -> str:
        """Generate the AI's opening greeting for the consultation.

        Returns a static greeting that introduces the assistant and asks
        about the user's organisation type and assessment focus area.
        The message is also stored in the conversation history.

        Returns:
            The greeting text to display to the user.
        """
        greeting = (
            "Hello! I'm your Standard_Inquirer assistant. I'm here to help "
            "you assess your organisation's compliance posture.\n\n"
            "To get started, could you tell me a bit about your organisation? "
            "What type are you — for example, a life insurer, reinsurer, "
            "friendly society, or superannuation fund?\n\n"
            "And what area would you like to focus on for this assessment?"
        )

        self._messages.append({"role": "assistant", "content": greeting})
        return greeting

    def process_user_message(self, user_message: str) -> tuple[str, bool]:
        """Process a user message and generate the consultant's response.

        Appends the user's message to the conversation history, extracts
        org_type and focus if not yet captured, builds the system prompt
        and conversation prompt, calls the LLM, and checks for the
        completion marker.

        Args:
            user_message: The user's input text.

        Returns:
            Tuple of (clean_response, is_ready) where:
            - clean_response: The LLM's response with the completion marker
              stripped (if present).
            - is_ready: True if the LLM included the completion marker,
              indicating the assessment is complete.
        """
        if not user_message or not user_message.strip():
            return (
                "Please provide a response so I can continue the assessment.",
                False,
            )

        # Extract org_type and focus from conversation if not captured
        self._extract_context_from_conversation()

        # Append user message to history
        self._messages.append({"role": "user", "content": user_message})

        # Check turn limit
        if self.turn_count > _MAX_CONVERSATION_TURNS:
            fallback = (
                "We've reached the maximum number of questions for this "
                "assessment. Let me compile what we've discussed."
            )
            self._messages.append({"role": "assistant", "content": fallback})
            return (fallback, True)

        try:
            # Build system prompt
            system_prompt = self._build_system_prompt()

            # Build conversation prompt from history (last 40 messages)
            recent_messages = self._messages[-40:]
            prompt = self._build_user_prompt_from_messages(recent_messages)

            # Call LLM
            response = self._llm_client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            logger.warning("LLM generation failed in process_user_message: %s", exc)
            fallback = (
                "I'm sorry, I encountered an issue generating a response. "
                "Could you please rephrase your answer and try again?"
            )
            self._messages.append({"role": "assistant", "content": fallback})
            return (fallback, False)

        # Handle empty response
        if not response or not response.strip():
            fallback = (
                "I didn't receive a response. Could you please rephrase "
                "your answer?"
            )
            self._messages.append({"role": "assistant", "content": fallback})
            return (fallback, False)

        # Check for completion marker
        is_ready = _COMPLETION_MARKER in response
        clean_response = response.replace(_COMPLETION_MARKER, "").strip()

        # Append assistant message to history (clean version without marker)
        self._messages.append({"role": "assistant", "content": clean_response})

        return (clean_response, is_ready)

    def _build_user_prompt_from_messages(self, messages: list[dict[str, str]]) -> str:
        """Encode multi-turn conversation history into a single prompt.

        Formats the conversation as alternating Consultant/User turns,
        skipping system messages. Adds a closing instruction for the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            Formatted prompt string for the LLM.
        """
        parts: list[str] = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Skip system messages
            if role == "system":
                continue

            if role == "assistant":
                parts.append(f"Consultant: {content}")
            elif role == "user":
                parts.append(f"User: {content}")

        conversation_text = "\n\n".join(parts)

        return (
            f"{conversation_text}\n\n"
            "Continue the conversation as the Consultant. Ask the next "
            "question or signal completion if you have enough information."
        )

    # -- data extraction --------------------------------------------------

    def extract_structured_data(self) -> tuple[Questionnaire, dict[str, Any]]:
        """Extract structured questionnaire and answers from the conversation.

        After the conversation concludes, formats the full exchange and
        uses the LLM to produce a validated Questionnaire and a mapping
        of question IDs to user answers.

        Returns:
            Tuple of (questionnaire, answers) where:
            - questionnaire: A validated Questionnaire Pydantic model.
            - answers: Dict mapping question IDs to answer strings.

        Raises:
            ChatConductorError: If extraction fails after all retries.
        """
        conversation = self._format_conversation()

        # Extract questionnaire
        try:
            questionnaire = self._extract_questionnaire(conversation)
        except Exception as exc:
            logger.warning("Questionnaire extraction failed, using fallback: %s", exc)
            questionnaire = self._build_fallback_questionnaire()

        # Extract answers
        try:
            answers = self._extract_answers(conversation, questionnaire)
        except Exception as exc:
            logger.warning("Answer extraction failed: %s", exc)
            # Collect question IDs for the fallback
            fallback_qids: list[str] = []
            for section in questionnaire.sections:
                for question in section.questions:
                    fallback_qids.append(question.id)
            answers = self._build_fallback_answers(fallback_qids)

        return (questionnaire, answers)

    def _format_conversation(self) -> str:
        """Format conversation messages as alternating Consultant/User turns.

        Returns:
            Formatted conversation string with role prefixes.
        """
        parts: list[str] = []

        for msg in self._messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                continue
            elif role == "assistant":
                parts.append(f"Consultant: {content}")
            elif role == "user":
                parts.append(f"User: {content}")

        return "\n\n".join(parts)

    def _extract_questionnaire(self, conversation: str) -> Questionnaire:
        """Extract a structured Questionnaire from the conversation text.

        Calls the LLM with the extraction system prompt and conversation
        text, retrying up to 3 times on failure. Falls back to a minimal
        questionnaire if all attempts fail.

        Args:
            conversation: Formatted conversation string.

        Returns:
            A validated Questionnaire Pydantic model.

        Raises:
            ChatConductorError: If extraction fails after all retries.
        """
        system_prompt = _EXTRACTION_SYSTEM_PROMPT

        for attempt in range(3):
            try:
                raw = self._llm_client.generate(
                    prompt=conversation,
                    system_prompt=system_prompt,
                )

                questionnaire = self._parse_questionnaire_json(raw)
                if questionnaire is not None:
                    logger.info(
                        "Questionnaire extracted: %d sections, %d questions",
                        len(questionnaire.sections),
                        sum(len(s.questions) for s in questionnaire.sections),
                    )
                    return questionnaire

                logger.warning(
                    "Questionnaire parse returned None on attempt %d/3",
                    attempt + 1,
                )

            except Exception as exc:
                logger.warning(
                    "Questionnaire extraction failed on attempt %d/3: %s",
                    attempt + 1,
                    exc,
                )

        # All retries exhausted — build fallback
        logger.warning(
            "All questionnaire extraction attempts failed — using fallback"
        )
        return self._build_fallback_questionnaire()

    def _parse_questionnaire_json(self, raw: str) -> Questionnaire | None:
        """Parse a raw JSON string into a Questionnaire.

        Cleans the raw text by stripping markdown fences, finding balanced
        braces, fixing trailing commas, and replacing single quotes. Then
        wraps the parsed dict with metadata fields before calling the
        shared ``_parse_questionnaire`` function.

        Args:
            raw: Raw JSON string from the LLM response.

        Returns:
            A validated Questionnaire, or None on failure.
        """
        cleaned = self._clean_json(raw)
        if cleaned is None:
            return None

        # Add wrapper fields expected by Questionnaire schema
        cleaned["generated_by"] = "llm"
        cleaned["generated_at"] = datetime.now(timezone.utc).isoformat()
        cleaned["organization_type"] = self.org_type
        cleaned["user_input"] = self.focus

        try:
            from llm.question_generator import _parse_questionnaire

            json_str = json.dumps(cleaned)
            return _parse_questionnaire(json_str)
        except Exception as exc:
            logger.warning("Questionnaire parse failed: %s", exc)
            return None

    def _clean_json(self, raw: str) -> dict[str, Any] | None:
        """Clean and parse a raw JSON string from the LLM.

        Strips markdown code fences, finds the outermost balanced braces,
        fixes trailing commas, and replaces single quotes with double quotes.

        Args:
            raw: Raw text that may contain JSON.

        Returns:
            Parsed dict, or None if the content cannot be parsed.
        """
        text = raw.strip()

        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Find balanced braces to extract the JSON object
        brace_count = 0
        json_end = -1
        for i, ch in enumerate(text):
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break

        if json_end > 0:
            text = text[:json_end]

        # Fix trailing commas before } or ]
        text = re.sub(r",(\s*[\]}])", r"\1", text)

        # Replace single quotes with double quotes (basic pass)
        text = text.replace("'", '"')

        # Parse JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("JSON parse failed: %s", exc)
            return None

    def _extract_answers(
        self, conversation: str, questionnaire: Questionnaire
    ) -> dict[str, Any]:
        """Extract user answers from the conversation mapped to questionnaire IDs.

        First attempts LLM-based extraction, then falls back to direct
        conversation-based extraction for any remaining unanswered questions.

        Args:
            conversation: Formatted conversation string.
            questionnaire: The extracted Questionnaire model.

        Returns:
            Dict mapping question IDs to answer strings.
        """
        # Collect all question IDs and texts from the questionnaire
        question_ids: list[str] = []
        question_texts: dict[str, str] = {}
        for section in questionnaire.sections:
            for question in section.questions:
                question_ids.append(question.id)
                question_texts[question.id] = question.text

        if not question_ids:
            return {}

        # -- Phase 1: LLM-based extraction ------------------------------------
        answers: dict[str, Any] = {}
        llm_succeeded = False

        system_prompt = (
            _EXTRACTION_ANSWER_PROMPT
            + f"\n\nQuestion IDs to extract answers for: {', '.join(question_ids)}"
        )

        try:
            raw = self._llm_client.generate(
                prompt=conversation,
                system_prompt=system_prompt,
            )

            cleaned = self._clean_json(raw)
            if cleaned is not None and isinstance(cleaned, dict):
                for qid in question_ids:
                    if qid in cleaned:
                        val = cleaned[qid]
                        # Accept the answer only if it's not the "Not answered"
                        # placeholder that the LLM itself may have generated.
                        if val and str(val).strip().lower() != "not answered":
                            answers[qid] = val
                llm_succeeded = len(answers) > 0

        except Exception as exc:
            logger.warning("LLM answer extraction failed: %s", exc)

        # -- Phase 2: Conversation-based fallback for missing answers ----------
        missing_ids = [qid for qid in question_ids if qid not in answers]
        if missing_ids:
            conv_answers = self._extract_answers_from_conversation(
                missing_ids, question_texts,
            )
            answers.update(conv_answers)

        # -- Phase 3: Final fallback — mark truly unanswered -------------------
        for qid in question_ids:
            if qid not in answers:
                answers[qid] = "Not answered"

        llm_count = sum(1 for qid in question_ids if qid in answers and answers[qid] != "Not answered")
        logger.info(
            "Answer extraction: %d/%d answered (LLM: %d, conversation: %d, missing: %d)",
            llm_count,
            len(question_ids),
            llm_succeeded and llm_count or 0,
            sum(1 for qid in missing_ids if qid in answers and answers[qid] != "Not answered"),
            sum(1 for qid in question_ids if answers.get(qid) == "Not answered"),
        )

        return answers

    def _extract_answers_from_conversation(
        self,
        question_ids: list[str],
        question_texts: dict[str, str],
    ) -> dict[str, Any]:
        """Extract answers directly from conversation history by pairing
        consultant questions with the user's next response.

        For each question ID, finds the consultant message that most closely
        matches the question text, then takes the user's next message as the
        answer.

        Args:
            question_ids: Question IDs still missing answers.
            question_texts: Mapping of question ID → question text.

        Returns:
            Dict mapping question IDs to extracted answer strings.
        """
        answers: dict[str, Any] = {}

        # Build a list of (index, role, content) for quick scanning
        indexed_messages = [
            (i, m.get("role", ""), m.get("content", ""))
            for i, m in enumerate(self._messages)
        ]

        for qid in question_ids:
            q_text = question_texts.get(qid, "")
            if not q_text:
                continue

            # Find the consultant message that best matches this question
            best_idx = -1
            best_overlap = 0

            # Use first 60 chars of question text for matching (avoids
            # false positives from long messages that mention many topics)
            q_key = q_text[:60].lower()

            for i, role, content in indexed_messages:
                if role != "assistant":
                    continue
                content_lower = content.lower()
                # Count how many significant words from the question appear
                # in the consultant's message
                q_words = [w for w in q_key.split() if len(w) > 3]
                if not q_words:
                    continue
                overlap = sum(1 for w in q_words if w in content_lower)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_idx = i

            # Require at least 2 matching words to consider it a match
            if best_idx < 0 or best_overlap < 2:
                continue

            # Find the next user message after this consultant message
            for i, role, content in indexed_messages[best_idx + 1 :]:
                if role == "user" and content.strip():
                    answers[qid] = content.strip()
                    break

        return answers

    def _build_fallback_answers(
        self, question_ids: list[str]
    ) -> dict[str, Any]:
        """Build answers from conversation history when LLM extraction fails.

        Delegates to :meth:`_extract_answers_from_conversation` for smart
        matching.  Falls back to ``'Not answered'`` only when no user
        response can be found for a question.

        Args:
            question_ids: List of question IDs from the questionnaire.

        Returns:
            Dict mapping question IDs to answer strings.
        """
        # Build minimal question_texts from the conversation
        # (used when called without a full questionnaire context)
        answers = self._extract_answers_from_conversation(
            question_ids, {qid: "" for qid in question_ids},
        )
        for qid in question_ids:
            if qid not in answers:
                answers[qid] = "Not answered"
        return answers

    def _build_fallback_questionnaire(self) -> Questionnaire:
        """Build a minimal fallback Questionnaire from the conversation.

        Creates a single section titled "General Compliance" with questions
        derived from the focus area and organisation type.

        Returns:
            A minimal Questionnaire instance with fallback metadata.
        """
        # Derive question text from the focus area
        focus_text = self.focus.replace("_", " ").title()
        org_text = self.org_type.replace("_", " ").title()

        questions = [
            Question(
                id="GENERAL_01",
                text=f"Can you describe your organisation's current approach to {focus_text.lower()}?",
                type="text",
                default=None,
                options=None,
                source_standard=None,
                source_clause=None,
                confidence=0.5,
                applies_to_standard=None,
            ),
            Question(
                id="GENERAL_02",
                text=f"Are there any documented policies or procedures related to {focus_text.lower()}?",
                type="boolean",
                default=False,
                options=None,
                source_standard=None,
                source_clause=None,
                confidence=0.5,
                applies_to_standard=None,
            ),
            Question(
                id="GENERAL_03",
                text=f"Has your {org_text} organisation undergone any {focus_text.lower()} assessments in the past 12 months?",
                type="boolean",
                default=False,
                options=None,
                source_standard=None,
                source_clause=None,
                confidence=0.5,
                applies_to_standard=None,
            ),
        ]

        section = QuestionSection(
            title="General Compliance",
            questions=questions,
        )

        return Questionnaire(
            sections=[section],
            generated_by="fallback",
            generated_at=datetime.now(timezone.utc).isoformat(),
            organization_type=self.org_type,
            user_input=self.focus,
        )
