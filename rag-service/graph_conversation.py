from langgraph.graph import StateGraph, END
from services.llm_service import llm
from services.policy_api import check_policy_status

class ConversationState(dict):
    pass

def coverage_checker(state: ConversationState):
    q = state["question"]
    doc = state["document_text"]
    prompt = f"""
    Based on this policy document, answer the user question:
    {q}

    Document:
    {doc}
    Respond concisely.
    """
    state["coverage"] = llm.invoke(prompt).strip()
    return state

def policy_status_checker(state: ConversationState):
    start = state.get("start_date")
    end = state.get("end_date")
    if start and end:
        active = check_policy_status(start, end)
        state["status"] = "✅ Active" if active else "❌ Not Active"
    else:
        state["status"] = "⚠️ Unknown (dates missing)"
    return state

def responder(state: ConversationState):
    return {
        "answer": state.get("coverage") or state.get("status", "No response")
    }

graph = StateGraph(ConversationState)
graph.add_node("coverage_checker", coverage_checker)
graph.add_node("policy_status_checker", policy_status_checker)
graph.add_node("responder", responder)

graph.set_entry_point("coverage_checker")
graph.add_edge("coverage_checker", "policy_status_checker")
graph.add_edge("policy_status_checker", "responder")
graph.add_edge("responder", END)

conversation_chain = graph.compile()

