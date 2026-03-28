import logging
from langchain_core.prompts import PromptTemplate
from langchain.agents import create_react_agent, AgentExecutor
from backend.services.tools import get_tools, run_python_code_fast
from backend.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_BASE = (
    "You are an expert AI Data Scientist Agent. Your goal is to give clean, structured, and highly readable responses.\n\n"
    "RESPONSE FORMATTING RULES (Apply these ONLY to your 'Final Answer'):\n"
    "1. NEVER expose internal reasoning or tool usage (e.g., NEVER say 'I used the python_repl tool', 'I searched the web', or 'Here are the steps I took'). Just give the raw answer.\n"
    "2. Put the final result/answer FIRST. Do not write a long introduction.\n"
    "3. Keep it extremely short and clean. Avoid long paragraphs. Use concise bullet points only when describing complex information.\n"
    "4. Format dynamically based on the query type (e.g. use clean markdown code blocks without surrounding prose for coding questions, and direct headline summaries for news).\n"
    "5. If you face a system error or missing package, perfectly state: 'There was an issue generating the response. Please try again.'\n\n"
    "CRITICAL AGENT RULES:\n"
    "You MUST strictly follow the ReAct format (Thought: / Action: / Action Input:). Do not use markdown for the Action or Action Input lines.\n"
)

def _build_system_prompt(file_context: dict = None) -> str:
    """Construct the system prompt, injecting file context if available."""
    sys_prompt = SYSTEM_PROMPT_BASE

    if not file_context:
        return sys_prompt

    file_type = file_context.get("file_type")
    filename = file_context.get("original_name")
    file_path = file_context.get("file_path", "").replace("\\", "/")

    sys_prompt += f"\n\n[ATTACHMENT CONTEXT]\nThe user attached a {file_type} file: '{filename}'.\n"

    if file_type == "csv":
        cols = ", ".join(file_context.get("column_names", []))
        sys_prompt += (
            f"The file is saved locally at: `{file_path}`\n"
            f"Columns: {cols}\n\n"
            f"IMPORTANT: To answer ANY question about this dataset, you MUST use your python_repl tool.\n"
            f"Write Python code using pandas to load `{file_path}`, compute the answer, and print it.\n"
        )
    elif file_type == "pdf":
        sys_prompt += (
            f"\nThe user has uploaded a PDF document named '{filename}'.\n"
            f"Its contents have been extracted and saved to your FAISS vector database.\n"
            f"IMPORTANT: You MUST use the `rag_search` tool to search for information inside this document to answer the user's questions.\n"
        )

    return sys_prompt

def _coerce_output_to_str(output) -> str:
    if isinstance(output, str):
        cleaned = output.strip()
        if not cleaned:
            return "I processed your request but didn't generate visible output."

        # Strip common ReAct parser artifacts that can leak into user responses.
        if "Invalid Format:" in cleaned:
            cleaned = cleaned.split("Invalid Format:", 1)[0].strip()

        cleaned = cleaned.replace("**Final Answer**", "").strip()

        if "Final Answer:" in cleaned:
            cleaned = cleaned.split("Final Answer:", 1)[1].strip()

        return cleaned or "There was an issue generating the response. Please try again."
    if isinstance(output, dict):
        return str(output.get("output", output))
    return str(output)


def _maybe_answer_from_file_context(user_message: str, file_context: dict | None) -> str | None:
    """Return a deterministic answer for common metadata questions about uploaded files."""
    if not file_context or not isinstance(file_context, dict):
        return None

    message = (user_message or "").strip().lower()
    file_type = (file_context.get("file_type") or "").lower()

    if file_type == "csv":
        rows = file_context.get("rows")
        columns = file_context.get("columns")
        column_names = file_context.get("column_names") or []

        asks_columns = any(
            k in message for k in [
                "how many columns",
                "number of columns",
                "total columns",
                "columns count",
                "count columns",
            ]
        )
        asks_rows = any(k in message for k in ["how many rows", "number of rows", "total rows", "rows count"])
        asks_shape = any(k in message for k in ["shape", "dimensions", "dataset size"])
        asks_headers = any(
            k in message for k in [
                "column names",
                "headers",
                "columns are",
                "list columns",
                "list of columns",
                "show columns",
            ]
        )

        # General fallback for column-list intent phrased in many ways.
        if not asks_headers and "column" in message and any(k in message for k in ["list", "show", "what are", "which"]):
            asks_headers = True

        if asks_columns and isinstance(columns, int):
            return f"The dataset has {columns} columns."

        if asks_rows and isinstance(rows, int):
            return f"The dataset has {rows} rows."

        if asks_shape and isinstance(rows, int) and isinstance(columns, int):
            return f"The dataset shape is {rows} rows x {columns} columns."

        if asks_headers and column_names:
            return "Columns:\n- " + "\n- ".join(str(name) for name in column_names)

    if file_type == "pdf":
        asks_page_count = any(k in message for k in ["how many pages", "page count", "total pages"])
        pages = file_context.get("total_pages")
        if asks_page_count and isinstance(pages, int):
            return f"The PDF has {pages} pages."

    return None


