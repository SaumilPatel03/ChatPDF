import React, { useState, useCallback } from 'react';
import axios from 'axios';
import './PDFUpload.css';

const PDFUpload = ({ onUploadSuccess }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState(null);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(async (e) => {
    e.preventDefault();
    setIsDragging(false);
    setError(null);

    const file = e.dataTransfer.files[0];
    if (file && file.type === 'application/pdf') {
      await uploadFile(file);
    } else {
      setError('Please upload a PDF file');
    }
  }, []);

  const handleFileSelect = useCallback(async (e) => {
    const file = e.target.files[0];
    if (file) {
      if (file.type === 'application/pdf') {
        await uploadFile(file);
      } else {
        setError('Please upload a PDF file');
      }
    }
  }, []);

  const uploadFile = async (file) => {
    setIsUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      console.log('Uploading file:', file.name);
      const response = await axios.post('http://localhost:8000/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      console.log('Upload response:', response.data);
      onUploadSuccess();
    } catch (err) {
      console.error('Upload error:', err);
      setError(
        err.response?.data?.detail || 
        err.message || 
        'Error uploading file. Please make sure the backend server is running.'
      );
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="pdf-upload-container">
      <div
        className={`upload-area ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept=".pdf"
          onChange={handleFileSelect}
          className="file-input"
          id="file-input"
        />
        <label htmlFor="file-input" className="upload-label">
          {isUploading ? (
            <div className="uploading">
              <div className="spinner"></div>
              <p>Uploading...</p>
            </div>
          ) : (
            <>
              <i className="upload-icon">📄</i>
              <p>Drag and drop your PDF here</p>
              <p>or</p>
              <button 
                type="button" 
                className="browse-button"
                onClick={() => document.getElementById('file-input').click()}
              >
                Browse Files
              </button>
            </>
          )}
        </label>
      </div>
      {error && <p className="error-message">{error}</p>}
    </div>
  );
};

export default PDFUpload; 