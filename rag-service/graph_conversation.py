from langgraph.graph import StateGraph, END
from services.llm_service import call_llm
from services.email_service import send_email
from utils.chroma_client import retrieve_query
from utils.cleanupFunc import collect_docs
from utils.memory_utils import HybridMemory
from config import VECTOR_COLLECTION, LLM_LIGHT_MODEL


# --- Helpers ---
def ensure_dict(state, node_name="node"):
    if isinstance(state, dict):
        print(f"[{node_name}] ✅ dict keys: {list(state.keys())}")
        return state
    print(f"[{node_name}] ❌ returned {type(state)} -> wrapping")
    if isinstance(state, list):
        return state[0] if state else {}
    return {"answer": str(state)}


# --- Ground Truth Check ---
def enforce_grounding(answer: str, docs: str) -> str:
    prompt = f"""
    You are a strict insurance assistant.

    Answer: {answer}

    Supporting Document:
    {docs}

    Task:
    - If the answer is clearly supported by the document, reply: SUPPORTED
    - If the answer is not supported or is uncertain, reply: NOT SUPPORTED
    """
    verdict = call_llm(prompt, LLM_LIGHT_MODEL)
    return str(verdict).strip().upper()  # SUPPORTED / NOT SUPPORTED


# --- Router (always start with RAG) ---
def router(state: dict):
    state["route"] = "RAG_AGENT"
    print("[router] default route: RAG_AGENT")
    return ensure_dict(state, "router")

def rewrite_query(question: str, history: str) -> str:
    """
    Rewrite the user's latest question into a self-contained query
    that can be understood without any prior conversation.
    """
    prompt = f"""
    Rewrite the user's latest question into a self-contained query
    that can be understood without any prior conversation.

    Conversation History:
    {history or "[No prior conversation]"}

    Latest Question:
    {question}

    Rewritten Query:
    """

    return str(call_llm(prompt, LLM_LIGHT_MODEL)).strip()


def rag_agent(state: dict):
    question = state.get("question", "").strip()
    memory: HybridMemory = state.get("memory")

    # Load history
    past = memory.load_memory_variables({}) if memory else {"history": ""}
    history_text = past.get("history", "").strip()

    # Rewrite query
    rewritten_query = rewrite_query(question, history_text)
    print(f"[rag_agent] Original Q: {question}")
    print(f"[rag_agent] Rewritten Q: {rewritten_query}")

    # Retrieve docs (just use clean query for retriever)
    results = retrieve_query(rewritten_query, VECTOR_COLLECTION, top_k=5)

    # Fallback: try raw question if no docs
    if not results:
        print("[rag_agent] ⚠️ No docs for rewritten query, retrying with raw question")
        results = retrieve_query(question, VECTOR_COLLECTION, top_k=5)

    docs = collect_docs(results)
    doc_text = "\n".join(docs).strip()

    # Policy context only for answering
    policy_context = ", ".join(filter(None, [
        f"Policy Number: {state.get('policy_number')}" if state.get("policy_number") else None,
        f"Type: {state.get('policy_type')}" if state.get("policy_type") else None,
        f"Policyholder: {state.get('policyholder_name')}" if state.get("policyholder_name") else None
    ])) or "[Not available]"

    # Build answering prompt
    prompt = f"""
    You are an Insurance Agent.

    Answer naturally and conversationally, as if you are assisting a customer.
    Use ONLY the information in the provided policy document.
    If the document does not contain the answer, say so politely.

    User Question: {question}
    Rewritten Query: {rewritten_query}
    Policy Context: {policy_context}
    Conversation Context: {history_text}

    Retrieved Policy Chunks:
    {doc_text or "[No documents retrieved]"}
    """

    raw_answer = str(call_llm(prompt, LLM_LIGHT_MODEL)).strip()

    # Grounding check
    verdict = enforce_grounding(raw_answer, doc_text)
    print(f"[rag_agent] VERDICT={verdict} | RAW={raw_answer[:120]}...")

    if verdict == "SUPPORTED":
        state["rag_answer"] = state["answer"] = raw_answer
        print(f"[rag_agent] ✅ answered: {raw_answer[:80]}...")
    else:
        state["handoff"] = True
        state["answer"] = "This question requires assistance from our support team."
        print("[rag_agent] ⏩ escalation → HUMAN_AGENT")

    if memory:
        memory.save_context({"input": question}, {"output": state["answer"]})

    return ensure_dict(state, "rag_agent")


# --- Human Agent ---
def human_agent(state: dict):
    # Already handled in rag_agent
    print(f"[human_agent] handoff triggered: {state.get('answer')}")
    return ensure_dict(state, "human_agent")


