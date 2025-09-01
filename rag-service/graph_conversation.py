from langgraph.graph import StateGraph, END
from services.llm_service import call_llm, draft_fraud_alert
from services.policy_api import check_policy_status
from utils.verify_policy import verify_policy
from services.email_service import send_summary_email
from utils.chroma_client import retrieve_query
from utils.cleanupFunc import collect_docs
from config import VECTOR_COLLECTION, LLM_LIGHT_MODEL


# --- Router Agent ---
def router(state: dict):
    q = state.get("question", "")
    policy_type = state.get("policy_type", "")

    prompt = f"""
    You are a coordinator agent.

    Policy type: {policy_type}
    Question: {q}

    Decide which agent should answer:
    - HEALTH_AGENT: if health/medical/hospitalization related
    - VEHICLE_AGENT: if vehicle/auto/accident/repair related
    - HUMAN_AGENT: if unusual or unsupported
    Always run FRAUD_AGENT in parallel in the background.

    Respond with ONLY one of: HEALTH_AGENT, VEHICLE_AGENT, HUMAN_AGENT
    """
    state["route"] = call_llm(prompt, LLM_LIGHT_MODEL).strip().upper()
    return state


# --- Fraud Agent ---
def fraud_agent(state: dict):
    details = {
        "policyholder_name": state.get("policyholder_name"),
        "policy_number": state.get("policy_number"),
        "policy_type": state.get("policy_type"),
        "start_date": state.get("start_date"),
        "end_date": state.get("end_date"),
    }
    is_valid, messages = verify_policy(details)

    if not is_valid:
        fraud_email = draft_fraud_alert(details, messages)
        send_summary_email(fraud_email["subject"], fraud_email["body"])
        state["fraud"] = True
        state["answer"] = "Policy details do not match our records."
    else:
        state["fraud"] = False
    return state

# --- Helper: Hallucination Check ---
def enforce_grounding(answer: str, docs: str) -> str:
    """Use a lightweight LLM to check if the answer is supported by docs."""
    prompt = f"""
    You are a strict judge.

    Answer: {answer}

    Supporting Document:
    {docs}

    Task:
    - If the answer is clearly supported by the document, reply: SUPPORTED
    - If the answer is not found in the document, reply: NOT SUPPORTED
    """

    verdict = call_llm(prompt, LLM_LIGHT_MODEL).strip().upper()
    if "SUPPORTED" in verdict:
        return answer

    # fallback if unsupported
    return "The asked information is not present in the provided policy document."


def health_agent(state: dict):
    q = state["question"]
    history = state.get("history", [])

    history_text = "\n".join([
        f"User: {h['user']}\nAssistant: {h['assistant']}"
        for h in history[-5:]
    ])

    results = retrieve_query(q, VECTOR_COLLECTION)
    docs = collect_docs(results)
    doc_text = "\n".join(docs)

    # Generate raw answer
    prompt = f"""
    You are a Health Insurance Agent.

    Answer the user’s question ONLY using the information in the provided policy document.
    If the answer is not explicitly stated in the document, reply with your best guess.
    (Your answer will be checked for grounding separately.)

    Conversation so far:
    {history_text}

    Current Question: {q}

    Policy Document:
    {doc_text}
    """
    raw_answer = call_llm(prompt).strip()

    # ✅ Post-validation step
    state["health_answer"] = enforce_grounding(raw_answer, doc_text)
    return state



def vehicle_agent(state: dict):
    q = state["question"]
    history = state.get("history", [])

    history_text = "\n".join([
        f"User: {h['user']}\nAssistant: {h['assistant']}"
        for h in history[-5:]
    ])

    results = retrieve_query(q, VECTOR_COLLECTION)
    docs = collect_docs(results)
    doc_text = "\n".join(docs)

    # Generate raw answer
    prompt = f"""
    You are a Vehicle Insurance Agent.

    Answer the user’s question ONLY using the information in the provided policy document.
    If the answer is not explicitly stated in the document, reply with your best guess.
    (Your answer will be checked for grounding separately.)

    Conversation so far:
    {history_text}

    Current Question: {q}

    Policy Document:
    {doc_text}
    """
    raw_answer = call_llm(prompt).strip()

    # ✅ Post-validation step
    state["vehicle_answer"] = enforce_grounding(raw_answer, doc_text)
    return state

# --- Human Agent ---
def human_agent(state: dict):
    q = state["question"]
    state["handoff"] = True
    state["answer"] = f"⚠️ Request '{q}' requires human assistance."
    return state


# --- Responder ---
def responder(state: dict):
    if state.get("fraud"):
        return {"answer": state["answer"]}

    answer = (
        state.get("health_answer")
        or state.get("vehicle_answer")
        or state.get("answer")
    )
    state["answer"] = answer or "No response available."

    # Maintain memory
    history = state.get("history", [])
    if isinstance(history, list):
        history.append({"user": state["question"], "assistant": state["answer"]})
        state["history"] = history

    return state


# --- Graph Assembly ---
graph = StateGraph(dict)

graph.add_node("router", router)
graph.add_node("fraud_agent", fraud_agent)
graph.add_node("health_agent", health_agent)
graph.add_node("vehicle_agent", vehicle_agent)
graph.add_node("human_agent", human_agent)
graph.add_node("responder", responder)

graph.set_entry_point("router")

# Router chooses domain agent
graph.add_conditional_edges(
    "router",
    lambda s: s["route"],
    {
        "HEALTH_AGENT": "health_agent",
        "VEHICLE_AGENT": "vehicle_agent",
        "HUMAN_AGENT": "human_agent",
    },
)

# Fraud always runs
graph.add_edge("router", "fraud_agent")

# End flows at responder
graph.add_edge("health_agent", "responder")
graph.add_edge("vehicle_agent", "responder")
graph.add_edge("human_agent", "responder")
graph.add_edge("fraud_agent", "responder")
graph.add_edge("responder", END)

conversation_chain = graph.compile()
