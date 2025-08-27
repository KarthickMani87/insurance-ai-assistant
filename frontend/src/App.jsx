import React, { useState } from "react";
import UploadBox from "./components/UploadBox";
import ExtractedInfoCard from "./components/ExtractedInfoCard";
import EditableFields from "./components/EditableFields";
import ChatAssistant from "./components/ChatAssistant";
import "./index.css";

function App() {
  const [policyInfo, setPolicyInfo] = useState(null);
  const [finalInfo, setFinalInfo] = useState(null);

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6 text-center">🛡️ Insurance Assistant</h1>
      <UploadBox onProcessed={setPolicyInfo} />
      <ExtractedInfoCard info={policyInfo} />
      {policyInfo && <EditableFields info={policyInfo} onConfirm={setFinalInfo} />}
      {finalInfo && <ChatAssistant policyNumber={finalInfo.policy_number} />}
    </div>
  );
}

export default App;

