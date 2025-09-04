from datetime import datetime, timedelta
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


# --- Tools ---
def check_policy_status(policy_number: str, start_date: str, end_date: str):
    if not start_date or not end_date:
        return {"status": "error", "message": "Missing policy dates for status check."}

    today = datetime.today().date()
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()

    if today < start:
        return {"status": "inactive", "message": f"Policy {policy_number} has not started yet (starts {start})."}
    elif start <= today <= end:
        return {"status": "active", "message": f"Policy {policy_number} is currently active (valid until {end})."}
    else:
        return {"status": "expired", "message": f"Policy {policy_number} expired on {end}."}


def check_waiting_period(start_date: str, waiting_days: int = 30):
    if not start_date:
        return {"status": "error", "message": "Missing policy start date for waiting period check."}

    today = datetime.today().date()
    start = datetime.fromisoformat(start_date).date()
    waiting_end = start + timedelta(days=waiting_days)

    if today < start:
        return {
            "status": "not_started",
            "message": f"Policy starts on {start}. Waiting period of {waiting_days} days applies after start date."
        }
    elif today < waiting_end:
        remaining = (waiting_end - today).days
        return {
            "status": "waiting",
            "message": f"Still in waiting period ({remaining} day(s) left). Claims not yet allowed."
        }
    else:
        return {"status": "active", "message": "Waiting period has ended. Claims are now allowed."}


def renew_policy(policy_number: str):
    if not policy_number:
        return {"status": "error", "message": "Missing policy number for renewal request."}

    return {
        "status": "renewal_requested",
        "message": f"Renewal request for policy {policy_number} has been submitted. Our team will contact you."
    }

# --- Query Rewriting ---
def rewrite_query(question: str, history: str) -> str:
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


# --- RAG Agent ---
def rag_agent(state: dict):
    question = state.get("question", "").strip()
    memory: HybridMemory = state.get("memory")

    past = memory.load_memory_variables({}) if memory else {"history": ""}
    history_text = past.get("history", "").strip()

    rewritten_query = rewrite_query(question, history_text)
    results = retrieve_query(rewritten_query, VECTOR_COLLECTION, top_k=5)
    if not results:
        results = retrieve_query(question, VECTOR_COLLECTION, top_k=5)

    docs = collect_docs(results)
    doc_text = "\n".join(docs).strip()

    state["retrieved_docs"] = doc_text
    state["rewritten_query"] = rewritten_query
    state["history_text"] = history_text

    print(f"[rag_agent] Retrieved {len(docs)} docs")
    return ensure_dict(state, "rag_agent")


# --- Decision Agent ---
def decision_agent(state: dict):
    question = state.get("question", "").strip()
    doc_text = state.get("retrieved_docs", "")
    rewritten_query = state.get("rewritten_query", "")
    history_text = state.get("history_text", "")

    policy_number = state.get("policy_number")
    start_date = state.get("start_date")
    end_date = state.get("end_date")
    waiting_days = state.get("waiting_period_days", 30)  # still optional
    policyholder_name = state.get("policyholder_name")
    insurance_provider = state.get("insurance_provider")
    policy_type = state.get("policy_type")

    # LLM decides if RAG or function
    prompt = f"""
    User Question: {question}

    Policy Info:
    - Policy Number: {policy_number}
    - Policyholder: {policyholder_name}
    - Insurance Provider: {insurance_provider}
    - Policy Type: {policy_type}
    - Start Date: {start_date}
    - End Date: {end_date}
    - Waiting Period (days): {waiting_days}

    Retrieved Docs:
    {doc_text or "[No documents]"}

    Decide:
    - Reply "RAG" if the answer is in the documents.
    - Reply "CHECK_STATUS" for active/expired checks.
    - Reply "WAITING_PERIOD" for waiting period questions.
    - Reply "RENEW_POLICY" for renewal requests.
    Only reply with one of: RAG, CHECK_STATUS, WAITING_PERIOD, RENEW_POLICY
    """
    decision = str(call_llm(prompt, LLM_LIGHT_MODEL)).strip().upper()
    print(f"[decision_agent] decision={decision}")

    if decision == "CHECK_STATUS":
        result = check_policy_status(policy_number, start_date, end_date)
        state["answer"] = result["message"]

    elif decision == "WAITING_PERIOD":
        result = check_waiting_period(start_date, waiting_days)
        state["answer"] = result["message"]

    elif decision == "RENEW_POLICY":
        result = renew_policy(policy_number)
        state["answer"] = result["message"]

    else:  # fallback to RAG
        policy_context = ", ".join(filter(None, [
            f"Policy Number: {policy_number}" if policy_number else None,
            f"Policyholder: {policyholder_name}" if policyholder_name else None,
            f"Insurance Provider: {insurance_provider}" if insurance_provider else None,
            f"Type: {policy_type}" if policy_type else None,
        ])) or "[Not available]"

        rag_prompt = f"""
        You are an Insurance Agent.

        Answer conversationally, grounded in the retrieved docs.
        If the docs do not contain the answer, say so politely.

        User Question: {question}
        Rewritten Query: {rewritten_query}
        Policy Context: {policy_context}
        Conversation Context: {history_text}

        Retrieved Docs:
        {doc_text or "[No documents retrieved]"}
        """
        raw_answer = str(call_llm(rag_prompt, LLM_LIGHT_MODEL)).strip()
        verdict = enforce_grounding(raw_answer, doc_text)

        if verdict == "SUPPORTED":
            state["answer"] = raw_answer
            state["rag_answer"] = raw_answer
            print(f"[decision_agent] ✅ RAG answer: {raw_answer[:80]}...")
        else:
            state["handoff"] = True
            state["answer"] = "This question requires support team assistance."
            print("[decision_agent] ⏩ escalation")

    memory: HybridMemory = state.get("memory")
    if memory:
        memory.save_context({"input": question}, {"output": state["answer"]})

    return ensure_dict(state, "decision_agent")


