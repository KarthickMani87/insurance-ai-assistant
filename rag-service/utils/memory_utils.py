from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferWindowMemory, ConversationSummaryMemory
from config import LLM_LIGHT_MODEL, OPENAI_API_KEY
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

class HybridMemory:
    def __init__(self, buffer_k: int = 5):
        print(f"[HybridMemory]********************** Using model: {LLM_LIGHT_MODEL}")
        llm = ChatOpenAI(
            model=LLM_LIGHT_MODEL,
            api_key=OPENAI_API_KEY,
            request_timeout=300
        )
        self.buffer_memory = ConversationBufferWindowMemory(k=buffer_k, return_messages=True)
        self.summary_memory = ConversationSummaryMemory(llm=llm, return_messages=True)

    def save_context(self, inputs, outputs):
        self.buffer_memory.save_context(inputs, outputs)
        self.summary_memory.save_context(inputs, outputs)

    def load_memory_variables(self, inputs=None):
        buffer_vars = self.buffer_memory.load_memory_variables(inputs or {})
        summary_vars = self.summary_memory.load_memory_variables(inputs or {})

        history = ""

        def format_messages(messages, title):
            if not messages:
                return ""
            text = f"### {title}\n"
            for m in messages:
                role = m.__class__.__name__.replace("Message", "").upper()
                content = m.content.strip()
                if content:
                    text += f"{role}: {content}\n"
            return text + "\n"

        history += format_messages(summary_vars.get("history") or summary_vars.get("chat_history"), "Summary of Past Conversation")
        history += format_messages(buffer_vars.get("history") or buffer_vars.get("chat_history"), "Recent Conversation")

        return {"history": history.strip()}

    # 🔑 For Redis persistence
    def serialize(self):
        """Return JSON-safe memory (roles + content)."""
        return {
            "buffer": [
                {"role": m.__class__.__name__.replace("Message", "").lower(), "content": m.content}
                for m in self.buffer_memory.chat_memory.messages
            ],
            "summary": [
                {"role": m.__class__.__name__.replace("Message", "").lower(), "content": m.content}
                for m in getattr(self.summary_memory, "chat_memory", []).messages
            ]
            if hasattr(self.summary_memory, "chat_memory")
            else []
        }

    @classmethod
    def deserialize(cls, data: dict, buffer_k: int = 5):
        """Rebuild HybridMemory from JSON-safe memory."""
        memory = cls(buffer_k=buffer_k)
        for msg in data.get("buffer", []):
            if msg["role"] == "human":
                memory.buffer_memory.chat_memory.add_message(HumanMessage(content=msg["content"]))
            elif msg["role"] == "ai":
                memory.buffer_memory.chat_memory.add_message(AIMessage(content=msg["content"]))
        return memory

