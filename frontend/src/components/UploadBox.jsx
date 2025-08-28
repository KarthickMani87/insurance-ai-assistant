import React, { useState } from "react";

function UploadBox({ onProcessed }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleFileSelect = (f) => {
    if (f && f.length > 0) {
      setFile(f[0]);
      setStatus(null);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    handleFileSelect(e.dataTransfer.files);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setStatus(null);

    try {
      const res = await fetch("http://localhost:5000/files/generate_presigned_url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          content_type: file.type,
        }),
      });

      const { url, key } = await res.json();

      const upload = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": file.type },
        body: file,
      });

      if (upload.ok) {
        setStatus("success");
        onProcessed({ filename: file.name, key });
      } else {
        setStatus("error");
      }
    } catch (err) {
      console.error("Upload error:", err);
      setStatus("error");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex justify-center mt-6">
      <div
        className={`w-full max-w-md p-6 border-2 rounded-lg text-center transition shadow-sm cursor-pointer
          ${isDragging ? "border-blue-500 bg-blue-50" : "border-dashed border-gray-300 bg-gray-50 hover:bg-gray-100"}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          type="file"
          id="fileInput"
          onChange={(e) => handleFileSelect(e.target.files)}
          className="hidden"
        />
        <label htmlFor="fileInput" className="block text-gray-600 cursor-pointer">
          {file ? (
            <p>
              📄 <b>{file.name}</b> ({(file.size / 1024).toFixed(1)} KB)
            </p>
          ) : (
            <p>
              Drag & drop your policy document here, or{" "}
              <span className="text-blue-600 underline">browse</span>
            </p>
          )}
        </label>

        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className={`mt-4 px-5 py-2 rounded font-semibold text-white transition ${
            uploading
              ? "bg-gray-400 cursor-not-allowed"
              : "bg-blue-600 hover:bg-blue-700"
          }`}
        >
          {uploading ? "⏳ Uploading..." : "⬆️ Upload to S3"}
        </button>

        {status === "success" && (
          <p className="mt-3 text-green-600 font-medium">✅ Upload successful</p>
        )}
        {status === "error" && (
          <p className="mt-3 text-red-600 font-medium">❌ Upload failed. Try again.</p>
        )}
      </div>
    </div>
  );
}

export default UploadBox;   // ✅ put this after the function, outside