def _maybe_run_csv_fast_analysis(user_message: str, file_context: dict | None) -> str | None:
    """Run deterministic CSV analysis for common intents without going through ReAct."""
    if not file_context or not isinstance(file_context, dict):
        return None

    if (file_context.get("file_type") or "").lower() != "csv":
        return None

    file_path = (file_context.get("file_path") or "").replace("\\", "/")
    if not file_path:
        return None

    message = (user_message or "").strip().lower()
    column_names = [str(c) for c in (file_context.get("column_names") or [])]

    asks_distribution = any(k in message for k in ["distribution", "histogram", "dist"]) or (
        "target" in message and "column" in message
    )
    if not asks_distribution:
        return None

    selected_col = None
    for col in column_names:
        if col.lower() in message:
            selected_col = col
            break

    if selected_col is None and "target" in message:
        if "selling_price" in column_names:
            selected_col = "selling_price"
        elif column_names:
            selected_col = column_names[-1]

    if selected_col:
        code = (
            "import pandas as pd\n"
            f"df = pd.read_csv(r'''{file_path}''')\n"
            f"col = r'''{selected_col}'''\n"
            "if col not in df.columns:\n"
            "    print(f'Column not found: {col}')\n"
            "else:\n"
            "    s = df[col]\n"
            "    print(f'## Distribution for {col}')\n"
            "    print(f'Count: {int(s.count())}')\n"
            "    print(f'Nulls: {int(s.isna().sum())}')\n"
            "    if pd.api.types.is_numeric_dtype(s):\n"
            "        print(s.describe(percentiles=[0.25, 0.5, 0.75]).to_string())\n"
            "    else:\n"
            "        print(s.value_counts(dropna=False).head(20).to_string())\n"
        )
        return run_python_code_fast(code)

    code = (
        "import pandas as pd\n"
        f"df = pd.read_csv(r'''{file_path}''')\n"
        "summary = []\n"
        "for col in df.columns:\n"
        "    s = df[col]\n"
        "    if pd.api.types.is_numeric_dtype(s):\n"
        "        d = s.describe()\n"
        "        summary.append(f'{col}: mean={d.get(\"mean\", \"n/a\")}, min={d.get(\"min\", \"n/a\")}, max={d.get(\"max\", \"n/a\")}, nulls={int(s.isna().sum())}')\n"
        "    else:\n"
        "        top = s.value_counts(dropna=False).head(1)\n"
        "        top_label = top.index[0] if len(top.index) else 'n/a'\n"
        "        top_count = int(top.iloc[0]) if len(top.values) else 0\n"
        "        summary.append(f'{col}: top={top_label} ({top_count}), nulls={int(s.isna().sum())}')\n"
        "print('## Column distribution summary')\n"
        "print('\\n'.join(summary))\n"
    )
    return run_python_code_fast(code)


