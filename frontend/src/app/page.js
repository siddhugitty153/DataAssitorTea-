"use client";

import { useState, useRef, useEffect } from "react";

// ── Simple Markdown Renderer ────────────────────────────────────
// Handles: headers, bold, inline code, code blocks, lists, links
function renderMarkdown(text) {
  if (!text) return null;
  
  const lines = text.split("\n");
  const elements = [];
  let inCodeBlock = false;
  let codeBuffer = [];
  let codeLang = "";

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Code block fence
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        elements.push(
          <div key={`code-${i}`} className="code-container">
            <div className="code-header">
              <span>{codeLang || "output"}</span>
            </div>
            <pre className="code-box"><code>{codeBuffer.join("\n")}</code></pre>
          </div>
        );
        codeBuffer = [];
        codeLang = "";
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
        codeLang = line.trim().replace("```", "").trim();
      }
      continue;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      continue;
    }

    // Headers
    if (line.startsWith("### ")) {
      elements.push(<h3 key={i}>{formatInline(line.slice(4))}</h3>);
    } else if (line.startsWith("## ")) {
      elements.push(<h2 key={i}>{formatInline(line.slice(3))}</h2>);
    } else if (line.startsWith("# ")) {
      elements.push(<h1 key={i}>{formatInline(line.slice(2))}</h1>);
    }
    // Unordered list items
    else if (/^\s*[-*]\s+/.test(line)) {
      const content = line.replace(/^\s*[-*]\s+/, "");
      elements.push(
        <ul key={i}><li>{formatInline(content)}</li></ul>
      );
    }
    // Ordered list items
    else if (/^\s*\d+\.\s+/.test(line)) {
      const content = line.replace(/^\s*\d+\.\s+/, "");
      elements.push(
        <ol key={i}><li>{formatInline(content)}</li></ol>
      );
    }
    // Empty line
    else if (!line.trim()) {
      elements.push(<div key={i} style={{ height: "0.4rem" }} />);
    }
    // Regular paragraph
    else {
      elements.push(<p key={i}>{formatInline(line)}</p>);
    }
  }

  return <div className="formatted-result">{elements}</div>;
}

// Format inline markdown: **bold**, *italic*, `code`, [links](url)
function formatInline(text) {
  if (!text) return text;
  
  const parts = [];
  let remaining = text;
  let key = 0;

  while (remaining.length > 0) {
    // Bold: **text**
    let match = remaining.match(/^(.*?)\*\*(.+?)\*\*(.*)/s);
    if (match) {
      if (match[1]) parts.push(match[1]);
      parts.push(<strong key={`b-${key++}`}>{match[2]}</strong>);
      remaining = match[3];
      continue;
    }
    
    // Inline code: `text`
    match = remaining.match(/^(.*?)`(.+?)`(.*)/s);
    if (match) {
      if (match[1]) parts.push(match[1]);
      parts.push(
        <code key={`c-${key++}`} style={{
          background: "rgba(99, 102, 241, 0.15)",
          padding: "0.1rem 0.35rem",
          borderRadius: "4px",
          fontSize: "0.85em",
          fontFamily: "'JetBrains Mono', monospace",
        }}>{match[2]}</code>
      );
      remaining = match[3];
      continue;
    }

    // No more patterns — push the rest
    parts.push(remaining);
    break;
  }

  return parts.length === 1 ? parts[0] : parts;
}