# --- Human Agent ---
def human_agent(state: dict):
    print(f"[human_agent] handoff triggered: {state.get('answer')}")
    return ensure_dict(state, "human_agent")


# --- End Detector ---
def detect_conversation_end(state: dict) -> bool:
    memory = state.get("memory")
    past = memory.load_memory_variables({}) if memory else {"history": ""}
    history_text = past.get("history", "").strip()

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
    - Reply NO otherwise.
    """
    verdict = call_llm(prompt, LLM_LIGHT_MODEL)
    return str(verdict).strip().upper() == "YES"


# --- Responder ---
def responder(state: dict):
    answer = state.get("rag_answer") or state.get("answer")
    state["answer"] = answer or "No response available."

    memory = state.get("memory")
    if memory:
        past = memory.load_memory_variables({})
        history_text = past.get("history", "").strip()
        if history_text:
            print("[conversation history]\n" + history_text)

        if detect_conversation_end(state):
            state["end_conversation"] = True

    print(f"[responder] final answer: {state['answer'][:80]}...")
    return ensure_dict(state, "responder")


# --- Summarizer ---
def summarize_conversation(state: dict):
    memory = state.get("memory")
    if not memory:
        print("[summarizer] ❌ No memory object, skipping summarization")
        return state

    past = memory.load_memory_variables({})
    history_text = past.get("history", "").strip()

    if not history_text:
        print("[summarizer] ⚠️ No conversation history available, skipping summarization")
        state["conversation_summary"] = "No conversation history available. Nothing to summarize."
        return state

    print(f"[summarizer] Conversation history:\n{history_text}")

    prompt = f"""
    You are an insurance assistant. Summarize the conversation faithfully.

    Conversation:
    {history_text}

    Task:
    1. Provide a summary in plain text.
    2. Then add:

    ### Critical Information
    - List only facts explicitly discussed.

    ### Resolution
    - State if questions were answered, partially answered, not answered, or escalated.

    ### Action Items
    - Note next steps (e.g., "Await support team follow-up" or "No action required").
    """
    resp = call_llm(prompt, LLM_LIGHT_MODEL)
    structured_summary = str(resp).strip()

    subject = f"Insurance Conversation Summary – Policy {state.get('policy_number')}"
    body = (
        f"Hello {state.get('policyholder_name') or 'Policyholder'},\n\n"
        f"Here’s a summary of your recent conversation:\n\n"
        f"{structured_summary}\n\n"
        f"---\n"
        f"### Full Conversation Log\n\n"
        f"{history_text}\n\n"
        "Best regards,\nYour Insurance Team"
    )

    send_email(subject, body)
    print("[summarizer] ✅ Summary + conversation log email sent")

    state["conversation_summary"] = structured_summary
    return state


# --- Graph Assembly ---
graph = StateGraph(dict)

graph.add_node("rag_agent", rag_agent)
graph.add_node("decision_agent", decision_agent)
graph.add_node("human_agent", human_agent)
graph.add_node("responder", responder)
graph.add_node("summarizer", summarize_conversation)

graph.set_entry_point("rag_agent")

# rag_agent → decision_agent
graph.add_edge("rag_agent", "decision_agent")

# decision_agent → responder
graph.add_edge("decision_agent", "responder")

# human_agent → responder
graph.add_edge("human_agent", "responder")

# summarizer condition
graph.add_conditional_edges(
    "responder",
    lambda s: "summarizer" if s.get("end_conversation") else "end",
    {"summarizer": "summarizer", "end": END},
)

graph.add_edge("summarizer", END)

conversation_chain = graph.compile()
