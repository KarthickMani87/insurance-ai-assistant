import React, { useState } from "react";
import UploadBox from "./components/UploadBox";
import ExtractedInfoCard from "./components/ExtractedInfoCard";
import EditableFields from "./components/EditableFields";
import ChatAssistant from "./components/ChatAssistant";
import "./index.css";

function App() {
  const [policyInfo, setPolicyInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [finalInfo, setFinalInfo] = useState(null);
  const [error, setError] = useState(null);

  const handleProcessed = async ({ filename, key }) => {
    setLoading(true);
    setError(null);

    try {
      // call your RAG service after upload
      const res = await fetch("http://localhost:8000/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_text: key }) // or pass actual text if you have it
      });

      if (!res.ok) throw new Error("Backend error");

      const data = await res.json();

      if (data && data.policy_number) {
        setPolicyInfo(data);
      } else {
        setError("❌ Not a valid policy document");
      }
    } catch (err) {
      console.error("Upload processing failed:", err);
      setError("❌ Failed to extract policy details");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6 text-center">🛡️ Insurance Assistant</h1>
      
      <UploadBox onProcessed={handleProcessed} />

      {loading && <p className="mt-4 text-blue-500">⏳ Extracting policy details...</p>}

      {error && <p className="mt-4 text-red-600">{error}</p>}

      {policyInfo && !error && (
        <>
          <ExtractedInfoCard info={policyInfo} />
          <EditableFields info={policyInfo} onConfirm={setFinalInfo} />
        </>
      )}

      {finalInfo && <ChatAssistant policyNumber={finalInfo.policy_number} />}
    </div>
  );
}

export default App;
