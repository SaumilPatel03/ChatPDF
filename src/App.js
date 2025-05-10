import React, { useState } from 'react';
import PDFUpload from './components/PDFUpload';
import ChatInterface from './components/ChatInterface';
import './App.css';

function App() {
  const [isPdfUploaded, setIsPdfUploaded] = useState(false);

  const handleUploadSuccess = () => {
    setIsPdfUploaded(true);
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>PDF Chat Assistant</h1>
      </header>
      <main>
        {!isPdfUploaded ? (
          <PDFUpload onUploadSuccess={handleUploadSuccess} />
        ) : (
          <ChatInterface />
        )}
      </main>
    </div>
  );
}

export default App;
