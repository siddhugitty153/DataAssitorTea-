"use client";

import { useState, useRef, useEffect } from "react";

export default function Dashboard() {
  const [messages, setMessages] = useState([
    { role: "agent", content: "Welcome! Upload a dataset to begin." },
  ]);
  const [input, setInput] = useState("");
  const [datasetId, setDatasetId] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  
  // We use a random UUID per session
  const threadId = useRef(Math.random().toString(36).substring(7));
  const ws = useRef(null);

  useEffect(() => {
    // Connect to WebSocket for real-time agent thoughts
    ws.current = new WebSocket(`ws://localhost:8000/ws/${threadId.current}`);
    
    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "thought") {
        // We could append thoughts to a side-panel, but for now we'll just log them or show a loading state
        console.log("Agent Thought:", data.content);
      }
    };

    return () => {
      if (ws.current) ws.current.close();
    };
  }, []);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("http://localhost:8000/api/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setDatasetId(data.dataset_id);
      setMessages((prev) => [
        ...prev,
        { role: "agent", content: `Successfully loaded dataset! The Profiler found ${data.columns.length} columns.` }
      ]);
    } catch (err) {
      alert("Failed to upload dataset.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || !datasetId) {
      if (!datasetId) alert("Please upload a dataset first!");
      return;
    }
    
    const query = input;
    setMessages((prev) => [...prev, { role: "user", content: query }]);
    setInput("");
    setIsProcessing(true);

    try {
      const res = await fetch("http://localhost:8000/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_id: datasetId,
          query: query,
          thread_id: threadId.current
        }),
      });
      const data = await res.json();
      
      setMessages((prev) => [
        ...prev, 
        { role: "agent", content: data.execution_result || data.execution_error || "Task complete." }
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev, 
        { role: "agent", content: "Error communicating with the backend." }
      ]);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="app-container">
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="logo">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
            <line x1="12" y1="22.08" x2="12" y2="12"></line>
          </svg>
          Data Assister
        </div>

        <div className="upload-zone" onClick={() => document.getElementById('fileUpload').click()}>
          <input 
            type="file" 
            id="fileUpload" 
            accept=".csv" 
            style={{ display: "none" }} 
            onChange={handleFileUpload} 
          />
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{marginBottom: "0.5rem", color: "var(--text-secondary)"}}>
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="17 8 12 3 7 8"></polyline>
            <line x1="12" y1="3" x2="12" y2="15"></line>
          </svg>
          <h3>{isUploading ? "Uploading..." : "Upload Dataset"}</h3>
          <p>Click to select a CSV file</p>
        </div>

        <div>
          <h4 className="section-title">Current Dataset</h4>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            {datasetId ? `✅ Loaded: ${datasetId}` : "No dataset loaded."}
          </p>
        </div>

        <div style={{ marginTop: "auto" }}>
          <h4 className="section-title">System Status</h4>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.875rem" }}>
            <span style={{ 
              width: "8px", 
              height: "8px", 
              borderRadius: "50%", 
              backgroundColor: isProcessing ? "orange" : "var(--success-color)" 
            }}></span>
            {isProcessing ? "Agents are thinking..." : "Agents Ready"}
          </div>
        </div>
      </aside>

      {/* MAIN WORKSPACE */}
      <main className="workspace">
        <header className="header">
          <h1>Analysis Workspace</h1>
          <button style={{ fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: "500" }}>
            Clear Chat
          </button>
        </header>

        <div className="chat-container">
          {messages.map((msg, idx) => (
            <div key={idx} className={`message ${msg.role}`}>
              <div className="message-avatar">
                {msg.role === "user" ? "U" : "AI"}
              </div>
              <div className="message-content">
                {msg.content}
              </div>
            </div>
          ))}
          {isProcessing && (
             <div className="message agent">
             <div className="message-avatar">AI</div>
             <div className="message-content" style={{ color: "var(--text-secondary)", fontStyle: "italic" }}>
               Analyzing data across the Multi-Agent engine... (Check console for raw thoughts)
             </div>
           </div>
          )}
        </div>

        <form className="input-area" onSubmit={handleSend}>
          <div className="input-box">
            <input 
              type="text" 
              placeholder={datasetId ? "Ask a question about your data..." : "Upload a CSV first..."} 
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={!datasetId || isProcessing}
            />
            <button type="submit" disabled={!datasetId || isProcessing}>Ask</button>
          </div>
        </form>
      </main>
    </div>
  );
}