def _build_llm_candidates(settings):
    """Build provider candidates in priority order based on settings."""
    provider = (settings.LLM_PROVIDER or "auto").strip().lower()
    candidates = []

    def add_gemini():
        if not settings.GEMINI_API_KEY:
            return
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            candidates.append(
                (
                    "gemini",
                    ChatGoogleGenerativeAI(
                        model=settings.GEMINI_MODEL,
                        google_api_key=settings.GEMINI_API_KEY,
                        temperature=0.2,
                    ),
                )
            )
        except Exception as exc:
            logger.warning(f"Gemini provider unavailable: {type(exc).__name__}")

    def add_groq():
        if not settings.GROQ_API_KEY:
            return
        try:
            from langchain_groq import ChatGroq

            candidates.append(
                (
                    "groq",
                    ChatGroq(
                        model="llama-3.1-8b-instant",
                        api_key=settings.GROQ_API_KEY,
                        temperature=0.2,
                    ),
                )
            )
        except Exception as exc:
            logger.warning(f"Groq provider unavailable: {type(exc).__name__}")

    def add_openrouter():
        if not settings.OPENROUTER_API_KEY:
            return
        try:
            from langchain_openai import ChatOpenAI

            candidates.append(
                (
                    "openrouter",
                    ChatOpenAI(
                        model="anthropic/claude-3.5-sonnet",
                        api_key=settings.OPENROUTER_API_KEY,
                        base_url="https://openrouter.ai/api/v1",
                        temperature=0.2,
                    ),
                )
            )
        except Exception as exc:
            logger.warning(f"OpenRouter provider unavailable: {type(exc).__name__}")

    if provider == "openrouter":
        add_openrouter()
        add_gemini()
        add_groq()
    elif provider == "gemini":
        add_gemini()
        add_openrouter()
        add_groq()
    elif provider == "groq":
        add_groq()
        add_openrouter()
        add_gemini()
    else:
        # auto: prefer OpenRouter first
        add_openrouter()
        add_gemini()
        add_groq()

    return candidates

def run_agent(user_message: str, file_context: dict = None, chat_history: list = None) -> dict:
    """
    Core logic to handle user input, decide on tool usage, and generate a response.
    Now receives `chat_history` from the database.
    """
    settings = get_settings()

    deterministic_answer = _maybe_answer_from_file_context(user_message, file_context)
    if deterministic_answer:
        return {"reply": deterministic_answer, "steps": []}

    fast_csv_answer = _maybe_run_csv_fast_analysis(user_message, file_context)
    if fast_csv_answer:
        return {"reply": fast_csv_answer, "steps": [{"tool": "python_repl", "input": "deterministic_fast_path", "output": "completed"}]}

    tools = get_tools()
    sys_prompt = _build_system_prompt(file_context)

    # Format previous chat history into a readable transcript string
    if chat_history:
        history_transcript = ""
        recent_history = chat_history[-10:] # Keep context window optimal
        for msg in recent_history:
            role_label = "User" if msg.get("role") == "user" else "Assistant"
            # Escape curly braces so LangChain PromptTemplate doesn't treat history as input variables
            safe_content = str(msg.get('content', '')).replace('{', '{{').replace('}', '}}')
            history_transcript += f"{role_label}: {safe_content}\n"
        
        sys_prompt += f"\n\n--- PREVIOUS CONVERSATION HISTORY ---\n{history_transcript}\n-----------------------------------\n\n"

    react_template = sys_prompt + """
You must answer the user's questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}"""

    prompt_template = PromptTemplate.from_template(react_template)
    llm_candidates = _build_llm_candidates(settings)

    if not llm_candidates:
        return {
            "reply": "No LLM provider is configured. Set GEMINI_API_KEY or GROQ_API_KEY in your environment.",
            "steps": [],
        }

    last_error = None
    for provider_name, llm in llm_candidates:
        try:
            agent = create_react_agent(llm, tools, prompt_template)
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True,
                handle_parsing_errors=True,
                max_iterations=5,
                max_execution_time=35,
                handle_tool_error=True,
                return_intermediate_steps=True,
            )

            response = agent_executor.invoke({"input": user_message})
            output = response.get("output", "I could not generate a response.")

            raw_steps = response.get("intermediate_steps", [])
            steps = []
            for action, observation in raw_steps:
                steps.append(
                    {
                        "tool": action.tool,
                        "input": getattr(action, "tool_input", str(action)),
                        "output": str(observation),
                    }
                )

            return {"reply": _coerce_output_to_str(output), "steps": steps}
        except Exception as exc:
            last_error = exc
            logger.warning(f"Provider {provider_name} failed, trying next provider: {type(exc).__name__}")

    logger.exception("Agent execution failed", exc_info=last_error)
    error_text = str(last_error) if last_error else "unknown_error"
    lowered = error_text.lower()

    if "401" in lowered or "unauthorized" in lowered:
        reply = "LLM provider authentication failed. Please verify GEMINI_API_KEY or GROQ_API_KEY and try again."
    elif "iteration limit" in lowered or "time limit" in lowered:
        reply = "I hit a reasoning limit for this request. Please ask for a specific column distribution (for example, selling_price distribution)."
    else:
        reply = "There was an issue generating the response. Please try again."

    return {"reply": reply, "steps": []}