// ── API Configuration ──────────────────────────────────────────
const API_BASE = "http://localhost:8000";


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
  const eventSourceRef = useRef(null);

  // Auto-scroll chat to bottom
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isProcessing]);

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

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
      const res = await fetch(`${API_BASE}/api/upload`, {
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

  // ── Handle Query Execution with Real SSE Streaming ──
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
        thoughts: [{ step: "Step 1", type: "supervisor", content: "Initializing Multi-Agent system..." }],
        generatedCode: null,
        error: null,
        status: "running",
      },
    ]);

    setExpandedThoughts((prev) => ({ ...prev, [agentMsgId]: true }));

    try {
      // 1. Dispatch background analysis
      const res = await fetch(`${API_BASE}/api/analyze`, {
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

      // 2. Connect to SSE stream for real-time thought updates (B3 fix)
      const eventSource = new EventSource(`${API_BASE}/api/threads/${threadId}/stream`);
      eventSourceRef.current = eventSource;

      // Track accumulated thoughts from SSE
      let accumulatedThoughts = [];

      eventSource.addEventListener("thought", (event) => {
        const thought = JSON.parse(event.data);
        accumulatedThoughts = [...accumulatedThoughts, thought];

        setMessages((prev) =>
          prev.map((msg) => {
            if (msg.id !== agentMsgId) return msg;
            return {
              ...msg,
              thoughts: accumulatedThoughts,
              status: "running",
            };
          })
        );
      });

      eventSource.addEventListener("done", (event) => {
        const finalData = JSON.parse(event.data);
        eventSource.close();
        eventSourceRef.current = null;

        setMessages((prev) =>
          prev.map((msg) => {
            if (msg.id !== agentMsgId) return msg;
            return {
              ...msg,
              content: finalData.result || "Analysis complete.",
              generatedCode: finalData.generated_code || null,
              error: finalData.error || null,
              status: finalData.status,
              tokenUsage: finalData.token_usage || null,
              thoughts: accumulatedThoughts,
            };
          })
        );
        setIsProcessing(false);
      });

      // Fallback: handle generic messages (for SSE servers that don't use event types)
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "done") {
            eventSource.close();
            eventSourceRef.current = null;

            setMessages((prev) =>
              prev.map((msg) => {
                if (msg.id !== agentMsgId) return msg;
                return {
                  ...msg,
                  content: data.result || "Analysis complete.",
                  generatedCode: data.generated_code || null,
                  error: data.error || null,
                  status: data.status,
                  tokenUsage: data.token_usage || null,
                };
              })
            );
            setIsProcessing(false);
            return;
          }

          // It's a thought step
          if (data.step || data.type) {
            accumulatedThoughts = [...accumulatedThoughts, data];
            setMessages((prev) =>
              prev.map((msg) => {
                if (msg.id !== agentMsgId) return msg;
                return {
                  ...msg,
                  thoughts: accumulatedThoughts,
                };
              })
            );
          }
        } catch (e) {
          // Ignore parse errors (e.g. keepalive comments)
        }
      };

      eventSource.onerror = (err) => {
        console.warn("SSE connection error:", err);
        eventSource.close();
        eventSourceRef.current = null;

        // Fallback: poll once for final result
        setTimeout(async () => {
          try {
            const statusRes = await fetch(`${API_BASE}/api/threads/${threadId}`);
            if (statusRes.ok) {
              const threadData = await statusRes.json();
              setMessages((prev) =>
                prev.map((msg) => {
                  if (msg.id !== agentMsgId) return msg;
                  return {
                    ...msg,
                    content: threadData.result || msg.content || "Analysis completed (SSE disconnected).",
                    generatedCode: threadData.generated_code || msg.generatedCode,
                    error: threadData.error || msg.error,
                    status: threadData.status || "completed",
                    tokenUsage: threadData.token_usage || msg.tokenUsage,
                    thoughts: threadData.thoughts || msg.thoughts,
                  };
                })
              );
            }
          } catch (e) {
            console.warn("Fallback poll failed:", e);
          }
          setIsProcessing(false);
        }, 1000);
      };

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
    // Close any active SSE connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

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
    setIsProcessing(false);
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
                {isProcessing ? "Multi-Agent System Active" : "System Ready"}
              </div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                Gemini 2.5 Flash + Local Sandbox • SSE Streaming
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
            <p>Multi-Agent Orchestration • Code Sandbox • QA Verification • SSE Streaming</p>
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
                        {msg.status === "running" && (
                          <div className="spinner" style={{ width: 12, height: 12, borderWidth: "1.5px" }} />
                        )}
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

                {/* Main Content — uses proper markdown rendering (B9 fix) */}
                {msg.content ? (
                  renderMarkdown(msg.content)
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
                    color: "var(--text-muted)",
                    flexWrap: "wrap",
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
