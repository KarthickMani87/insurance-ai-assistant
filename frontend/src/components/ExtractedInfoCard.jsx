function ExtractedInfoCard({ info }) {
  if (!info) return null;

  // Helper to convert snake_case to Title Case
  const formatLabel = (key) => {
    return key
      .replace(/_/g, " ")       // replace underscores with spaces
      .replace(/\b\w/g, (c) => c.toUpperCase()); // capitalize each word
  };

  return (
    <div className="p-4 border rounded-lg shadow-md bg-white mt-4">
      <h3 className="font-bold text-lg mb-2">📑 Policy Details</h3>
      {Object.entries(info).map(([key, value]) => {
        if (
          value === null ||
          value === "" ||
          (Array.isArray(value) && value.length === 0)
        ) {
          return null; // skip empty fields
        }

        return (
          <p key={key}>
            <b>{formatLabel(key)}:</b>{" "}
            {Array.isArray(value) ? value.join(", ") : value}
          </p>
        );
      })}
    </div>
  );
}

export default ExtractedInfoCard;