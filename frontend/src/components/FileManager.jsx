import React, {
  useEffect,
  useState,
  forwardRef,
  useImperativeHandle,
} from "react";

const FileManager = forwardRef((_, ref) => {
  const [files, setFiles] = useState([]);
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(false);

  /**
   * Fetch file list from backend
   */
  const fetchFiles = async () => {
    setLoading(true);
    try {
      const res = await fetch("http://localhost:5000/files/list_files");
      if (!res.ok) throw new Error("Failed to fetch files");

      const data = await res.json();
      setFiles(data.files || []);
    } catch (err) {
      console.error("Error fetching files:", err);
    } finally {
      setLoading(false);
    }
  };

  // Expose fetchFiles() to parent (App.jsx) via ref
  useImperativeHandle(ref, () => ({ fetchFiles }));

  useEffect(() => {
    fetchFiles();
  }, []);

  /**
   * Handle selecting/unselecting files
   */
  const toggleSelect = (key) => {
    setSelected((prev) =>
      prev.includes(key) ? prev.filter((f) => f !== key) : [...prev, key]
    );
  };

  const selectAll = () => {
    setSelected(selected.length === files.length ? [] : files);
  };

  /**
   * Delete selected files
   */
  const deleteFiles = async () => {
    if (selected.length === 0) return;
    if (!window.confirm(`Delete ${selected.length} file(s)?`)) return;

    try {
      await Promise.all(
        selected.map((key) =>
          fetch("http://localhost:5000/files/delete_file", {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ key }),
          })
        )
      );
      setSelected([]);
      fetchFiles(); // refresh list
    } catch (err) {
      console.error("Error deleting files:", err);
    }
  };

  return (
    <div className="max-w-2xl mx-auto mt-6 p-6 border rounded shadow">
      <h2 className="text-xl font-bold mb-4">📂 File Manager</h2>

      {/* Controls */}
      <div className="flex justify-between items-center mb-3">
        <button
          onClick={selectAll}
          className="px-3 py-1 bg-gray-200 rounded hover:bg-gray-300"
        >
          {selected.length === files.length ? "Unselect All" : "Select All"}
        </button>

        <button
          onClick={deleteFiles}
          disabled={selected.length === 0}
          className={`px-3 py-1 rounded text-white ${
            selected.length === 0
              ? "bg-gray-400 cursor-not-allowed"
              : "bg-red-600 hover:bg-red-700"
          }`}
        >
          🗑 Delete Selected
        </button>
      </div>

      {/* File list */}
      {loading ? (
        <p className="text-gray-500">⏳ Loading files...</p>
      ) : files.length === 0 ? (
        <p className="text-gray-500">No files found.</p>
      ) : (
        <ul className="divide-y divide-gray-200">
          {files.map((file) => (
            <li
              key={file}
              className="flex justify-between items-center py-2 px-2 hover:bg-gray-50 rounded"
            >
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected.includes(file)}
                  onChange={() => toggleSelect(file)}
                />
                <span className="text-gray-700 truncate">{file}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
});

export default FileManager;
