import React, { useState } from "react";
import axios from "axios";

function ChatAssistant({ policyNumber }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");

  const sendMessage = async () => {
    const res = await axios.post("/query", {
      policy_number: policyNumber,
      query: input,
    });

    setMessages([...messages, { role: "user", text: input }, { role: "assistant", text: res.data.answer }]);
    setInput("");
  };

  return (
    <div className="mt-6 p-4 border rounded-lg bg-white">
      <h3 className="font-semibold mb-2">💬 Ask Insurance Assistant</h3>
      <div className="h-40 overflow-y-auto border p-2 mb-2 bg-gray-50">
        {messages.map((m, i) => (
          <p key={i} className={m.role === "user" ? "text-blue-700" : "text-green-700"}>
            <b>{m.role}:</b> {m.text}
          </p>
        ))}
      </div>
      <input
        className="border p-2 w-3/4 rounded mr-2"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Ask about coverage, hospitals, surgeries..."
      />
      <button
        onClick={sendMessage}
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
      >
        Send
      </button>
    </div>
  );
}

export default ChatAssistant;

