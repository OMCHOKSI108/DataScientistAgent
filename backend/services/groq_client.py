"""
GROQ API Client Service
Initializes the GROQ client and provides functions
for generating text responses.
"""

from groq import Groq
from backend.config import get_settings

# Initialize the GROQ client on module load
settings = get_settings()

if not settings.GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY is not set in the environment variables.")
    client = None
else:
    client = Groq(api_key=settings.GROQ_API_KEY)


def generate_response(prompt: str) -> str:
    """
    Generate a basic text response from GROQ.
    (This simple version will be upgraded to a LangChain Agent in Chunk 4)

    Args:
        prompt: The user's input text.

    Returns:
        The generated response string.
    """
    if not settings.GROQ_API_KEY or not client:
        return "Error: GROQ_API_KEY is missing. Please configure it in your .env file."

    try:
        # Use a GROQ model
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as exc:
        return f"Error communicating with GROQ API: {str(exc)}"
