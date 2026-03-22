import logging
from langchain_core.prompts import PromptTemplate
from langchain.agents import create_react_agent, AgentExecutor
from backend.services.tools import get_tools
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

def run_agent(user_message: str, file_context: dict = None, chat_history: list = None) -> dict:
    """
    Core logic to handle user input, decide on tool usage, and generate a response.
    Now receives `chat_history` from the database.
    """
    settings = get_settings()

    deterministic_answer = _maybe_answer_from_file_context(user_message, file_context)
    if deterministic_answer:
        return {"reply": deterministic_answer, "steps": []}
    
    # Lazy import to prevent gRPC multi-processing deadlock on Windows Uvicorn '--reload' workers
    from langchain_groq import ChatGroq

    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        api_key=settings.GROQ_API_KEY,
        temperature=0.2,
    )

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
    agent = create_react_agent(llm, tools, prompt_template)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=6,
        max_execution_time=45,
        handle_tool_error=True,
        return_intermediate_steps=True,
    )

    try:
        response = agent_executor.invoke({"input": user_message})
        output = response.get("output", "I could not generate a response.")
        
        raw_steps = response.get("intermediate_steps", [])
        steps = []
        for action, observation in raw_steps:
            steps.append({
                "tool": action.tool,
                "input": getattr(action, "tool_input", str(action)),
                "output": str(observation)
            })
            
        return {"reply": _coerce_output_to_str(output), "steps": steps}
    except Exception as e:
        logger.exception("Agent execution failed")
        error_text = str(e)
        lowered = error_text.lower()

        if "401" in lowered or "unauthorized" in lowered:
            reply = "LLM provider authentication failed. Please verify GROQ_API_KEY and try again."
        elif "iteration limit" in lowered or "time limit" in lowered:
            reply = "I hit a reasoning limit for this request. Please rephrase with more specific details, or upload the file again for fresh context."
        else:
            reply = "There was an issue generating the response. Please try again."

        return {"reply": reply, "steps": []}
