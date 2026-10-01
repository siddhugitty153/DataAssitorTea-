"use client";

import { useState, useRef, useEffect } from "react";

export default function Dashboard() {
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      role: "agent",
      content: "👋 Welcome to Agentic Data Assistant! Upload a CSV dataset on the left to start autonomous multi-agent analysis with code generation and verification.",
      thoughts: [],
      generatedCode: null,
      error: null,
    },
  ]);
  const [input, setInput] = useState("");
  const [datasetInfo, setDatasetInfo] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [expandedThoughts, setExpandedThoughts] = useState({});

  const fileInputRef = useRef(null);
  const chatBottomRef = useRef(null);

  // Auto-scroll chat to bottom
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isProcessing]);

  const toggleThoughts = (msgId) => {
    setExpandedThoughts((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
  };

  // Upload handler
  const handleUploadFile = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setUploadError("Please upload a valid .csv file.");
      return;
    }

    setIsUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("http://localhost:8000/api/upload", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || data.message || "Failed to upload file");
      }

      setDatasetInfo({
        id: data.dataset_id,
        filename: data.filename,
        columns: data.columns || [],
        rowCount: data.row_count || 0,
      });

      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: "agent",
          content: `✅ **Dataset Loaded Successfully!**\n\n- **File:** \`${data.filename}\`\n- **Rows:** ${data.row_count.toLocaleString()}\n- **Columns (${data.columns.length}):** ${data.columns.slice(0, 10).join(", ")}${data.columns.length > 10 ? "..." : ""}\n\nYou can now ask any question or click a suggested query below.`,
          thoughts: [],
          generatedCode: null,
          error: null,
        },
      ]);
    } catch (err) {
      setUploadError(err.message || "Upload failed. Please ensure the backend is running.");
    } finally {
      setIsUploading(false);
    }
  };

  // Handle Query Execution with Live Streaming & Polling Fallback
  const handleSend = async (queryText) => {
    const query = (queryText || input).trim();
    if (!query || !datasetInfo?.id || isProcessing) return;

    setInput("");
    setIsProcessing(true);

    const userMsgId = Date.now().toString();
    const agentMsgId = (Date.now() + 1).toString();

    // Append user message and blank agent placeholder
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: query },
      {
        id: agentMsgId,
        role: "agent",
        content: "",
        thoughts: [{ step: "Step 1", type: "supervisor", content: "Initializing Multi-Agent swarm..." }],
        generatedCode: null,
        error: null,
        status: "running",
      },
    ]);

    setExpandedThoughts((prev) => ({ ...prev, [agentMsgId]: true }));

    try {
      // 1. Dispatch background analysis
      const res = await fetch("http://localhost:8000/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_id: datasetInfo.id,
          query: query,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || "Failed to start analysis");
      }

      const threadId = data.thread_id;

      // 2. Poll & stream results until completed or failed
      let isDone = false;
      let attempts = 0;

      const pollInterval = setInterval(async () => {
        attempts += 1;
        if (isDone || attempts > 120) {
          clearInterval(pollInterval);
          if (attempts > 120 && !isDone) {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === agentMsgId
                  ? { ...msg, error: "Analysis timed out after 60 seconds.", status: "failed" }
                  : msg
              )
            );
            setIsProcessing(false);
          }
          return;
        }

        try {
          const statusRes = await fetch(`http://localhost:8000/api/threads/${threadId}`);
          if (!statusRes.ok) return;

          const threadData = await statusRes.json();

          // Update thoughts & status live
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.id !== agentMsgId) return msg;
              return {
                ...msg,
                thoughts: threadData.thoughts || msg.thoughts,
                status: threadData.status,
                generatedCode: threadData.generated_code || msg.generatedCode,
                content: threadData.result || msg.content,
                error: threadData.error || msg.error,
                tokenUsage: threadData.token_usage || msg.tokenUsage,
              };
            })
          );

          if (threadData.status === "completed" || threadData.status === "failed") {
            isDone = true;
            clearInterval(pollInterval);
            setIsProcessing(false);
          }
        } catch (pollErr) {
          console.warn("Polling status error:", pollErr);
        }
      }, 600);
    } catch (err) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === agentMsgId
            ? {
                ...msg,
                error: err.message || "Error communicating with backend.",
                status: "failed",
              }
            : msg
        )
      );
      setIsProcessing(false);
    }
  };

  const handleClearChat = () => {
    setMessages([
      {
        id: "welcome",
        role: "agent",
        content: datasetInfo
          ? `Dataset **${datasetInfo.filename}** is still active. Ask any analytical question!`
          : "👋 Welcome! Upload a dataset to begin.",
        thoughts: [],
        generatedCode: null,
        error: null,
      },
    ]);
  };

  const sampleQueries = datasetInfo
    ? [
        "Provide a high-level summary and key statistics of this dataset.",
        "Check for missing values, outliers, and data anomalies.",
        "Show the top 5 rows and distribution across main categories.",
        "What interesting patterns or correlations exist in this data?",
      ]
    : [
        "Upload a dataset to see sample analytical queries.",
      ];

  // Helper to render formatted text
  const renderFormattedText = (text) => {
    if (!text) return null;
    const lines = text.split("\n");
    return (
      <div className="formatted-result">
        {lines.map((line, idx) => {
          if (line.startsWith("### ")) {
            return <h3 key={idx}>{line.replace("### ", "")}</h3>;
          }
          if (line.startsWith("## ")) {
            return <h2 key={idx}>{line.replace("## ", "")}</h2>;
          }
          if (line.startsWith("# ")) {
            return <h1 key={idx}>{line.replace("# ", "")}</h1>;
          }
          if (line.startsWith("* ") || line.startsWith("- ")) {
            return (
              <ul key={idx}>
                <li>{line.substring(2)}</li>
              </ul>
            );
          }
          if (!line.trim()) {
            return <div key={idx} style={{ height: "0.4rem" }} />;
          }
          return <p key={idx}>{line}</p>;
        })}
      </div>
    );
  };

  return (
    <div className="app-container">
      {/* ── SIDEBAR ── */}
      <aside className="sidebar">
        <div className="logo-container">
          <div className="logo-badge">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
              <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
              <line x1="12" y1="22.08" x2="12" y2="12" />
            </svg>
          </div>
          <div className="logo-text">
            <h2>Data Assister</h2>
            <p>Autonomous MAS Engine</p>
          </div>
        </div>

        {/* Upload Zone */}
        <div>
          <input
            type="file"
            ref={fileInputRef}
            accept=".csv"
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files?.[0]) handleUploadFile(e.target.files[0]);
              e.target.value = "";
            }}
          />
          <div
            className={`upload-zone ${isDragOver ? "dragover" : ""}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragOver(false);
              if (e.dataTransfer.files?.[0]) {
                handleUploadFile(e.dataTransfer.files[0]);
              }
            }}
          >
            <div className="upload-icon">
              {isUploading ? (
                <div className="spinner" style={{ borderColor: "rgba(99,102,241,0.3)", borderTopColor: "var(--primary)" }} />
              ) : (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
              )}
            </div>
            <h3>{isUploading ? "Indexing Dataset..." : "Upload CSV Dataset"}</h3>
            <p>{isUploading ? "Extracting metadata & building FAISS index" : "Drag & drop or click to browse"}</p>
          </div>
          {uploadError && <div className="error-box">{uploadError}</div>}
        </div>

        {/* Dataset Profile Card */}
        {datasetInfo && (
          <div className="dataset-card">
            <div className="dataset-header">
              <div className="dataset-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                <span style={{ maxWidth: "160px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {datasetInfo.filename}
                </span>
              </div>
              <span className="dataset-badge">Active</span>
            </div>

            <div className="stats-grid">
              <div className="stat-box">
                <div className="stat-label">Total Rows</div>
                <div className="stat-value">{datasetInfo.rowCount.toLocaleString()}</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Columns</div>
                <div className="stat-value">{datasetInfo.columns.length}</div>
              </div>
            </div>

            <div>
              <div className="section-title" style={{ marginBottom: "0.35rem" }}>Column Attributes</div>
              <div className="columns-preview">
                {datasetInfo.columns.map((col, idx) => (
                  <span key={idx} className="col-tag">{col}</span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Suggested Queries */}
        <div className="suggested-section">
          <div className="section-title">Suggested Inquiries</div>
          {sampleQueries.map((q, idx) => (
            <button
              key={idx}
              className="suggestion-chip"
              disabled={!datasetInfo || isProcessing}
              onClick={() => handleSend(q)}
            >
              <span>⚡</span>
              <span>{q}</span>
            </button>
          ))}
        </div>

        {/* System Status */}
        <div className="system-status-card">
          <div className="status-indicator">
            <div className={`pulse-dot ${isProcessing ? "busy" : ""}`} />
            <div>
              <div style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                {isProcessing ? "Multi-Agent Swarm Active" : "System Ready"}
              </div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                Gemini 2.5 Flash + Local Sandbox
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* ── MAIN WORKSPACE ── */}
      <main className="workspace">
        <header className="header">
          <div className="header-title-box">
            <h1>Autonomous Analysis Workspace</h1>
            <p>ReAct Orchestration • Code Sandbox • QA Verification</p>
          </div>
          <div className="header-actions">
            <button className="btn-secondary" onClick={handleClearChat}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="1 4 1 10 7 10" />
                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
              </svg>
              Clear Chat
            </button>
          </div>
        </header>

        {/* Chat History */}
        <div className="chat-container">
          {messages.map((msg) => (
            <div key={msg.id} className={`message ${msg.role}`}>
              <div className="message-avatar">
                {msg.role === "user" ? "YOU" : "AI"}
              </div>
              <div className="message-content">
                {/* Agent Thought Stream Accordion */}
                {msg.role === "agent" && msg.thoughts && msg.thoughts.length > 0 && (
                  <div className="thought-stream-card">
                    <div className="thought-header" onClick={() => toggleThoughts(msg.id)}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span style={{ color: "var(--primary)" }}>⚙️</span>
                        <span>Agent Reasoning Chain ({msg.thoughts.length} steps)</span>
                      </div>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        {expandedThoughts[msg.id] ? "▲ Collapse" : "▼ Expand"}
                      </span>
                    </div>

                    {expandedThoughts[msg.id] && (
                      <div className="thought-list">
                        {msg.thoughts.map((t, tIdx) => (
                          <div key={tIdx} className={`thought-item ${t.type || ""}`}>
                            {t.content}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Generated Code block */}
                {msg.generatedCode && (
                  <div className="code-container">
                    <div className="code-header">
                      <span>Generated Python Script</span>
                      <button className="copy-btn" onClick={() => copyToClipboard(msg.generatedCode)}>
                        Copy Code
                      </button>
                    </div>
                    <pre className="code-box">
                      <code>{msg.generatedCode}</code>
                    </pre>
                  </div>
                )}

                {/* Main Content */}
                {msg.content ? (
                  renderFormattedText(msg.content)
                ) : msg.status === "running" ? (
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--text-secondary)" }}>
                    <div className="spinner" />
                    <span>Orchestrating agents and executing sandbox verification...</span>
                  </div>
                ) : null}

                {/* Token Usage Badge */}
                {msg.tokenUsage && msg.tokenUsage.total_tokens > 0 && (
                  <div style={{
                    marginTop: "0.75rem",
                    paddingTop: "0.5rem",
                    borderTop: "1px solid var(--border-color)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                    fontSize: "0.72rem",
                    color: "var(--text-muted)"
                  }}>
                    <span style={{ display: "flex", alignItems: "center", gap: "0.3rem", color: "var(--accent-cyan)", fontWeight: 600 }}>
                      ⚡ {msg.tokenUsage.total_tokens.toLocaleString()} tokens
                    </span>
                    <span>•</span>
                    <span>Prompt: {msg.tokenUsage.prompt_tokens?.toLocaleString() || 0}</span>
                    <span>•</span>
                    <span>Completion: {msg.tokenUsage.completion_tokens?.toLocaleString() || 0}</span>
                    <span>•</span>
                    <span style={{ color: "var(--accent-emerald)" }}>Memory Palace: Optimized</span>
                  </div>
                )}

                {/* Error Banner */}
                {msg.error && (
                  <div className="error-box">
                    <strong>Error during execution:</strong> {msg.error}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={chatBottomRef} />
        </div>

        {/* Input Bar */}
        <form
          className="input-area"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <div className="input-box">
            <input
              type="text"
              placeholder={
                !datasetInfo
                  ? "👈 Upload a CSV dataset first to begin analysis..."
                  : isProcessing
                  ? "Agents are currently reasoning and executing code..."
                  : "Ask an analytical question (e.g., 'What is the correlation between price and ratings?')..."
              }
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={!datasetInfo || isProcessing}
            />
            <button
              type="submit"
              className="send-button"
              disabled={!datasetInfo || isProcessing || !input.trim()}
            >
              {isProcessing ? (
                <div className="spinner" />
              ) : (
                <>
                  <span>Analyze</span>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </>
              )}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