# --- End Detector (LLM, last 2–3 turns) ---
def detect_conversation_end(state: dict) -> bool:
    memory = state.get("memory")
    past = memory.load_memory_variables({}) if memory else {"history": ""}
    history_text = past.get("history", "").strip()

    # Extract last 3 exchanges (≈6 lines: user + assistant pairs)
    if history_text:
        recent_lines = history_text.split("\n")[-6:]
        recent_text = "\n".join(recent_lines)
    else:
        recent_text = "[No prior conversation available]"

    user_message = state.get("question", "").strip()

    prompt = f"""
    Recent conversation:
    {recent_text}

    Latest user message: "{user_message}"

    Task:
    - Reply YES if the user clearly intends to end the conversation
      (e.g., "thanks", "thank you, that's all", "bye", "no further questions", "done").
    - Reply NO if they are asking another question or continuing the chat.
    Respond with ONLY YES or NO.
    """

    verdict = call_llm(prompt, LLM_LIGHT_MODEL)
    verdict_str = str(verdict).strip().upper()

    return verdict_str == "YES"

# --- Responder ---
def responder(state: dict):
    answer = state.get("rag_answer") or state.get("answer")
    state["answer"] = answer or "No response available."

    memory = state.get("memory")
    if not memory:
        return state

    # Load memory variables (formatted history from HybridMemory)
    past = memory.load_memory_variables({})

    history_text = past.get("history", "").strip()
    if history_text:
        print("[conversation history]\n" + history_text)
    else:
        print("[conversation history] No conversation available yet.") 

    if detect_conversation_end(state):
        state["end_conversation"] = True

    print(f"[responder] final answer: {state['answer'][:80]}...")
    return ensure_dict(state, "responder")


# --- Summarizer ---
def summarize_conversation(state: dict):
    memory = state.get("memory")
    if not memory:
        return state

    past = memory.load_memory_variables({})
    history_text = past.get("history", "").strip() or "[No conversation history available]"

    print(f"[summarizer] Conversation history:\n{history_text}")

    prompt = f"""
    You are an insurance assistant. Summarize the conversation faithfully.

    Conversation:
    {history_text}

    Task:
    1. First, provide a clear **summary of the conversation** in plain text.
    2. Then add the following three sections:

    ### Critical Information
    - List only facts, definitions, coverage points, waiting periods, exclusions, or conditions explicitly discussed.
    - If none were discussed, write: "No critical information discussed."

    ### Resolution
    - State if the user’s question(s) were answered, partially answered, not answered, or escalated.
    - If the policy coverage/approval could not be determined, write that explicitly.
    - If nothing was resolved, write: "No questions were resolved."

    ### Action Items
    - If the assistant escalated, write: "Await support team follow-up."
    - If clarification or approval is required (e.g., surgery, treatment), write: "Support team must review."
    - If everything was resolved, write: "No action required."

    Rules:
    - Do NOT invent information not present in the conversation.
    - Output must always have: conversation summary + 3 sections in this exact order.
    """

    resp = call_llm(prompt, LLM_LIGHT_MODEL)
    structured_summary = str(resp).strip()

    subject = f"Insurance Conversation Summary – Policy {state.get('policy_number')}"
    body = (
        f"Hello {state.get('policyholder_name') or 'Policyholder'},\n\n"
        f"Here’s a summary of your recent conversation:\n\n"
        f"{structured_summary}\n\n"
        f"---\n"
        f"### Full Conversation Log (for reference)\n\n"
        f"{history_text}\n\n"
        "Best regards,\nYour Insurance Team"
    )

    send_email(subject, body)

    print("[summarizer] ✅ Summary + conversation log email sent")
    state["conversation_summary"] = structured_summary
    return state



# --- Graph Assembly ---
graph = StateGraph(dict)

graph.add_node("router", router)
graph.add_node("rag_agent", rag_agent)
graph.add_node("human_agent", human_agent)
graph.add_node("responder", responder)
graph.add_node("summarizer", summarize_conversation)

graph.set_entry_point("router")

# router always → rag_agent
graph.add_edge("router", "rag_agent")

# rag_agent → responder
graph.add_edge("rag_agent", "responder")

# human_agent (if escalated) → responder
graph.add_edge("human_agent", "responder")

# summarizer only if end_conversation=True
graph.add_conditional_edges(
    "responder",
    lambda s: "summarizer" if s.get("end_conversation") else "end",
    {"summarizer": "summarizer", "end": END},
)

graph.add_edge("summarizer", END)

conversation_chain = graph.compile()
