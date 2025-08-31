import React, { useState } from "react";
import UploadBox from "./components/UploadBox";
import ExtractedInfoCard from "./components/ExtractedInfoCard";
import EditableFields from "./components/EditableFields";
import ChatAssistant from "./components/ChatAssistant";
import ProgressBar from "./components/ProgressBar";
import "./index.css";

function App() {
  const [policyInfo, setPolicyInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [finalInfo, setFinalInfo] = useState(null);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState({ chunksDone: 0, totalChunks: 0 });

  const handleProcessed = async ({ filename, key }) => {
    setLoading(true);
    setError(null);
    setPolicyInfo(null);
    setProgress({ chunksDone: 0, totalChunks: 0 });
  
    try {
      let data = null;
  
      while (true) {   // 👈 keep polling until completion
        const res = await fetch("http://localhost:8000/upload", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key }),
        });
  
        if (!res.ok) throw new Error("Backend error");
        data = await res.json();
  
        // ✅ Always update progress (including "complete")
        if (["processing", "pending", "complete"].includes(data.status)) {
          setProgress({
            chunksDone: data.chunks_done || 0,
            totalChunks: data.total_chunks || 0,
          });
        }

        if (data.status === "complete") {
          setPolicyInfo(data);
          break;
        }
  
        if (data.status === "complete" && data.policy_number) {
          setPolicyInfo(data);
          break;
        }
  
        if (data.error) {
          setError(data.error);
          break;
        }
  
        if (data.status === "not_found") {
          setError("❌ Document not found");
          break;
        }
  
        // Still processing → wait and retry
        await new Promise((resolve) => setTimeout(resolve, 2000));
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

      {loading && (
        <div className="mt-4">
          <p className="text-blue-500">⏳ Processing document...</p>
          <ProgressBar
            chunksDone={progress.chunksDone}
            totalChunks={progress.totalChunks}
          />
        </div>
      )}

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
