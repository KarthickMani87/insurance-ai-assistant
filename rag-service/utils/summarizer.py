from services.llm_service import llm

def summarize_with_llm(conversation: list[str]) -> str:
    """
    Summarize a list of conversation turns into a concise summary.
    """
    transcript = "\n".join([f"User: {q}" for q in conversation])
    prompt = f"""
    Summarize this insurance-related conversation into key points:
    {transcript}

    Include:
    - Policy number (if mentioned)
    - Important user questions
    - Answers given
    - Final conclusion
    Respond in plain text, concise.
    """
    return llm.invoke(prompt).strip()


def simple_summary(conversation: list[str]) -> str:
    """
    Fallback: Just concatenate conversation turns.
    """
    return " | ".join(conversation)

