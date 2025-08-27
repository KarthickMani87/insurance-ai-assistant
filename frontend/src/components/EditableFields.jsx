import React, { useState } from "react";

function EditableFields({ info, onConfirm }) {
  const [edited, setEdited] = useState(info);

  const handleChange = (e) => {
    setEdited({ ...edited, [e.target.name]: e.target.value });
  };

  return (
    <div className="mt-4 p-4 border rounded-lg bg-gray-100">
      <h3 className="font-semibold mb-2">✏️ Review & Correct</h3>
      {Object.keys(edited).map((key) => (
        <div key={key} className="mb-2">
          <label className="block text-sm">{key}</label>
          <input
            className="border p-1 w-full rounded"
            name={key}
            value={edited[key]}
            onChange={handleChange}
          />
        </div>
      ))}
      <button
        onClick={() => onConfirm(edited)}
        className="mt-2 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
      >
        Confirm
      </button>
    </div>
  );
}

export default EditableFields;

