import React, { useState, useEffect } from "react";

function EditableFields({ info, onConfirm }) {
  const [edited, setEdited] = useState(info || {});

  // Update state when new info comes in (after upload)
  useEffect(() => {
    if (info) {
      setEdited(info);
    }
  }, [info]);

  if (!info) return null; // don’t render until info is ready

  const handleChange = (e) => {
    setEdited({ ...edited, [e.target.name]: e.target.value });
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault(); // prevent accidental form submit reload
      onConfirm(edited);
    }
  };

  return (
    <div className="border p-4 mt-4 rounded shadow-sm bg-white">
      <h2 className="font-bold mb-2">Confirm Policy Details</h2>

      <div className="flex flex-col gap-2">
        <input
          name="name"
          value={edited.name || ""}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Policy Holder Name"
          className="border p-2 rounded"
        />
        <input
          name="policy_number"
          value={edited.policy_number || ""}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Policy Number"
          className="border p-2 rounded"
        />
        <input
          name="start_date"
          value={edited.start_date || ""}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Start Date"
          className="border p-2 rounded"
        />
        <input
          name="end_date"
          value={edited.end_date || ""}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="End Date"
          className="border p-2 rounded"
        />
      </div>

      <button
        onClick={() => onConfirm(edited)}
        className="bg-green-500 text-white px-4 py-2 rounded mt-4 hover:bg-green-600 transition"
      >
        Confirm
      </button>
    </div>
  );
}

export default EditableFields;
