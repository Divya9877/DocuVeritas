
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useEffect, useState } from "react";
import {
  FileText,
  Upload,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  LoaderCircle,
  GitCompareArrows,
  RefreshCw,
  Search,
  MessageSquare,
  Save,
  Clock3,
  FileDown,
  LayoutDashboard,
  History,
  ClipboardCheck,
  Files,
  FileCheck2,
  Clock3 as ReviewClock,
  Menu,
  X,
} from "lucide-react";
import "./App.css";
import "./Auth.css";
import "./Navigation.css";


const API = "http://localhost:5000";

async function apiFetch(url, options = {}) {
  return fetch(url, {
    ...options,
    credentials: "include",
  });
}


function mapFindings(findings, reviews = []) {
  const reviewByIndex = new Map(
    reviews.map((review) => [review.finding_index, review])
  );

  return (findings || []).map((item, index) => {
    const savedReview = reviewByIndex.get(index);
    const decision = savedReview?.decision || null;

    return {
      id: String(index + 1),
      findingIndex: index,
      a: item.claim_a,
      b: item.claim_b,
      similarity: item.similarity,
      context: item.context_analysis,
      nli: item.nli_analysis,
      explanation: item.genai_explanation || null,
      explanationLoading: false,
      explanationError: "",
      reviewStatus: decision
        ? decisionLabel(decision)
        : "Pending review",
      reviewDecision: decision,
      reviewComment: savedReview?.reviewer_comment || "",
    };
  });
}

function decisionLabel(decision) {
  const labels = {
    confirmed_contradiction: "Confirmed contradiction",
    false_positive: "False positive",
    needs_review: "Needs further review",
  };
  return labels[decision] || "Pending review";
}

