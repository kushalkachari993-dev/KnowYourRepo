import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import "./styles.css";

function getSessionId() {
  const existing = localStorage.getItem("kyr_session_id");
  if (existing) return existing;
  const created = `session:${crypto.randomUUID()}`;
  localStorage.setItem("kyr_session_id", created);
  return created;
}

function formatTtl(seconds) {
  if (!seconds) return "temporary";
  const minutes = Math.round(seconds / 60);
  return `${minutes} min`;
}

function shortSessionId(sessionId) {
  return sessionId?.replace("session:", "").slice(0, 8) || "unknown";
}

function clearStoredAuth() {
  localStorage.removeItem("kyr_access_token");
  localStorage.removeItem("kyr_refresh_token");
  localStorage.removeItem("kyr_user");
}

function groundednessLabel(status) {
  if (status === "grounded") return "Grounded";
  if (status === "partially_grounded") return "Partially grounded";
  return "Insufficient evidence";
}

function App() {
  const [sessionId, setSessionId] = useState(getSessionId);
  const [config, setConfig] = useState(null);
  const [status, setStatus] = useState(null);
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem("kyr_user");
    return raw ? JSON.parse(raw) : null;
  });
  const [authMode, setAuthMode] = useState("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [files, setFiles] = useState([]);
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [threshold, setThreshold] = useState(0.3);
  const [documents, setDocuments] = useState([]);
  const [chunks, setChunks] = useState([]);
  const [chatQuestion, setChatQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [activeJob, setActiveJob] = useState(null);

  const signedIn = Boolean(user);

  useEffect(() => {
    bootstrapSession();
  }, []);

  async function bootstrapSession() {
    const token = localStorage.getItem("kyr_access_token");
    if (token) {
      try {
        const current = await api.me();
        const currentUser = current.user || current;
        localStorage.setItem("kyr_user", JSON.stringify(currentUser));
        setUser(currentUser);
      } catch {
        clearStoredAuth();
        setUser(null);
        setMessage("Your saved sign-in expired. Please sign in again.");
      }
    }

    await refreshBasics();
  }

  async function refreshBasics() {
    const [configData, statusData] = await Promise.all([api.config(), api.status(sessionId).catch(() => null)]);
    setConfig(configData);
    setStatus(statusData);
  }

  async function runAction(label, action) {
    setBusy(label);
    setMessage("");
    try {
      await action();
      await refreshBasics();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy("");
    }
  }

  async function waitForJob(jobId) {
    let latest = null;
    for (;;) {
      latest = await api.job(jobId, sessionId);
      setActiveJob(latest);

      if (latest.status === "completed") {
        setMessage(
          `${latest.message}. ${latest.chunks_indexed} chunks indexed. Vectors expire in ${formatTtl(config?.session_ttl_seconds)}.`,
        );
        return latest;
      }
      if (latest.status === "failed") {
        throw new Error(latest.error || latest.message || "Ingestion failed.");
      }

      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  }

  async function handleAuth(event) {
    event.preventDefault();
    await runAction(authMode === "sign-in" ? "Signing in" : "Creating account", async () => {
      const redirectTo = window.location.origin;
      const result =
        authMode === "sign-in" ? await api.signIn(email, password) : await api.signUp(email, password, redirectTo);
      const session = result.session || result;
      if (session?.access_token) {
        localStorage.setItem("kyr_access_token", session.access_token);
        localStorage.setItem("kyr_refresh_token", session.refresh_token || "");
        localStorage.setItem("kyr_user", JSON.stringify(session.user));
        setUser(session.user);
        setMessage("Signed in.");
      } else if (result.confirmation_required) {
        setMessage("Account created. Check your email if Supabase requires confirmation, then sign in.");
      }
    });
  }

  async function handleSignOut() {
    await runAction("Signing out", async () => {
      await api.signOut().catch(() => null);
      clearStoredAuth();
      setUser(null);
      setDocuments([]);
      setChunks([]);
      setAnswer("");
    });
  }

  function handleNewSession() {
    const created = `session:${crypto.randomUUID()}`;
    localStorage.setItem("kyr_session_id", created);
    setSessionId(created);
    setDocuments([]);
    setChunks([]);
    setAnswer("");
    setActiveJob(null);
    api.status(created).then(setStatus).catch(() => null);
    setMessage("Started a fresh anonymous workspace. Re-index your source before searching.");
  }

  async function handleIngestSource(event) {
    event.preventDefault();
    if (!sourceUrl.trim()) {
      setMessage("Paste a public source link first.");
      return;
    }

    await runAction("Indexing source", async () => {
      const result = await api.ingestSource(sourceUrl.trim(), sessionId);
      setMessage("Ingestion job queued. You can keep using the page while it runs.");
      await waitForJob(result.job_id);
    });
  }

  async function handleUpload(event) {
    event.preventDefault();
    if (!files.length) {
      setMessage("Choose at least one file first.");
      return;
    }

    await runAction("Indexing uploads", async () => {
      const result = await api.uploadFiles(files, sessionId);
      setMessage("Upload ingestion job queued. You can keep using the page while it runs.");
      setFiles([]);
      await waitForJob(result.job_id);
    });
  }

  async function handleSearch(event) {
    event.preventDefault();
    if (!query.trim()) {
      setMessage("Enter a search question first.");
      return;
    }

    await runAction("Searching", async () => {
      const result = await api.search({
        query: query.trim(),
        sessionId,
        topK,
        similarityThreshold: threshold,
      });
      setDocuments(result.documents || []);
      setChunks(result.chunks || []);
      setAnswer("");
      setMessage(result.count ? `Found ${result.count} relevant documents.` : "No matching documents found.");
    });
  }

  async function handleChat(event) {
    event.preventDefault();
    if (!chatQuestion.trim()) {
      setMessage("Ask a follow-up question first.");
      return;
    }

    await runAction("Asking model", async () => {
      const result = await api.chat(chatQuestion.trim(), chunks);
      setAnswer(result);
    });
  }

  const metrics = useMemo(
    () => [
      ["Indexed chunks", status?.total_chunks ?? "..."],
      ["Vector DB", config?.vector_backend ?? "..."],
      ["Embeddings", config?.embedding_provider ?? "..."],
      ["Chat", config?.chat_provider ?? "..."],
    ],
    [config, status],
  );

  return (
    <main className="page">
      <header className="nav">
        <div className="brand">
          <div className="brandMark">K</div>
          <div>
            <span>KnowYourRepo</span>
            <small>Retrieval workspace</small>
          </div>
        </div>
        <div className="navPills">
          <span>{signedIn ? user.email || "Signed in" : "Anonymous session"}</span>
          <span>Workspace {shortSessionId(sessionId)}</span>
          <span>{config?.session_ttl_seconds ? `${formatTtl(config.session_ttl_seconds)} vector TTL` : "Temporary vectors"}</span>
        </div>
      </header>

      <section className="workspaceHeader">
        <div className="titleBlock">
          <span className="eyebrow"><span /> Session workspace</span>
          <h1>Repository Intelligence</h1>
          <p>Index a source, search its chunks, and ask grounded follow-up questions.</p>
        </div>
        <section className="metrics">
          {metrics.map(([label, value]) => (
            <div className="metric" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </section>
      </section>

      <section className="topGrid">
        <AccountCard
          signedIn={signedIn}
          user={user}
          authMode={authMode}
          setAuthMode={setAuthMode}
          email={email}
          setEmail={setEmail}
          password={password}
          setPassword={setPassword}
          onAuth={handleAuth}
          onSignOut={handleSignOut}
          config={config}
        />
        {!signedIn && (
          <section className="sessionNotice">
            <div>
              <span className="kicker">Anonymous Workspace</span>
              <p>
                Search scope: <strong>{shortSessionId(sessionId)}</strong>
              </p>
            </div>
            <button type="button" className="secondary" onClick={handleNewSession}>
              New session
            </button>
          </section>
        )}
      </section>

      {message && <div className={message.toLowerCase().includes("error") ? "notice danger" : "notice"}>{message}</div>}
      {busy && <div className="busy">{busy}...</div>}
      {activeJob && <JobCard job={activeJob} />}

      <section className="workspace">
        <div className="sectionHead">
          <div>
            <span className="kicker">Sources</span>
            <h2>Build the temporary index</h2>
            <p>Anonymous GitHub repositories up to {config?.anonymous_repo_limit_mb ?? 100} MB do not require sign-in.</p>
          </div>
        </div>

        <div className="indexGrid">
          <form className="panel" onSubmit={handleIngestSource}>
            <label htmlFor="source-url">Source link</label>
            <p>Public GitHub repository or Google Drive link</p>
            <input
              id="source-url"
              value={sourceUrl}
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder="https://github.com/owner/repo or Drive folder link"
            />
            <button type="submit">Index source link</button>
          </form>

          <form className="panel" onSubmit={handleUpload}>
            <label htmlFor="files">Upload files</label>
            <p>PDF, TXT, DOCX, or Markdown</p>
            <input
              id="files"
              type="file"
              multiple
              accept=".pdf,.txt,.docx,.md"
              onChange={(event) => setFiles(Array.from(event.target.files || []))}
            />
            <button type="submit" className="secondary">Index uploaded files</button>
          </form>
        </div>
      </section>

      <section className="queryGrid">
        <section className="panel searchPanel">
          <span className="kicker">Search</span>
          <h2>Find relevant files</h2>
          <form onSubmit={handleSearch} className="searchForm">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ask about a feature, class, topic, policy, or concept..."
            />
            <div className="controls">
              <label>
                Results
                <input type="range" min="1" max="20" value={topK} onChange={(event) => setTopK(Number(event.target.value))} />
                <span>{topK}</span>
              </label>
              <label>
                Similarity
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={threshold}
                  onChange={(event) => setThreshold(Number(event.target.value))}
                />
                <span>{threshold.toFixed(2)}</span>
              </label>
            </div>
            <button type="submit">Search documents</button>
          </form>
        </section>

        <section className="panel chatPanel">
          <span className="kicker">Chat</span>
          <h2>Ask retrieved context</h2>
          <form onSubmit={handleChat} className="chatForm">
            <input
              value={chatQuestion}
              onChange={(event) => setChatQuestion(event.target.value)}
              placeholder="What should I know from the returned documents?"
            />
            <button type="submit" className="dark">Ask context</button>
          </form>
          {answer && <AnswerPanel answer={answer} />}
        </section>
      </section>

      <div className="resultsHead">
        <div>
          <span className="kicker">Results</span>
          <h2>Retrieved files</h2>
        </div>
        <span>{documents.length} documents</span>
      </div>
      <Results documents={documents} />

      <footer>
        {config &&
          `Embeddings: ${config.embedding_provider} ${config.embedding_model} - Chat: ${config.chat_provider} ${config.chat_model} - Vector DB: ${config.vector_backend}`}
      </footer>
    </main>
  );
}

function AnswerPanel({ answer }) {
  const payload = typeof answer === "string" ? { answer, confidence: "medium", groundedness: { status: "partially_grounded" } } : answer;
  const status = payload?.groundedness?.status || "insufficient_evidence";
  const unsupported = payload?.groundedness?.unsupported_claims || [];
  const citations = payload?.citations || [];

  return (
    <div className="answer">
      <div className="answerTop">
        <span className={`groundedBadge ${status}`}>{groundednessLabel(status)}</span>
        <span>Confidence: {payload?.confidence || "low"}</span>
        {payload?.corrected && <span>Self-corrected</span>}
      </div>
      <p>{payload?.answer || "No answer returned."}</p>

      {citations.length > 0 && (
        <div className="citations">
          <span className="kicker">Evidence</span>
          {citations.map((citation, index) => (
            <div className="citation" key={`${citation.filename}-${citation.chunk_index}-${index}`}>
              <strong>{citation.filename} · chunk {citation.chunk_index}</strong>
              {citation.quote && <p>{citation.quote}</p>}
            </div>
          ))}
        </div>
      )}

      {unsupported.length > 0 && (
        <div className="unsupportedClaims">
          <span className="kicker">Unsupported claims removed</span>
          <ul>
            {unsupported.map((claim, index) => (
              <li key={`${claim}-${index}`}>{claim}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function AccountCard({
  signedIn,
  user,
  authMode,
  setAuthMode,
  email,
  setEmail,
  password,
  setPassword,
  onAuth,
  onSignOut,
  config,
}) {
  if (signedIn) {
    return (
      <aside className="accountCard">
        <span className="kicker">Account</span>
        <div className="accountSignedIn">
          <div>
            <h2>Signed in</h2>
            <p>{user.email || user.id}</p>
          </div>
          <button type="button" className="secondary" onClick={onSignOut}>Sign out</button>
        </div>
      </aside>
    );
  }

  return (
    <aside className="accountCard">
      <span className="kicker">Account</span>
      <h2>Sign in for larger repos</h2>
      <p>Repos over {config?.anonymous_repo_limit_mb ?? 100} MB require sign-in.</p>
      <form onSubmit={onAuth}>
        <div className="tabs" role="tablist">
          <button type="button" className={authMode === "sign-in" ? "active" : ""} onClick={() => setAuthMode("sign-in")}>Sign in</button>
          <button type="button" className={authMode === "sign-up" ? "active" : ""} onClick={() => setAuthMode("sign-up")}>Sign up</button>
        </div>
        <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" type="email" />
        <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" />
        <button type="submit">{authMode === "sign-in" ? "Sign in" : "Create account"}</button>
      </form>
    </aside>
  );
}

function JobCard({ job }) {
  const statusText = job.status.charAt(0).toUpperCase() + job.status.slice(1);
  return (
    <section className={`jobCard ${job.status}`}>
      <div className="jobTop">
        <div>
          <span className="kicker">Ingestion Job</span>
          <h2>{statusText}</h2>
          <p>{job.message}</p>
        </div>
        <strong>{job.progress}%</strong>
      </div>
      <div className="progressTrack">
        <div style={{ width: `${job.progress}%` }} />
      </div>
      <div className="jobMeta">
        <span>{job.files_indexed || 0} files</span>
        <span>{job.chunks_indexed || 0} chunks</span>
        <span>{job.kind}</span>
      </div>
      {job.error && <div className="jobError">{job.error}</div>}
    </section>
  );
}

function Results({ documents }) {
  if (!documents.length) return null;

  return (
    <section className="results">
      {documents.map((doc) => (
        <article className="resultCard" key={doc.document_id || doc.filename}>
          <div className="resultTop">
            <div>
              <h3>{doc.filename}</h3>
              <p>
                relevance {Number(doc.relevance_score).toFixed(3)} - {doc.num_matching_chunks} matching chunks
              </p>
            </div>
            {doc.metadata?.source_url && (
              <a href={doc.metadata.source_url} target="_blank" rel="noreferrer">Open source</a>
            )}
          </div>
          {(doc.chunks || []).map((chunk, index) => (
            <div className="excerpt" key={`${doc.document_id}-${index}`}>
              <span>
                excerpt {index + 1} - similarity {Number(chunk.similarity).toFixed(3)}
              </span>
              <p>{chunk.text}</p>
            </div>
          ))}
        </article>
      ))}
    </section>
  );
}

createRoot(document.getElementById("root")).render(<App />);
