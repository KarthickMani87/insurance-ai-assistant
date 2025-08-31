import React from "react";

const ProgressBar = ({ chunksDone, totalChunks }) => {
  if (!totalChunks || totalChunks === 0) return null;

  const percentage = Math.min(100, Math.round((chunksDone / totalChunks) * 100));

  return (
    <div className="w-full bg-gray-200 rounded-full h-4 mt-4">
      <div
        className="bg-blue-500 h-4 rounded-full transition-all duration-500 ease-in-out"
        style={{ width: `${percentage}%` }}
      />
      <p className="text-sm text-gray-600 mt-1 text-center">
        {chunksDone}/{totalChunks} chunks ({percentage}%)
      </p>
    </div>
  );
};

export default ProgressBar;