function Dashboard({ onLogout, userEmail }) {
  const [activeView, setActiveView] = useState("overview");
  const [menuOpen, setMenuOpen] = useState(false);
  const [files, setFiles] = useState([null, null]);
  const [results, setResults] = useState([]);
  const [claimCounts, setClaimCounts] = useState([0, 0]);
  const [pairStats, setPairStats] = useState({
    possible: 0,
    candidates: 0,
  });
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [auditId, setAuditId] = useState(null);
  const [savingReviewIndex, setSavingReviewIndex] = useState(null);

  const [reviewMessage, setReviewMessage] = useState("");
  const [audits, setAudits] = useState([]);
  const [workspaceStats, setWorkspaceStats] = useState({
    documentsAnalyzed: 0,
    findingsReviewed: 0,
    unresolvedFindings: 0,
  });
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [openingAuditId, setOpeningAuditId] = useState(null);
  const [expandedEvidence, setExpandedEvidence] = useState({});
  const [documentQuestion, setDocumentQuestion] = useState("");
  const [documentAnswer, setDocumentAnswer] = useState("");
  const [documentSources, setDocumentSources] = useState([]);
  const [askingDocuments, setAskingDocuments] = useState(false);
  const [documentQuestionError, setDocumentQuestionError] = useState("");

  // Restore the most recently opened audit and its saved human reviews
  // when the page is refreshed.
  useEffect(() => {
    loadAuditHistory();
    const savedAuditId = window.localStorage.getItem("docuveritas.lastAuditId");
    if (!savedAuditId) return;

    let cancelled = false;

    async function restoreAudit() {
      try {
        const auditResponse = await apiFetch(`${API}/api/audits/${savedAuditId}`);
        const audit = await readJson(auditResponse);

        const reviewsResponse = await apiFetch(
          `${API}/api/audits/${savedAuditId}/reviews`
        );
        const reviewsData = await readJson(reviewsResponse);

        if (cancelled) return;

        setAuditId(audit.id);
        setClaimCounts([audit.claims_a_count || 0, audit.claims_b_count || 0]);
        setPairStats({
          possible: audit.possible_pairs || 0,
          candidates: audit.candidate_pairs || 0,
        });
        setResults(mapFindings(audit.findings || [], reviewsData.reviews || []));
        setProgress(`Restored saved audit #${audit.id}.`);
      } catch (err) {
        if (!cancelled) {
          setReviewMessage(
            `Could not restore the previous audit: ${err.message}. Run a new analysis if needed.`
          );
        }
      }
    }

    restoreAudit();

    return () => {
      cancelled = true;
    };
  }, []);

  async function loadAuditHistory() {
    setHistoryLoading(true);
    setHistoryError("");

    try {
      const response = await apiFetch(`${API}/api/audits`);
      const data = await readJson(response);
      const auditList = Array.isArray(data) ? data : (data.audits || []);
      setAudits(auditList);

      // Calculate workspace-wide statistics from saved audits and their review records.
      const documentsAnalyzed = auditList.reduce(
        (total, audit) => total + (audit.document_a ? 1 : 0) + (audit.document_b ? 1 : 0),
        0
      );

      const auditStats = await Promise.all(
        auditList.map(async (audit) => {
          try {
            const [detailResponse, reviewsResponse] = await Promise.all([
              apiFetch(`${API}/api/audits/${audit.id}`),
              apiFetch(`${API}/api/audits/${audit.id}/reviews`),
            ]);
            const [detail, reviewData] = await Promise.all([
              readJson(detailResponse),
              readJson(reviewsResponse),
            ]);
            const findingCount = Array.isArray(detail.findings) ? detail.findings.length : 0;
            const reviewedCount = Array.isArray(reviewData.reviews) ? reviewData.reviews.length : 0;
            return {
              findingCount,
              reviewedCount: Math.min(reviewedCount, findingCount),
            };
          } catch {
            // Keep the dashboard usable if one historical audit cannot be loaded.
            return { findingCount: 0, reviewedCount: 0 };
          }
        })
      );

      const findingsReviewed = auditStats.reduce((total, item) => total + item.reviewedCount, 0);
      const totalFindings = auditStats.reduce((total, item) => total + item.findingCount, 0);
      setWorkspaceStats({
        documentsAnalyzed,
        findingsReviewed,
        unresolvedFindings: Math.max(0, totalFindings - findingsReviewed),
      });
    } catch (err) {
      setHistoryError(`Could not load audit history: ${err.message}`);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function openSavedAudit(id) {
    setOpeningAuditId(id);
    setError("");
    setReviewMessage("");
    setProgress("");

    try {
      const auditResponse = await apiFetch(`${API}/api/audits/${id}`);
      const audit = await readJson(auditResponse);

      const reviewsResponse = await apiFetch(`${API}/api/audits/${id}/reviews`);
      const reviewsData = await readJson(reviewsResponse);

      setAuditId(audit.id);
      window.localStorage.setItem("docuveritas.lastAuditId", String(audit.id));
      setClaimCounts([audit.claims_a_count || 0, audit.claims_b_count || 0]);
      setPairStats({
        possible: audit.possible_pairs || 0,
        candidates: audit.candidate_pairs || 0,
      });
      setResults(mapFindings(audit.findings || [], reviewsData.reviews || []));
      setProgress(`Opened saved audit #${audit.id}.`);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(`Could not open audit: ${err.message}`);
    } finally {
      setOpeningAuditId(null);
    }
  }

  function selectFile(index, file) {
    setFiles((old) =>
      old.map((item, i) => (i === index ? file : item))
    );

    setResults([]);
    setClaimCounts([0, 0]);
    setPairStats({ possible: 0, candidates: 0 });
    setAuditId(null);
    setReviewMessage("");
    setError("");
    setProgress("");
  }

  async function readJson(response) {
    let data;

    try {
      data = await response.json();
    } catch {
      throw new Error("The backend returned an invalid response.");
    }

    if (!response.ok) {
      throw new Error(
        data.error || `Request failed with status ${response.status}.`
      );
    }

    return data;
  }

  async function extractClaims(file) {
    const form = new FormData();
    form.append("file", file);

    const response = await apiFetch(
      `${API}/api/claims/extract`,
      {
        method: "POST",
        body: form,
      }
    );

    const data = await readJson(response);
    return data.claims || [];
  }

  async function analyzeDocuments() {
    if (!files[0] || !files[1]) {
      setError("Please select both documents before starting.");
      return;
    }

    setLoading(true);
    setError("");
    setResults([]);
    setClaimCounts([0, 0]);
    setPairStats({ possible: 0, candidates: 0 });
    setAuditId(null);
    setReviewMessage("");

    try {
      // Step 1: Extract claims from Document A.
      setProgress("Extracting claims from Document A...");

      const claimsA = await extractClaims(files[0]);

      setClaimCounts([claimsA.length, 0]);

      // Step 2: Extract claims from Document B.
      setProgress("Extracting claims from Document B...");

      const claimsB = await extractClaims(files[1]);

      setClaimCounts([claimsA.length, claimsB.length]);

      if (!claimsA.length || !claimsB.length) {
        throw new Error(
          "At least one document has no extractable claims."
        );
      }

      // Step 3: Send both claim lists to the batch API.
      setProgress(
        "Finding semantically related claims and analyzing contradictions..."
      );

      const response = await apiFetch(
        `${API}/api/contradiction/batch`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            claims_a: claimsA,
            claims_b: claimsB,
          }),
        }
      );

      const data = await readJson(response);

      // Store the audit ID so human-review decisions attach to this audit.
      setAuditId(data.audit_id ?? null);
      if (data.audit_id != null) {
        window.localStorage.setItem(
          "docuveritas.lastAuditId",
          String(data.audit_id)
        );
      }

      // Step 4: Store candidate-pair statistics.
      setPairStats({
        possible: data.total_possible_pairs ?? claimsA.length * claimsB.length,
        candidates: data.candidate_pairs ?? 0,
      });

      // Step 5: Convert backend results into dashboard format.
      const findings = mapFindings(data.findings || []);

      setResults(findings);
      setProgress(
        `Analysis complete. ${findings.length} candidate pairs analyzed.`
      );
    } catch (err) {
      setError(
        `${err.message} Check that Flask is running on port 5000.`
      );
      setProgress("");
    } finally {
      setLoading(false);
    }
  }

  const contradictions = results.filter(
    (r) => r.nli?.prediction === "contradiction"
  );

  const contextReviews = results.filter(
    (r) => r.context?.decision !== "comparable"
  );

  const reviewedPairs = results.length;

  const reduction = pairStats.possible > 0
    ? Math.round(
        (1 - pairStats.candidates / pairStats.possible) * 100
      )
    : 0;

  function labelFor(result) {
    if (!result.nli) {
      return result.context?.decision || "Needs review";
    }

    return result.nli.prediction;
  }

  async function saveReview(result, decision) {
    if (auditId == null) {
      setReviewMessage("No saved audit ID was returned. Run the analysis again.");
      return;
    }

    setSavingReviewIndex(result.findingIndex);
    setReviewMessage("");
    setError("");

    try {
      const response = await apiFetch(
        `${API}/api/audits/${auditId}/reviews`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            finding_index: result.findingIndex,
            decision,
            reviewer_comment: result.reviewComment || "",
          }),
        }
      );

      const data = await readJson(response);

      setResults((current) =>
        current.map((item) =>
          item.findingIndex === result.findingIndex
            ? {
                ...item,
                reviewDecision: data.review.decision,
                reviewStatus: decisionLabel(data.review.decision),
              }
            : item
        )
      );

      setReviewMessage(`Review saved for Pair ${result.id}.`);
    } catch (err) {
      setReviewMessage(`Could not save review: ${err.message}`);
    } finally {
      setSavingReviewIndex(null);
    }
  }

  function updateReviewComment(findingIndex, comment) {
    setResults((current) =>
      current.map((item) =>
        item.findingIndex === findingIndex
          ? { ...item, reviewComment: comment }
          : item
      )
    );
  }

  async function generateExplanation(result) {
    setResults((current) => current.map((item) =>
      item.findingIndex === result.findingIndex
        ? { ...item, explanationLoading: true, explanationError: "" }
        : item
    ));

    try {
       console.log("Explanation claim A:", result.a.text);
       console.log("Explanation claim B:", result.b.text);
      const response = await apiFetch(`${API}/api/contradiction/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          claim_a: result.a.text,
          claim_b: result.b.text,
        }),
      });
      const data = await readJson(response);
      setResults((current) => current.map((item) =>
        item.findingIndex === result.findingIndex
          ? { ...item, explanation: data.explanation, explanationError: "" }
          : item
      ));
    } catch (err) {
      setResults((current) => current.map((item) =>
        item.findingIndex === result.findingIndex
          ? { ...item, explanationError: err.message }
          : item
      ));
    } finally {
      setResults((current) => current.map((item) =>
        item.findingIndex === result.findingIndex
          ? { ...item, explanationLoading: false }
          : item
      ));
    }
  }

  async function askAboutDocuments(event) {
    event?.preventDefault();
    if (!files[0] || !files[1]) {
      setDocumentQuestionError("First open Document Audit and select both PDF/DOCX files.");
      return;
    }
    if (!documentQuestion.trim()) {
      setDocumentQuestionError("Enter a question about the uploaded documents.");
      return;
    }
    setAskingDocuments(true);
    setDocumentQuestionError("");
    setDocumentAnswer("");
    setDocumentSources([]);
    try {
      const form = new FormData();
      form.append("document_a", files[0]);
      form.append("document_b", files[1]);
      form.append("question", documentQuestion.trim());
      const response = await apiFetch(`${API}/api/documents/ask`, {
        method: "POST",
        body: form,
      });
      const data = await readJson(response);
      setDocumentAnswer(data.answer || "No answer was returned.");
      setDocumentSources(data.sources || []);
    } catch (err) {
      setDocumentQuestionError(err.message || "Could not answer the question.");
    } finally {
      setAskingDocuments(false);
    }
  }

  function resetDashboard() {
    window.localStorage.removeItem("docuveritas.lastAuditId");
    setFiles([null, null]);
    setResults([]);
    setClaimCounts([0, 0]);
    setPairStats({ possible: 0, candidates: 0 });
    setAuditId(null);
    setReviewMessage("");
    setError("");
    setProgress("");
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <button
          type="button"
          className="brand brand-button"
          onClick={() => { setActiveView("overview"); setMenuOpen(false); }}
          aria-label="Go to overview"
        >
          <span className="brand-icon"><ShieldCheck size={25} /></span>
          <span className="brand-copy">
            <strong>DocuVeritas</strong>
            <small>AI DOCUMENT AUDITOR</small>
          </span>
        </button>

        <button
          type="button"
          className="menu-toggle"
          onClick={() => setMenuOpen((open) => !open)}
          aria-label={menuOpen ? "Close navigation menu" : "Open navigation menu"}
          aria-expanded={menuOpen}
        >
          {menuOpen ? <X size={23} /> : <Menu size={23} />}
        </button>

        <nav className={`top-navigation ${menuOpen ? "is-open" : ""}`} aria-label="Main navigation">
          <button type="button" className={`top-nav-item ${activeView === "overview" ? "active" : ""}`} onClick={() => { setActiveView("overview"); setMenuOpen(false); }}><LayoutDashboard size={18} /><span>Overview</span></button>
          <button type="button" className={`top-nav-item ${activeView === "audit" ? "active" : ""}`} onClick={() => { setActiveView("audit"); setMenuOpen(false); }}><FileText size={18} /><span>Document Audit</span></button>
          <button type="button" className={`top-nav-item ${activeView === "contradictions" ? "active" : ""}`} onClick={() => { setActiveView("contradictions"); setMenuOpen(false); }}><GitCompareArrows size={18} /><span>Contradiction Analysis</span></button>
          <button type="button" className={`top-nav-item ${activeView === "ask" ? "active" : ""}`} onClick={() => { setActiveView("ask"); setMenuOpen(false); }}><MessageSquare size={18} /><span>Ask Documents</span></button>
          <button type="button" className={`top-nav-item ${activeView === "history" ? "active" : ""}`} onClick={() => { setActiveView("history"); setMenuOpen(false); loadAuditHistory(); }}><History size={18} /><span>Audit History</span></button>
          <button type="button" className={`top-nav-item ${activeView === "review" ? "active" : ""}`} onClick={() => { setActiveView("review"); setMenuOpen(false); }}><ClipboardCheck size={18} /><span>Human Review</span></button>
          <button type="button" className={`top-nav-item ${activeView === "reports" ? "active" : ""}`} onClick={() => { setActiveView("reports"); setMenuOpen(false); loadAuditHistory(); }}><FileDown size={18} /><span>Reports</span></button>
          <div className="mobile-account">
            <span className="status-pill"><span className="status-dot" />{userEmail || "Signed in"}</span>
            <button type="button" className="secondary-button" onClick={onLogout}>Log out</button>
          </div>
        </nav>
      </header>

      <main className="main-content">
        <header className="topbar">
          <div>
            <span className="breadcrumb">Workspace / {({ overview: "Overview", audit: "Document audit", contradictions: "Contradiction analysis", ask: "Ask documents", history: "Audit history", review: "Human review", reports: "Reports" })[activeView]}</span>
            <h1>{({ overview: "Workspace overview", audit: "Document consistency audit", contradictions: "Contradiction analysis", ask: "Ask your documents", history: "Audit history", review: "Human review", reports: "Audit reports" })[activeView]}</h1>
            <p>{({ overview: "Review your document auditing activity at a glance.", audit: "Upload two documents and compare their claims.", contradictions: "Inspect semantic matches and potential conflicts.", ask: "Ask questions grounded in evidence retrieved from your uploaded documents.", history: "Reopen previous comparisons and review their results.", review: "Review AI predictions and record human decisions.", reports: "Download PDF reports from completed audits." })[activeView]}</p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
            <span className="status-pill">
              <span className="status-dot" />
              {userEmail || "Signed in"}
            </span>
            <button type="button" className="secondary-button" onClick={onLogout}>
              Log out
            </button>
          </div>
        </header>

        {/* Dashboard statistics */}
        {(activeView === "overview") && (
        <section className="metrics">
          <div className="metric-card">
            <span>Document A claims</span>
            <strong>{claimCounts[0]}</strong>
            <FileText size={20} />
          </div>

          <div className="metric-card">
            <span>Document B claims</span>
            <strong>{claimCounts[1]}</strong>
            <FileText size={20} />
          </div>

          <div className="metric-card">
            <span>Candidate pairs analyzed</span>
            <strong>{reviewedPairs}</strong>
            <GitCompareArrows size={20} />
          </div>

          <div className="metric-card">
            <span>Contradiction predictions</span>
            <strong>{contradictions.length}</strong>
            <AlertTriangle size={20} />
          </div>
          <div className="metric-card">
            <span>Documents analyzed</span>
            <strong>{workspaceStats.documentsAnalyzed}</strong>
            <Files size={20} />
          </div>

          <div className="metric-card">
            <span>Findings reviewed</span>
            <strong>{workspaceStats.findingsReviewed}</strong>
            <FileCheck2 size={20} />
          </div>

          <div className="metric-card">
            <span>Unresolved findings</span>
            <strong>{workspaceStats.unresolvedFindings}</strong>
            <ReviewClock size={20} />
          </div>
        </section>

        )}
        {/* Document upload */}
        {(activeView === "audit") && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Upload documents</h2>
              <p>
                Select two PDF or DOCX files to compare their claims.
              </p>
            </div>

            <span className="file-limit">
              Maximum 10 MB per file
            </span>
          </div>

          <div className="upload-grid">
            {[0, 1].map((index) => (
              <label className="upload-box" key={index}>
                <input
                  type="file"
                  accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={(event) =>
                    selectFile(
                      index,
                      event.target.files?.[0] || null
                    )
                  }
                  disabled={loading}
                />

                <div className="upload-icon">
                  <Upload size={23} />
                </div>

                <strong>
                  Document {index === 0 ? "A" : "B"}
                </strong>

                <span>
                  {files[index]?.name ||
                    "Click to choose a PDF or DOCX"}
                </span>

                <small>
                  {files[index] ? "File selected" : "Choose file"}
                </small>
              </label>
            ))}
          </div>

          <div className="action-row">
            <button
              className="primary-button"
              onClick={analyzeDocuments}
              disabled={loading}
            >
              {loading ? (
                <LoaderCircle className="spin" size={18} />
              ) : (
                <GitCompareArrows size={18} />
              )}

              {loading ? "Analyzing..." : "Analyze documents"}
            </button>

            <button
              className="secondary-button"
              onClick={resetDashboard}
              disabled={loading}
            >
              <RefreshCw size={16} />
              Reset
            </button>
          </div>

          {progress && (
            <p className="progress-text">
              {progress}
            </p>
          )}

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}
        </section>

        )}
        {/* Semantic filtering statistics */}
        {(activeView === "audit") && (
          <>
        {pairStats.possible > 0 && (
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Semantic filtering summary</h2>
                <p>
                  Related claims are shortlisted before NLI analysis.
                </p>
              </div>

              <Search size={22} />
            </div>

            <div className="metrics">
              <div className="metric-card">
                <span>All possible pairs</span>
                <strong>{pairStats.possible}</strong>
              </div>

              <div className="metric-card">
                <span>Candidate pairs</span>
                <strong>{pairStats.candidates}</strong>
              </div>

              <div className="metric-card">
                <span>Pairs filtered out</span>
                <strong>
                  {pairStats.possible - pairStats.candidates}
                </strong>
              </div>

              <div className="metric-card">
                <span>Reduction</span>
                <strong>{reduction}%</strong>
              </div>
            </div>

            <p className="progress-text">
              Filtering is a preliminary step. Some genuine conflicts
              may be missed, so results require evaluation and review.
            </p>
          </section>
        )}

        {auditId != null && (
          <p className="progress-text">Saved audit ID: {auditId}</p>
        )}

        {reviewMessage && (
          <p className="progress-text" role="status">{reviewMessage}</p>
        )}
          </>
        )}
        {/* Audit history */}
        {(activeView === "history" || activeView === "reports") && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2><Clock3 size={20} style={{ verticalAlign: "middle", marginRight: "8px" }} />Audit history</h2>
              <p>Reopen a previous comparison and its saved human-review decisions.</p>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={loadAuditHistory}
              disabled={historyLoading}
            >
              <RefreshCw size={16} />
              {historyLoading ? "Refreshing..." : "Refresh history"}
            </button>
          </div>

          {historyError && <div className="error-message">{historyError}</div>}

          {historyLoading && audits.length === 0 ? (
            <p className="progress-text">Loading audit history...</p>
          ) : audits.length === 0 ? (
            <div className="empty-state">
              <FileText size={26} />
              <strong>No saved audits found</strong>
              <p>Run an analysis to create your first audit record.</p>
            </div>
          ) : (
            <div style={{ display: "grid", gap: "12px" }}>
              {audits.map((audit) => (
                <div
                  key={audit.id}
                  style={{
                    border: "1px solid var(--border-color, #e5e7eb)",
                    borderRadius: "10px",
                    padding: "14px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: "14px",
                    flexWrap: "wrap",
                  }}
                >
                  <div style={{ minWidth: 0, flex: "1 1 260px" }}>
                    <strong>Audit #{audit.id}</strong>
                    <p style={{ margin: "6px 0", overflowWrap: "anywhere" }}>
                      {audit.document_a || "Document A"} ↔ {audit.document_b || "Document B"}
                    </p>
                    <small>
                      {audit.created_at ? new Date(audit.created_at).toLocaleString() : "Date unavailable"}
                      {" · "}
                      {audit.candidate_pairs ?? 0} candidate pairs
                      {" · "}
                      {audit.contradiction_count ?? 0} predicted contradictions
                    </small>
                  </div>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => openSavedAudit(audit.id)}
                    disabled={openingAuditId === audit.id}
                  >
                    {openingAuditId === audit.id ? (
                      <LoaderCircle className="spin" size={16} />
                    ) : (
                      <FileText size={16} />
                    )}
                    {openingAuditId === audit.id ? "Opening..." : "Open audit"}
                  </button>
                  <a
                    className="secondary-button"
                    href={`${API}/api/audits/${audit.id}/report.pdf`}
                    download={`docuveritas_audit_${audit.id}.pdf`}
                    style={{
                      textDecoration: "none",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "8px",
                    }}
                  >
                    <FileDown size={16} />
                    Download PDF
                  </a>
                </div>
              ))}
            </div>
          )}
        </section>

        )}
        {activeView === "ask" && (
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Ask your documents</h2>
                <p>Ask a question across the two selected documents. Answers use retrieved passages and cite their sources.</p>
              </div>
              <MessageSquare size={22} />
            </div>
            <div className="info-banner" style={{ marginBottom: "14px" }}>
              {files[0] && files[1]
                ? <>Selected: <strong>{files[0].name}</strong> and <strong>{files[1].name}</strong></>
                : <>No documents selected yet. Go to <strong>Document Audit</strong> and select both files first. Your selected files remain available when you switch tabs.</>}
            </div>
            <form onSubmit={askAboutDocuments}>
              <label htmlFor="document-question"><strong>Your question</strong></label>
              <textarea
                id="document-question"
                value={documentQuestion}
                onChange={(event) => setDocumentQuestion(event.target.value)}
                placeholder="e.g. What do the documents say about password rotation requirements?"
                rows={3}
                maxLength={1000}
                style={{ width: "100%", marginTop: "8px", padding: "12px", borderRadius: "10px", border: "1px solid var(--border-color, #d1d5db)", font: "inherit", resize: "vertical" }}
              />
              <div className="action-row">
                <button className="primary-button" type="submit" disabled={askingDocuments}>
                  {askingDocuments ? <LoaderCircle className="spin" size={18} /> : <Search size={18} />}
                  {askingDocuments ? "Searching evidence..." : "Ask with GenAI"}
                </button>
              </div>
            </form>
            {documentQuestionError && <div className="error-message" style={{ marginTop: "12px" }}>{documentQuestionError}</div>}
            {documentAnswer && (
              <section style={{ marginTop: "18px", padding: "16px", border: "1px solid var(--border-color, #e5e7eb)", borderRadius: "12px" }}>
                <h3 style={{ marginTop: 0 }}>Answer</h3>
                <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.65 }}>{documentAnswer}</p>
                <p style={{ color: "var(--muted-text, #64748b)", fontSize: "0.9rem" }}>AI-generated answer. Verify the cited passages in the original documents.</p>
                <h3>Retrieved source evidence</h3>
                <div className="findings-list">
                  {documentSources.map((source) => (
                    <article className="finding-card" key={source.id}>
                      <div className="finding-header">
                        <strong>[Source {source.id}] {source.document}</strong>
                        <span className="finding-number">{source.location}</span>
                      </div>
                      <p style={{ whiteSpace: "pre-wrap" }}>{source.text}</p>
                    </article>
                  ))}
                </div>
              </section>
            )}
          </section>
        )}

        {/* Analysis findings */}
        {(activeView === "contradictions" || activeView === "review") && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Analysis findings</h2>
              <p>
                Semantic matches, context decisions, and NLI predictions.
              </p>
            </div>

            <span className="result-count">
              {results.length} results
            </span>
          </div>

          {results.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">
                <FileText size={28} />
              </div>

              <strong>
                {loading ? "Analysis in progress" : "No findings yet"}
              </strong>

              <p>
                {loading
                  ? "Please wait while your documents are analyzed."
                  : "Upload two documents and start the analysis."}
              </p>
            </div>
          ) : (
            <div className="findings-list">
              {results.map((result) => (
                <article
                  className="finding-card"
                  key={result.id}
                >
                  <div className="finding-header">
                    <span
                      className={`prediction ${labelFor(result)}`}
                    >
                      {labelFor(result).replaceAll("_", " ")}
                    </span>

                    <span className="finding-number">
                      Pair {result.id}
                    </span>
                  </div>

                  <div className="claim-grid">
                    <div className="claim-box">
                      <span>DOCUMENT A</span>

                      <p>{result.a.text}</p>

                      <small>
                        {result.a.source_document || "Document A"}
                        {" · "}
                        {result.a.source_location || "Location unavailable"}
                      </small>
                    </div>

                    <div className="claim-box">
                      <span>DOCUMENT B</span>

                      <p>{result.b.text}</p>

                      <small>
                        {result.b.source_document || "Document B"}
                        {" · "}
                        {result.b.source_location || "Location unavailable"}
                      </small>
                    </div>
                  </div>

                  <div style={{ marginTop: "10px" }}>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setExpandedEvidence((current) => ({ ...current, [result.findingIndex]: !current[result.findingIndex] }))}
                      aria-expanded={Boolean(expandedEvidence[result.findingIndex])}
                    >
                      <Search size={16} />
                      {expandedEvidence[result.findingIndex] ? "Hide source evidence" : "Show source evidence"}
                    </button>
                  </div>
                  {expandedEvidence[result.findingIndex] && (
                    <section style={{ marginTop: "12px", padding: "14px", border: "1px solid var(--border-color, #e5e7eb)", borderRadius: "10px", background: "var(--surface-muted, #f8fafc)" }}>
                      <strong>Source evidence for Pair {result.id}</strong>
                      <p style={{ marginBottom: "6px" }}><strong>{result.a.source_document || "Document A"}</strong> · {result.a.source_location || "Location unavailable"}</p>
                      <p style={{ marginTop: 0 }}><mark style={{ padding: "2px 4px", borderRadius: "3px" }}>{result.a.text}</mark></p>
                      <p style={{ marginBottom: "6px" }}><strong>{result.b.source_document || "Document B"}</strong> · {result.b.source_location || "Location unavailable"}</p>
                      <p style={{ marginTop: 0 }}><mark style={{ padding: "2px 4px", borderRadius: "3px" }}>{result.b.text}</mark></p>
                      <small>Highlighted text shows the extracted claims used in this comparison. Check the source document for surrounding context.</small>
                    </section>
                  )}

                  <div className="finding-details">
                    <p>
                      <strong>Semantic similarity:</strong>{" "}
                      {typeof result.similarity === "number"
                        ? `${(result.similarity * 100).toFixed(1)}%`
                        : "Unavailable"}
                    </p>

                    <p>
                      <strong>Context decision:</strong>{" "}
                      {result.context?.decision || "Unavailable"}
                    </p>

                    <p>
                      {result.context?.reason}
                    </p>

                    {result.nli && (
                      <div className="scores">
                        {Object.entries(
                          result.nli.scores || {}
                        ).map(([name, score]) => (
                          <span key={name}>
                            {name}: {(score * 100).toFixed(1)}%
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <section
                    className="genai-explanation-panel"
                    style={{
                      marginTop: "14px",
                      padding: "14px",
                      border: "1px solid var(--border-color, #e5e7eb)",
                      borderRadius: "10px",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                      <MessageSquare size={18} />
                      <strong>GenAI explanation</strong>
                    </div>
                    <p style={{ margin: "8px 0", color: "var(--muted-text, #6b7280)" }}>
                      Generate a plain-language explanation of how these claims differ.
                      The result is AI-generated and should be checked against the source documents.
                    </p>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => generateExplanation(result)}
                      disabled={result.explanationLoading}
                    >
                      {result.explanationLoading ? (
                        <LoaderCircle className="spin" size={16} />
                      ) : (
                        <MessageSquare size={16} />
                      )}
                      {result.explanationLoading ? "Generating explanation..." : result.explanation ? "Regenerate explanation" : "Explain with GenAI"}
                    </button>
                    {result.explanationError && (
                      <p className="error-message" role="alert" style={{ marginTop: "10px" }}>
                        {result.explanationError}
                      </p>
                    )}{result.explanation && (
  <div
    className="genai-markdown"
    style={{ marginTop: "12px", lineHeight: 1.7 }}
  >
    <ReactMarkdown remarkPlugins={[remarkGfm]}>
      {result.explanation}
    </ReactMarkdown>
  </div>
)}
                  </section>

                  <div className="human-review-panel" style={{
                    marginTop: "16px",
                    paddingTop: "14px",
                    borderTop: "1px solid var(--border-color, #e5e7eb)"
                  }}>
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      marginBottom: "10px",
                      flexWrap: "wrap"
                    }}>
                      <MessageSquare size={18} />
                      <strong>Human review</strong>
                      <span className="result-count">
                        {result.reviewStatus || "Pending review"}
                      </span>
                    </div>

                    <label style={{ display: "block", marginBottom: "10px" }}>
                      <span style={{
                        display: "block",
                        fontSize: "0.9rem",
                        marginBottom: "6px"
                      }}>Reviewer comment (optional)</span>
                      <textarea
                        value={result.reviewComment || ""}
                        onChange={(event) =>
                          updateReviewComment(result.findingIndex, event.target.value)
                        }
                        maxLength={2000}
                        rows={2}
                        placeholder="Explain why you agree or disagree with the AI prediction..."
                        disabled={savingReviewIndex === result.findingIndex}
                        style={{
                          width: "100%",
                          boxSizing: "border-box",
                          padding: "10px",
                          border: "1px solid #d1d5db",
                          borderRadius: "8px",
                          font: "inherit",
                          resize: "vertical"
                        }}
                      />
                    </label>

                    <div style={{
                      display: "flex",
                      gap: "8px",
                      flexWrap: "wrap"
                    }}>
                      <button
                        type="button"
                        className="primary-button"
                        onClick={() => saveReview(result, "confirmed_contradiction")}
                        disabled={savingReviewIndex === result.findingIndex}
                      >
                        <CheckCircle2 size={16} />
                        Confirm contradiction
                      </button>

                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => saveReview(result, "false_positive")}
                        disabled={savingReviewIndex === result.findingIndex}
                      >
                        <ShieldCheck size={16} />
                        False positive
                      </button>

                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => saveReview(result, "needs_review")}
                        disabled={savingReviewIndex === result.findingIndex}
                      >
                        <AlertTriangle size={16} />
                        Needs review
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}

          {results.length > 0 && (
            <div className="review-note">
              <CheckCircle2 size={18} />

              <span>
                AI predictions are preliminary. A human reviewer must
                confirm whether a real policy conflict exists.
                {contextReviews.length > 0 &&
                  ` ${contextReviews.length} result(s) require additional context review.`}
              </span>
            </div>
          )}
        </section>

        )}
        <footer>
          DocuVeritas AI · Document intelligence and consistency review
        </footer>
      </main>
    </div>
  );
}


function AuthPage({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");

    if (mode === "signup" && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setBusy(true);
    try {
      const response = await fetch(`${API}/api/auth/${mode}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "Authentication failed.");
      onAuthenticated(data.user);
    } catch (err) {
      setError(err.message || "Could not connect to the backend.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="auth-brand">
          <div className="auth-brand-icon"><ShieldCheck size={27} /></div>
          <div>
            <h1>DocuVeritas AI</h1>
            <p>Document consistency intelligence</p>
          </div>
        </div>

        <div className="auth-intro">
          <span className="auth-eyebrow">SECURE WORKSPACE</span>
          <h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
          <p>
            {mode === "login"
              ? "Sign in to compare documents and review AI findings."
              : "Create an account to access your document audit workspace."}
          </p>
        </div>

        <form className="auth-form" onSubmit={submit}>
          {mode === "signup" && (
            <label>
              Full name
              <input
                autoComplete="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Enter your name"
                required
                maxLength={100}
              />
            </label>
          )}
          <label>
            Email address
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              required
              maxLength={254}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={mode === "signup" ? "At least 8 characters" : "Enter your password"}
              minLength={8}
              required
            />
          </label>
          {mode === "signup" && (
            <label>
              Confirm password
              <input
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder="Re-enter your password"
                minLength={8}
                required
              />
            </label>
          )}

          {error && <div className="auth-error" role="alert">{error}</div>}

          <button className="auth-submit" type="submit" disabled={busy}>
            {busy ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <p className="auth-switch">
          {mode === "login" ? "New to DocuVeritas? " : "Already have an account? "}
          <button
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "signup" : "login");
              setError("");
            }}
          >
            {mode === "login" ? "Create an account" : "Sign in"}
          </button>
        </p>
        <p className="auth-footnote">
          AI findings are preliminary and should be reviewed against the original documents.
        </p>
      </section>
    </main>
  );
}

function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/api/auth/me`, { credentials: "include" })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Session check failed.");
        if (!cancelled) setUser(data.user || null);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setCheckingSession(false);
      });
    return () => { cancelled = true; };
  }, []);

  async function logout() {
    try {
      await fetch(`${API}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } finally {
      setUser(null);
    }
  }

  if (checkingSession) {
    return <div className="auth-loading">Loading DocuVeritas AI...</div>;
  }

  return user
    ? <Dashboard userEmail={user.email} onLogout={logout} />
    : <AuthPage onAuthenticated={setUser} />;
}

export default App;

