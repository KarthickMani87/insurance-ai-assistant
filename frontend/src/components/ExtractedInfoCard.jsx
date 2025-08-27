function ExtractedInfoCard({ info }) {
  if (!info) return null;

  return (
    <div className="p-4 border rounded-lg shadow-md bg-white mt-4">
      <h3 className="font-bold text-lg mb-2">📑 Policy Details</h3>
      <p><b>Policyholder:</b> {info.name}</p>
      <p><b>Policy Number:</b> {info.policy_number}</p>
      <p><b>Policy Type:</b> {info.type}</p>
      <p><b>Coverage:</b> {info.coverage}</p>
    </div>
  );
}

export default ExtractedInfoCard;

