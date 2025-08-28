import React, { useState } from "react";
import axios from "axios";

function ChatAssistant({ policyNumber }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");

  const sendMessage = async () => {
    if (!input.trim()) return;

    const newMsg = { role: "user", content: input };
    setMessages((prev) => [...prev, newMsg]);
    setInput("");

    try {
      const res = await axios.post("http://localhost:8000/query", {
        question: input,
        policy_number: policyNumber,
        conversation: messages.map((m) => m.content),
      });

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.data.answer || JSON.stringify(res.data) },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "⚠️ Error connecting to server." },
      ]);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const endConversation = async () => {
    await axios.post("http://localhost:8000/summary", {
      policy_number: policyNumber,
      conversation: messages.map((m) => m.content),
    });
    alert("✅ Summary sent to backend team");
  };

  return (
    <div className="mt-6 border p-4 rounded shadow bg-white">
      <h2 className="font-bold mb-3 text-lg">💬 Chat Assistant</h2>

      {/* Chat window */}
      <div className="h-96 overflow-y-auto border rounded p-3 mb-3 bg-gray-50">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`mb-2 flex ${
              m.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`px-3 py-2 rounded-lg max-w-xs ${
                m.role === "user"
                  ? "bg-blue-500 text-white"
                  : "bg-green-100 text-gray-800"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
      </div>

      {/* Input + actions */}
      <div className="flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message and press Enter..."
          className="flex-1 border px-3 py-2 rounded resize-none h-12"
        />
        <button
          onClick={sendMessage}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
        >
          Send
        </button>
        <button
          onClick={endConversation}
          className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded"
        >
          End
        </button>
      </div>
    </div>
  );
}

export default ChatAssistant;
