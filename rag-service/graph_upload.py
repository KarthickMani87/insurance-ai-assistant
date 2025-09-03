from langgraph.graph import StateGraph, END
from services.llm_service import pick_llm

class UploadState(dict):
    pass

def upload_extractor(state: UploadState):
    text = state["document_text"]
    prompt = f"""
    Extract the following from this insurance policy document:
    - Policyholder Name
    - Policy Number
    - Start Date (ISO 8601)
    - End Date (ISO 8601)
    - Policy Type (Car or Health Insurance)

    Document:
    {text}

    Respond in JSON.
    """
    import json
    try:
        llm = pick_llm()
        extracted = json.loads(llm.invoke(prompt))
        state.update(extracted)
    except Exception as e:
        state["error"] = f"Extraction failed: {e}"
    return state

graph = StateGraph(UploadState)
graph.add_node("upload_extractor", upload_extractor)
graph.set_entry_point("upload_extractor")
graph.add_edge("upload_extractor", END)

upload_chain = graph.compile()

