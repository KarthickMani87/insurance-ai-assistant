import React, { useState } from "react";
import axios from "axios";

function UploadBox({ onProcessed }) {
  const [files, setFiles] = useState([]);

  const handleUpload = async () => {
    let formData = new FormData();
    files.forEach(f => formData.append("files", f));

    const res = await axios.post("/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });

    onProcessed(res.data);
  };

  return (
    <div className="border-2 border-dashed p-6 rounded-lg text-center bg-gray-50">
      <input
        type="file"
        multiple
        onChange={(e) => setFiles(Array.from(e.target.files))}
        className="mb-4"
      />
      <button
        onClick={handleUpload}
        className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
      >
        Upload & Process
      </button>
    </div>
  );
}

export default UploadBox;

