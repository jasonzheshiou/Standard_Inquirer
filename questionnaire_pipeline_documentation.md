# Free-Text-to-Questionnaire: Complete Pipeline Documentation

> **Purpose**: This document traces every step of the pipeline that converts free-text user input into a structured compliance questionnaire. Includes exact code, data flow, error handling, and known failure points.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Step 1: User Input (UI)](#2-step-1-user-input-ui)
3. [Step 2: LLM Client Initialization](#3-step-2-llm-client-initialization)
4. [Step 3: ChromaDB Retrieval](#4-step-3-chromadb-retrieval)
5. [Step 4: Prompt Construction](#5-step-4-prompt-construction)
6. [Step 5: LLM API Call](#6-step-5-llm-api-call)
7. [Step 6: JSON Parsing & Validation](#7-step-6-json-parsing--validation)
8. [Step 7: Fallback Mechanism](#8-step-7-fallback-mechanism)
9. [Known Failure Points](#9-known-failure-points)
10. [Full Call Flow Diagram](#10-full-call-flow-diagram)
11. [Configuration Reference](#11-configuration-reference)

---

## 1. Overview

The pipeline has **7 stages**:

```
User Input → LLM Client Init → ChromaDB Retrieval → Prompt Construction → LLM API Call → JSON Parsing → Questionnaire Object
```

### Key Files

| File | Role |
|------|------|
| `ui/questionnaire_intake.py` | UI entry point — free-text input + generate button |
| `llm/client.py` | LMStudio HTTP client — retry, timeout, response_format handling |
| `llm/question_generator.py` | Orchestration — retrieval, prompt building, LLM call, JSON parsing, fallback |
| `engine/schemas.py` | Pydantic models — Questionnaire, QuestionSection, Question |
| `standards_ingestion/embedder.py` | ChromaDB client, embedding model, collection management |

---

## 2. Step 1: User Input (UI)

**File**: `ui/questionnaire_intake.py`

### Data Flow

1. User selects organisation type (radio buttons)
2. User types free text or clicks example chip
3. User clicks "Generate Questionnaire"
4. Button handler calls `generate_questionnaire()`

### Code: Button Handler (lines 321-389)

```python
if generated and not disabled:
    st.session_state.intake_status = "generating"

    # Build LLM client from user settings
    try:
        from llm.client import LLMSettings
        model_val: str = st.session_state.intake_model
        temp_val: float = float(st.session_state.intake_temperature)
        custom_settings = LLMSettings(
            llm_base_url="http://192.168.1.59:1234/v1",
            llm_model=model_val,
            llm_temperature=temp_val,
        )
        llm_client = LLMClient(settings=custom_settings)
    except Exception as exc:
        logger.error("Failed to create LLM client: %s", exc)
        st.session_state.intake_status = "error"
        st.session_state.intake_error = "Could not initialise the LLM client."
        st.rerun()

    try:
        org_type: str = st.session_state.intake_org_type
        questionnaire = generate_questionnaire(
            user_input=user_input,
            organization_type=org_type,
            llm_client=llm_client,
        )
        # ... success handling ...

    except QuestionGenerationError as exc:
        st.session_state.intake_status = "error"
        st.session_state.intake_error = str(exc)

    except Exception as exc:
        st.session_state.intake_status = "error"
        st.session_state.intake_error = f"An unexpected error occurred: {exc}"

    finally:
        st.rerun()
```

### Session State Keys

| Key | Type | Purpose |
|-----|------|---------|
| `intake_org_type` | str | Selected organisation type |
| `intake_user_input` | str | Free-text user input |
| `intake_model` | str | LLM model name |
| `intake_temperature` | float | Sampling temperature |
| `intake_status` | str | "idle" / "generating" / "success" / "error" |
| `generated_questionnaire` | str | JSON-serialized Questionnaire |
| `gen_llm_called` | bool | Whether LLM was actually called |
| `gen_chromadb_docs` | int | ChromaDB document count |
| `gen_standards_retrieved` | int | Number of standards retrieved |
| `gen_fallback_used` | bool | Whether fallback was used |

---

## 3. Step 2: LLM Client Initialization

**File**: `llm/client.py`

### LLMSettings (lines 72-95)

```python
class LLMSettings(BaseSettings):
    llm_base_url: str = "http://192.168.1.59:1234/v1"
    llm_model: str = "qwen/qwen3.6-35b-a3b"
    llm_timeout: float = 60.0
    llm_max_retries: int = 2
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

### LLMClient Constructor (lines 114-121)

```python
def __init__(self, settings: LLMSettings | None = None) -> None:
    self._settings = settings or _llm_settings
    self._base_url: str = self._settings.llm_base_url.rstrip("/")
    self._model: str = self._settings.llm_model
    self._timeout: float = self._settings.llm_timeout
    self._max_retries: int = self._settings.llm_max_retries
    self._temperature: float = self._settings.llm_temperature
    self._max_tokens: int = self._settings.llm_max_tokens
```

### Health Check (lines 286-302)

```python
def is_available(self) -> bool:
    try:
        resp = requests.get(
            f"{self._base_url}/models",
            timeout=self._timeout,
        )
        return resp.status_code == 200
    except Exception:
        return False
```

---

## 4. Step 3: ChromaDB Retrieval

**File**: `llm/question_generator.py` — `_retrieve_relevant_standards()` (lines 146-261)

### Step 3a: ChromaDB Status Check

```python
def _check_chromadb_status() -> tuple[bool, int]:
    try:
        client = init_chroma_client()
        collection = get_or_create_collection(client)
        count = collection.count()
        return (count > 0, count)
    except Exception:
        return (False, 0)
```

### Step 3b: Query ChromaDB

```python
def _retrieve_relevant_standards(
    user_input: str,
    organization_type: str,
    k: int = MAX_STANDARDS,  # = 5
) -> list[dict[str, Any]]:
    k = min(k, MAX_STANDARDS)

    # Check ChromaDB has documents
    has_docs, doc_count = _check_chromadb_status()
    if not has_docs:
        logger.warning("ChromaDB standards collection is empty (0 documents).")
        return []

    # Load all available standards for org-type filtering
    all_sources = _load_sources()
    applicable_categories: set[str] = set()

    # Map org types to relevant standard categories
    org_category_map: dict[str, list[str]] = {
        "life_insurer": ["APRA", "AASB", "IFRS"],
        "general_insurer": ["APRA", "AASB", "IFRS"],
        "health_insurer": ["APRA", "AASB", "IFRS"],
        "superannuation": ["APRA", "AASB", "IFRS"],
        "friendly_society": ["APRA", "AASB", "IFRS"],
        "reinsurer": ["APRA", "AASB", "IFRS"],
    }

    applicable_categories = set(org_category_map.get(organization_type.lower(), ["APRA", "AASB", "IFRS"]))

    # Filter sources by applicable categories
    applicable_sources: dict[str, str] = {}  # name -> category
    for source in all_sources:
        cat = source.get("category", "")
        if cat in applicable_categories:
            applicable_sources[source["name"]] = cat

    if not applicable_sources:
        return []

    try:
        client = init_chroma_client()
        collection = get_or_create_collection(client)

        # Query ChromaDB
        query_text = f"{user_input} {organization_type}"
        results = collection.query(
            query_texts=[query_text],
            n_results=min(k * 3, 30),  # fetch extra for filtering = min(15, 30) = 15
            include=["documents", "metadatas", "distances"],
        )

        chunks: list[dict[str, Any]] = []
        seen_standards: set[str] = set()

        documents = results["documents"][0] or []
        metadatas = results["metadatas"][0] or []
        distances = results["distances"][0] or []

        for doc_text, meta, dist in zip(documents, metadatas, distances):
            std_name = meta.get("standard_name", "")
            if not isinstance(std_name, str) or not std_name:
                continue
            if std_name not in applicable_sources:
                continue
            if std_name in seen_standards:
                continue
            seen_standards.add(std_name)

            chunks.append({
                "standard_name": std_name,
                "standard_category": applicable_sources[std_name],
                "clause": meta.get("clause", ""),
                "document": doc_text,
                "source_url": meta.get("source_url", ""),
                "distance": dist,
            })

            if len(chunks) >= k:
                break

        return chunks

    except Exception as exc:
        logger.warning("ChromaDB retrieval failed: %s", exc)
        return []
```

### ChromaDB Configuration

| Setting | Value |
|---------|-------|
| Collection name | `"standards_collection"` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` (384-dim) |
| Distance metric | Cosine distance |
| Persistence directory | `data/chroma_db/` |
| Chunk size | 500 chars (with 50 char overlap) |

---

## 5. Step 4: Prompt Construction

**File**: `llm/question_generator.py` — `_build_prompt()` (lines 269-355)

### System Prompt (lines 284-325)

```python
system_prompt = (
    "You are an Australian life insurance compliance expert. "
    "Your task is to generate a structured compliance questionnaire "
    "based on the user's organisation description and applicable "
    "regulatory standards.\n\n"
    "OUTPUT REQUIREMENTS:\n"
    "1. Return ONLY valid JSON — no markdown, no explanation, no code fences.\n"
    "2. The JSON must match this schema exactly:\n"
    "   {\n"
    '     "sections": [\n'
    '       {\n'
    '         "title": "section heading",\n'
    '         "questions": [\n'
    '           {\n'
    '             "id": "STANDARD_CLAUSE_SEQ",\n'
    '             "text": "question text",\n'
    '             "type": "boolean|text|multi_choice",\n'
    '             "default": null or boolean or string,\n'
    '             "options": ["opt1", "opt2"] or null,\n'
    '             "source_standard": "Standard Name",\n'
    '             "source_clause": "Clause reference",\n'
    '             "confidence": 0.0-1.0\n'
    "           }\n"
    "         ]\n"
    "       }\n"
    "     ]\n"
    "   }\n"
    "3. Question ID format: {standard_code}_{clause}_{seq} "
    "(e.g., CPS230_27_01, LPS115_15_02).\n"
    "4. Include source_standard, source_clause, and confidence for EACH question.\n"
    "5. Only include standards that apply to the organisation type.\n"
    "6. Generate at least 3 sections with at least 1 question each.\n"
    "7. Use type 'boolean' for yes/no questions, 'text' for open-ended, "
    "'multi_choice' for multiple-choice questions.\n"
    "8. Confidence should reflect how directly the standard applies "
    "(1.0 = directly applicable, 0.5 = partially applicable, 0.3 = tangential).\n"
    "9. Keep the questionnaire focused and practical — no more than 15 questions total.\n"
    "10. If the user mentions specific topics (e.g., reinsurance, risk management), "
    "prioritise those standards."
)
```

### User Prompt — Standards Context Block (lines 328-355)

```python
# Per standard formatting:
standards_context = ""
for i, std in enumerate(relevant_standards, 1):
    standards_context += (
        f"\n--- Standard {i}: {std['standard_name']} "
        f"[{std['standard_category']}] ---\n"
    )
    if std.get("clause"):
        standards_context += f"Clause: {std['clause']}\n"
    if std.get("source_url"):
        standards_context += f"URL: {std['source_url']}\n"
    # Truncation: hard cap at 1000 chars
    doc = std.get("document", "")
    if len(doc) > 1000:
        doc = doc[:1000] + "... [truncated]"
    standards_context += f"Content:\n{doc}\n"

# Final user prompt:
user_prompt = (
    f"Organisation type: {organization_type}\n"
    f"User description: {user_input}\n\n"
    f"Below are relevant regulatory standards retrieved from the standards database.\n"
    f"Use them to generate a compliance questionnaire tailored to this organisation.\n\n"
    f"{standards_header}{standards_context}"
    f"\nPlease generate the questionnaire JSON now."
)
```

### Approximate Prompt Sizes

| Component | Size |
|-----------|------|
| System prompt | ~1,700 chars |
| User header | ~100 chars |
| Standards context (5 standards × 1000 chars) | ~5,000 chars |
| **Total** | **~6,800 chars** |

---

## 6. Step 5: LLM API Call

**File**: `llm/client.py` — `generate()` (lines 157-254)

### Full Generate Method

```python
def generate(
    self,
    prompt: str,
    system_prompt: str,
    response_format: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": self._model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": self._temperature,
        "max_tokens": self._max_tokens,
    }

    if response_format is not None:
        payload["response_format"] = response_format  # {"type": "json_object"}

    last_exc: Exception | None = None
    delay: float = 1.0

    for attempt in range(self._max_retries + 1):  # default: 3 attempts
        try:
            resp = requests.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                timeout=self._timeout,
            )

            # If response_format caused a 400, retry without it
            if resp.status_code == 400 and "response_format" in payload:
                try:
                    error_body = resp.json() if isinstance(resp.json(), dict) else {}
                except Exception:
                    error_body = {}
                error_msg = error_body.get("error", {}).get("message", "")
                if not error_msg:
                    error_msg = error_body.get("error", "")
                if "response_format" in error_msg.lower() or "json_schema" in error_msg.lower():
                    logger.warning("response_format not supported, retrying without it")
                    del payload["response_format"]
                    continue

            resp.raise_for_status()
            body = resp.json()
            content = body["choices"][0]["message"]["content"].strip()
            return content

        except requests.exceptions.Timeout as exc:
            last_exc = exc
        except requests.exceptions.ConnectionError as exc:
            last_exc = exc
        except requests.exceptions.HTTPError as exc:
            raise LLMGenerationError(exc.response.status_code, str(exc)) from exc
        except Exception as exc:
            last_exc = exc

        if attempt < self._max_retries:
            time.sleep(delay)
            delay *= 2  # exponential backoff: 1s, 2s, 4s

    raise LLMConnectionError(
        f"{self._base_url}/chat/completions",
        cause=str(last_exc) if last_exc else "unknown",
    ) from last_exc
```

### Request Payload (what gets sent to LMStudio)

```json
{
    "model": "qwen/qwen3.6-35b-a3b",
    "messages": [
        {
            "role": "system",
            "content": "You are an Australian life insurance compliance expert..."
        },
        {
            "role": "user",
            "content": "Organisation type: life_insurer\nUser description: Check my capital adequacy compliance\n\n--- Relevant Standards ---\n--- Standard 1: CPS 230 [APRA] ---\nClause: Paragraph 1\nContent:\n{first 1000 chars of CPS 230 text}..."
        }
    ],
    "temperature": 0.3,
    "max_tokens": 4096,
    "response_format": {"type": "json_object"}
}
```

---

## 7. Step 6: JSON Parsing & Validation

**File**: `llm/question_generator.py` — `_parse_questionnaire()` (lines 363-437)

### Full Parse Method

```python
def _parse_questionnaire(json_str: str) -> Questionnaire:
    # Clean up markdown code fences
    cleaned = json_str.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Extract balanced JSON braces
    brace_count = 0
    json_end = -1
    for i, ch in enumerate(cleaned):
        if ch == "{":
            brace_count += 1
        elif ch == "}":
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1

    if json_end > 0:
        cleaned = cleaned[:json_end]

    # Try 1: Direct parse
    data = None
    parse_errors: list[str] = []
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        parse_errors.append(str(exc))

    # Try 2: Fix common LLM JSON issues
    if data is None:
        repaired = cleaned
        # Fix trailing commas before } or ]
        repaired = re.sub(r',(\s*[\]}])', r'\1', repaired)
        # Fix single quotes to double quotes
        repaired = repaired.replace("'", '"')
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as exc:
            parse_errors.append('repair attempt: ' + str(exc))

    if data is None:
        raise QuestionGenerationError(
            "LLM returned invalid JSON (tried %d attempts)" % len(parse_errors),
            cause=json.JSONDecodeError("; ".join(parse_errors), cleaned, 0),
        )

    # Validate against Pydantic schema
    try:
        return Questionnaire.model_validate(data)
    except ValidationError as exc:
        raise QuestionGenerationError(
            f"LLM JSON failed schema validation: {exc}",
            cause=exc,
        ) from exc
```

---

## 8. Step 7: Fallback Mechanism

**File**: `llm/question_generator.py` — `_default_questionnaire()` (lines 445-559)

When the LLM fails after all retries, a hardcoded fallback is returned:

```python
def _default_questionnaire(organization_type: str, user_input: str | None = None) -> Questionnaire:
    sections: list[QuestionSection] = [
        QuestionSection(
            title="Operational Risk Management (CPS 230)",
            questions=[
                Question(
                    id="CPS230_1_01",
                    text="Does the organisation have a documented operational risk management framework?",
                    type="boolean",
                    default=False,
                    source_standard="CPS 230 — Operational Risk Management",
                    source_clause="Paragraph 1",
                    confidence=0.95,
                ),
                # ... 2 more CPS 230 questions ...
            ],
        ),
        QuestionSection(
            title="Insurance Risk Charge (LPS 115)",
            questions=[...],
        ),
        QuestionSection(
            title="Insurance Contracts (AASB 17)",
            questions=[...],
        ),
    ]

    return Questionnaire(
        sections=sections,
        generated_by="fallback",
        generated_at=datetime.now(timezone.utc).isoformat(),
        organization_type=organization_type,
        user_input=user_input,
    )
```

### Fallback Trigger Conditions

| Condition | When |
|-----------|------|
| ChromaDB empty | `_retrieve_relevant_standards()` returns `[]` |
| LLM unavailable | `client.is_available()` returns `False` |
| LLM returns empty string | `not raw_response or not raw_response.strip()` |
| JSON parse fails (all retries) | `_parse_questionnaire()` raises `QuestionGenerationError` |
| Schema validation fails (all retries) | `Questionnaire.model_validate()` raises `ValidationError` |
| LLM connection error | `LLMConnectionError` raised |
| LLM timeout | `LLMTimeoutError` raised |

---

## 9. Known Failure Points

### 9.1: LLM Returns Empty Response

**Symptom**: All retries return empty string → fallback used.

**Root Cause**: The 35B model may not be fully loaded in LMStudio. When the model is listed but not loaded, the API may return empty responses under heavy load.

**Evidence from test run**:
```
LLM returned empty response on attempt 2/4
LLM returned empty response on attempt 3/4
LLM returned empty response on attempt 4/4
All attempts returned empty — using default questionnaire
```

**Fix**: Ensure the model is loaded in LMStudio UI (click "Load Model" next to `qwen/qwen3.6-35b-a3b`). If it fails, try `qwen/qwen3.6-27b` which is smaller.

### 9.2: response_format Rejected by LMStudio

**Symptom**: HTTP 400 error with "response_format" in the error message.

**Root Cause**: Not all LMStudio versions support the `response_format` parameter.

**Fix**: The client already handles this — it detects the 400, strips `response_format`, and retries. Log shows: `response_format not supported by this server, retrying without it`.

### 9.3: JSON Parse Failure

**Symptom**: LLM returns malformed JSON → repair attempts fail → fallback used.

**Root Cause**: LLM may return JSON with trailing commas, single quotes, or other non-standard formatting.

**Fix**: Two-attempt repair (trailing commas + single quotes). If still fails, fallback is used.

### 9.4: ChromaDB Empty

**Symptom**: No standards retrieved → LLM gets no regulatory context.

**Root Cause**: Standards not ingested or ingestion failed.

**Fix**: Go to Standards page → click "Populate ChromaDB" button.

### 9.5: Prompt Too Long

**Current state**: ~6,800 chars total (system ~1,700 + user ~5,000).

**Impact**: Larger prompts increase the chance of empty LLM responses, especially with the 35B model.

**Current mitigations**:
- `MAX_STANDARDS = 5` (reduced from 10)
- Document truncation at 1,000 chars per chunk
- Fetch `min(k*3, 30)` results from ChromaDB, then filter to top-k

### 9.6: LLM Timeout

**Current timeout**: 60 seconds (default in `LLMSettings`).

**Impact**: The 35B model may take longer than 60s to generate a response. The user requested increasing this to 30 minutes (1800s), but this was only set in the UI settings, not in the `LLMSettings` default.

**Fix**: Either set `llm_timeout=1800` in the `.env` file or ensure the UI passes the correct timeout value.

---

## 10. Full Call Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        FREE-TEXT → QUESTIONNAIRE                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. USER INPUT (ui/questionnaire_intake.py)                            │
│     ┌───────────────────────────────────────────────┐                  │
│     │ Organisation type: life_insurer               │                  │
│     │ User input: "Check my capital adequacy"       │                  │
│     │ Model: qwen/qwen3.6-35b-a3b                   │                  │
│     │ Temperature: 0.3                              │                  │
│     └──────────────────────────┬────────────────────┘                  │
│                                │                                        │
│  2. LLM CLIENT INIT (llm/client.py)                                    │
│     ┌───────────────────────────────────────────────┐                  │
│     │ LLMSettings(base_url, model, temp, max_tokens)│                  │
│     │ LLMClient(settings)                           │                  │
│     └──────────────────────────┬────────────────────┘                  │
│                                │                                        │
│  3. CHROMADB RETRIEVAL                                         │
│     ┌───────────────────────────────────────────────┐                  │
│     │ _check_chromadb_status() → (True, 2743)       │                  │
│     │ _retrieve_relevant_standards():               │                  │
│     │   query_text = "Check my capital adequacy life_insurer"             │
│     │   ChromaDB.query(n_results=15)                │                  │
│     │   Filter by applicable_categories             │                  │
│     │   Deduplicate by standard_name                │                  │
│     │   Return top-5 chunks                          │                  │
│     └──────────────────────────┬────────────────────┘                  │
│                                │                                        │
│  4. PROMPT CONSTRUCTION                                          │
│     ┌───────────────────────────────────────────────┐                  │
│     │ System prompt: ~1,700 chars                   │                  │
│     │ User prompt: org_type + user_input + 5×1000   │                  │
│     │ Total: ~6,800 chars                           │                  │
│     └──────────────────────────┬────────────────────┘                  │
│                                │                                        │
│  5. LLM API CALL (llm/client.py)                                       │
│     ┌───────────────────────────────────────────────┐                  │
│     │ POST /chat/completions                        │                  │
│     │ model: qwen/qwen3.6-35b-a3b                   │                  │
│     │ max_tokens: 4096                              │                  │
│     │ response_format: {"type": "json_object"}      │                  │
│     │ timeout: 60s (or 1800s if set)                │                  │
│     │                                                 │                  │
│     │ On 400 + "response_format" → strip & retry    │                  │
│     │ On Timeout → retry (exponential backoff)       │                  │
│     │ On ConnectionError → retry                     │                  │
│     │ On 200 → extract choices[0].message.content   │                  │
│     └──────────────────────────┬────────────────────┘                  │
│                                │                                        │
│  6. JSON PARSING (llm/question_generator.py)                           │
│     ┌───────────────────────────────────────────────┐                  │
│     │ Strip markdown fences                          │                  │
│     │ Extract balanced braces                        │                  │
│     │ Try 1: json.loads()                           │                  │
│     │ Try 2: Fix trailing commas + single quotes    │                  │
│     │ Validate: Questionnaire.model_validate()      │                  │
│     └──────────────────────────┬────────────────────┘                  │
│                                │                                        │
│  7. QUESTIONNAIRE OBJECT                                       │
│     ┌───────────────────────────────────────────────┐                  │
│     │ Questionnaire(                                │                  │
│     │   sections=[QuestionSection(...), ...],       │                  │
│     │   generated_by="llm",                         │                  │
│     │   generated_at="2026-05-17T...",              │                  │
│     │   organization_type="life_insurer",           │                  │
│     │   user_input="Check my capital adequacy"      │                  │
│     │ )                                              │                  │
│     └───────────────────────────────────────────────┘                  │
│                                                                         │
│  ─── FALLBACK PATH (on any failure after retries) ───                   │
│     _default_questionnaire() → hardcoded CPS 230 + LPS 115 + AASB 17  │
│     generated_by="fallback"                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Configuration Reference

### LLMSettings Defaults (llm/client.py)

| Setting | Default | Description |
|---------|---------|-------------|
| `llm_base_url` | `http://192.168.1.59:1234/v1` | LMStudio API endpoint |
| `llm_model` | `qwen/qwen3.6-35b-a3b` | Model identifier |
| `llm_timeout` | `60.0` | Request timeout in seconds |
| `llm_max_retries` | `2` | Client-level retries (3 total attempts) |
| `llm_temperature` | `0.3` | Sampling temperature |
| `llm_max_tokens` | `4096` | Max response tokens |

### question_generator.py Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `MAX_STANDARDS` | `5` | Max standards to retrieve |
| `MAX_RETRIES` | `3` | Caller-level retries (4 total attempts) |
| `SOURCES_YAML_PATH` | `standards_ingestion/sources.yaml` | Standards catalog |

### ChromaDB Configuration (standards_ingestion/embedder.py)

| Setting | Value |
|---------|-------|
| Collection name | `standards_collection` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Embedding dimension | 384 |
| Distance metric | Cosine |
| Persistence dir | `data/chroma_db/` |

### Ingestion Configuration (standards_ingestion/parser.py)

| Setting | Value |
|---------|-------|
| Chunk size | 500 characters |
| Chunk overlap | 50 characters |
| Clause regex | `(?:Paragraph|Clause|¶)\s*(\d+[A-Z]?(?:\([a-z]+\))?)` |

---

## Appendix A: Retry Architecture

The pipeline has **two layers** of retry:

### Layer 1: LLMClient.generate() (3 attempts)

| Error | Retry? | Backoff |
|-------|--------|---------|
| HTTP 400 + response_format error | Yes, strip & retry | None (immediate) |
| Timeout | Yes | 1s → 2s → 4s |
| ConnectionError | Yes | 1s → 2s → 4s |
| HTTPError (non-400) | No | — |
| Any other Exception | Yes | 1s → 2s → 4s |

### Layer 2: generate_questionnaire() (4 attempts)

| Error | Retry? |
|-------|--------|
| Empty response | Yes |
| JSON parse failure | Yes |
| Schema validation failure | Yes |
| LLMConnectionError | Yes |
| LLMTimeoutError | Yes |
| LLMGenerationError | Yes |

### Total Max Attempts: 12 (3 × 4)

### Total Max Time: ~300s (3 retries × 4 attempts × ~10s each including backoff)

---

## Appendix B: Questionnaire Schema (engine/schemas.py)

```python
class Questionnaire(BaseModel):
    sections: list[QuestionSection]
    generated_by: str  # "llm" or "fallback"
    generated_at: str  # ISO 8601
    organization_type: str
    user_input: str | None = None

class QuestionSection(BaseModel):
    title: str
    questions: list[Question]

class Question(BaseModel):
    id: str
    text: str
    type: str  # "boolean" | "text" | "multi_choice"
    default: Any  # None | bool | str
    options: list[str] | None = None
    source_standard: str | None = None
    source_clause: str | None = None
    confidence: float = 1.0
    applies_to_standard: str | None = None
```
