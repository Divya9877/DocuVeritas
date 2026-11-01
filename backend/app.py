from claim_extractor import extract_claims
from context_filter import analyze_context
from nli_engine import compare_claims
from semantic_filter import find_candidate_pairs
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from pathlib import Path
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
import re
import sqlite3
from functools import wraps
from document_parser import extract_document
from io import BytesIO
from xml.sax.saxutils import escape

from flask import send_file
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from database import (
    init_db,
    save_audit,
    list_audits,
    get_audit,
    save_review_decision,
    list_review_decisions,
)

init_db()

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Set DOCUVERITAS_SECRET_KEY in your environment for deployments.
app.secret_key = os.environ.get("DOCUVERITAS_SECRET_KEY", "dev-only-change-this-secret")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False  # Local HTTP development only.

AUTH_DB = Path(__file__).parent / "auth_users.sqlite3"

def init_auth_db():
    with sqlite3.connect(AUTH_DB) as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")

init_auth_db()

@app.before_request
def require_login_for_api():
    # Browsers send OPTIONS preflight requests before certain cross-origin
    # requests (such as JSON POST requests). They must reach Flask-CORS and
    # must not be rejected by session authentication.
    if request.method == "OPTIONS":
        return "", 204

    # Public health check and authentication endpoints remain accessible.
    if (
        request.path.startswith("/api/")
        and request.path != "/api/health"
        and not request.path.startswith("/api/auth/")
    ):
        if not session.get("user_id"):
            return jsonify({"error": "Please sign in to access this resource."}), 401

@app.post("/api/auth/signup")
def signup():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip() if isinstance(data.get("name", ""), str) else ""
    email = data.get("email", "").strip().lower() if isinstance(data.get("email", ""), str) else ""
    password = data.get("password", "")
    if not name:
        return jsonify({"error": "Name is required."}), 400
    if len(name) > 100:
        return jsonify({"error": "Name must be 100 characters or fewer."}), 400
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
        return jsonify({"error": "Enter a valid email address."}), 400
    if not isinstance(password, str) or len(password) < 8:
        return jsonify({"error": "Password must contain at least 8 characters."}), 400
    if len(password) > 128:
        return jsonify({"error": "Password must be 128 characters or fewer."}), 400
    try:
        with sqlite3.connect(AUTH_DB) as connection:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password))
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        return jsonify({"error": "An account with this email already exists. Please sign in."}), 409
    session.clear()
    session["user_id"] = user_id
    session["user_email"] = email
    return jsonify({"message": "Account created successfully.", "user": {"id": user_id, "name": name, "email": email}}), 201

@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower() if isinstance(data.get("email", ""), str) else ""
    password = data.get("password", "")
    if not email or not isinstance(password, str):
        return jsonify({"error": "Email and password are required."}), 400
    with sqlite3.connect(AUTH_DB) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT id, name, email, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "Incorrect email or password."}), 401
    session.clear()
    session["user_id"] = row["id"]
    session["user_email"] = row["email"]
    return jsonify({"message": "Signed in successfully.", "user": {"id": row["id"], "name": row["name"], "email": row["email"]}}), 200

@app.get("/api/auth/me")
def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"user": None}), 200
    with sqlite3.connect(AUTH_DB) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        session.clear()
        return jsonify({"user": None}), 200
    return jsonify({"user": dict(row)}), 200

@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"message": "Signed out successfully."}), 200

UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE


@app.get("/")
def home():
    return jsonify({
        "project": "DocuVeritas AI",
        "status": "running",
        "message": "Document consistency auditing API is ready."
    })


@app.get("/api/health")
def health():
    return jsonify({"status": "healthy"})


@app.post("/api/documents/upload")
def upload_document():
    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400

    uploaded_file = request.files["file"]

    if not uploaded_file.filename:
        return jsonify({"error": "Please select a file."}), 400

    safe_name = secure_filename(uploaded_file.filename)

    if not safe_name:
        return jsonify({"error": "Invalid filename."}), 400

    extension = Path(safe_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": "Only PDF and DOCX files are supported."
        }), 400

    # Use a unique storage name to avoid overwriting another upload.
    import uuid
    stored_name = f"{uuid.uuid4().hex}{extension}"
    file_path = UPLOAD_FOLDER / stored_name

    try:
        uploaded_file.save(file_path)
        result = extract_document(file_path)

        if not any(
            item.get("text", "").strip()
            for item in result["content"]
        ):
            return jsonify({
                "error": (
                    "No readable text was found. "
                    "The PDF may be scanned and require OCR."
                )
            }), 422

        return jsonify({
            "message": "Document uploaded and parsed successfully.",
            "filename": safe_name,
            "format": result["format"],
            "content": result["content"]
        }), 200

    except Exception:
        app.logger.exception("Document processing failed")
        return jsonify({
            "error": "Unable to process this document."
        }), 500

    finally:
        # Remove the temporary upload after extraction.
        if file_path.exists():
            file_path.unlink()


@app.errorhandler(413)
def file_too_large(error):
    return jsonify({
        "error": "File exceeds the 10 MB limit."
    }), 413


@app.post("/api/claims/extract")
def extract_document_claims():
    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400

    uploaded_file = request.files["file"]

    if not uploaded_file.filename:
        return jsonify({"error": "Please select a file."}), 400

    safe_name = secure_filename(uploaded_file.filename)

    if not safe_name:
        return jsonify({"error": "Invalid filename."}), 400

    extension = Path(safe_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": "Only PDF and DOCX files are supported."
        }), 400

    import uuid
    stored_name = f"{uuid.uuid4().hex}{extension}"
    file_path = UPLOAD_FOLDER / stored_name

    try:
        uploaded_file.save(file_path)
        document = extract_document(file_path)

        if not any(
            item.get("text", "").strip()
            for item in document["content"]
        ):
            return jsonify({
                "error": "No readable text was found in the document."
            }), 422

        # Use the original filename for claim provenance.
        document["filename"] = safe_name
        claims = extract_claims(document)

        return jsonify({
            "filename": safe_name,
            "total_claims": len(claims),
            "claims": claims
        }), 200

    except Exception:
        app.logger.exception("Claim extraction failed")
        return jsonify({
            "error": "Unable to extract claims from this document."
        }), 500

    finally:
        if file_path.exists():
            file_path.unlink()


@app.post("/api/contradiction/compare")
def compare_claim_pair():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Send a JSON object containing claim_a and claim_b."
        }), 400

    claim_a = data.get("claim_a")
    claim_b = data.get("claim_b")

    if not isinstance(claim_a, str) or not claim_a.strip():
        return jsonify({"error": "claim_a is required."}), 400

    if not isinstance(claim_b, str) or not claim_b.strip():
        return jsonify({"error": "claim_b is required."}), 400

    if len(claim_a) > 2000 or len(claim_b) > 2000:
        return jsonify({
            "error": "Each claim must be 2000 characters or fewer."
        }), 400

    try:
        result = compare_claims(claim_a, claim_b)
        return jsonify(result), 200

    except Exception:
        app.logger.exception("NLI comparison failed")
        return jsonify({
            "error": "Unable to compare claims. Check the backend logs."
        }), 500


@app.post("/api/contradiction/analyze")
def analyze_claim_pair():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    claim_a = data.get("claim_a")
    claim_b = data.get("claim_b")

    if not isinstance(claim_a, dict) or not isinstance(claim_b, dict):
        return jsonify({
            "error": "claim_a and claim_b must be JSON objects."
        }), 400

    for name, claim in (("claim_a", claim_a), ("claim_b", claim_b)):
        text = claim.get("text")

        if not isinstance(text, str) or not text.strip():
            return jsonify({
                "error": f"{name} must contain non-empty text."
            }), 400

        if len(text) > 2000:
            return jsonify({
                "error": f"{name} text must be 2000 characters or fewer."
            }), 400

    context = analyze_context(claim_a, claim_b)

    result = {
        "claim_a": claim_a,
        "claim_b": claim_b,
        "context_analysis": context,
        "nli_analysis": None
    }

    if context["compare_with_nli"]:
        try:
            result["nli_analysis"] = compare_claims(
                claim_a["text"],
                claim_b["text"]
            )
        except Exception:
            app.logger.exception("NLI analysis failed")
            return jsonify({
                "error": "AI comparison failed. Check backend logs."
            }), 500

    return jsonify(result), 200


@app.post("/api/contradiction/batch")
def analyze_document_pair():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    claims_a = data.get("claims_a")
    claims_b = data.get("claims_b")

    if not isinstance(claims_a, list) or not isinstance(claims_b, list):
        return jsonify({
            "error": "claims_a and claims_b must be lists."
        }), 400

    if not claims_a or not claims_b:
        return jsonify({
            "error": "Both documents must contain claims."
        }), 400

    if len(claims_a) > 100 or len(claims_b) > 100:
        return jsonify({
            "error": "This demo supports up to 100 claims per document."
        }), 400

    for claim in claims_a + claims_b:
        if (
            not isinstance(claim, dict)
            or not isinstance(claim.get("text"), str)
            or not claim["text"].strip()
            or len(claim["text"]) > 2000
        ):
            return jsonify({
                "error": (
                    "Every claim must contain valid text "
                    "of at most 2000 characters."
                )
            }), 400

    try:
        candidates = find_candidate_pairs(claims_a, claims_b)
        findings = []

        for candidate in candidates:
            a = candidate["claim_a"]
            b = candidate["claim_b"]

            context = analyze_context(a, b)

            nli = None
            if context["compare_with_nli"]:
                nli = compare_claims(a["text"], b["text"])

            findings.append({
                "claim_a": a,
                "claim_b": b,
                "similarity": candidate["similarity"],
                "context_analysis": context,
                "nli_analysis": nli
            })

        # Save the completed audit to SQLite.
        document_a = claims_a[0].get(
            "source_document", "Document A"
        )
        document_b = claims_b[0].get(
            "source_document", "Document B"
        )

        audit_id = save_audit(
            document_a=document_a,
            document_b=document_b,
            claims_a_count=len(claims_a),
            claims_b_count=len(claims_b),
            possible_pairs=len(claims_a) * len(claims_b),
            candidate_pairs=len(candidates),
            findings=findings
        )

        return jsonify({
            "audit_id": audit_id,
            "total_possible_pairs": len(claims_a) * len(claims_b),
            "candidate_pairs": len(candidates),
            "findings": findings
        }), 200

    except Exception:
        app.logger.exception("Batch contradiction analysis failed")
        return jsonify({
            "error": "Analysis failed. Check the backend terminal."
        }), 500


# --------------------------------------------------
# HUMAN REVIEW API
# --------------------------------------------------

@app.post("/api/audits/<int:audit_id>/reviews")
def create_or_update_review(audit_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Send a JSON object containing finding_index and decision."
        }), 400

    finding_index = data.get("finding_index")
    decision = data.get("decision")
    reviewer_comment = data.get("reviewer_comment", "")

    # bool is a subclass of int in Python, so check the exact type.
    if type(finding_index) is not int or finding_index < 0:
        return jsonify({
            "error": "finding_index must be a non-negative integer."
        }), 400

    allowed_decisions = {
        "confirmed_contradiction",
        "false_positive",
        "needs_review"
    }

    if decision not in allowed_decisions:
        return jsonify({
            "error": (
                "decision must be confirmed_contradiction, "
                "false_positive, or needs_review."
            )
        }), 400

    if not isinstance(reviewer_comment, str):
        return jsonify({
            "error": "reviewer_comment must be a string."
        }), 400

    if len(reviewer_comment) > 2000:
        return jsonify({
            "error": "reviewer_comment must be 2000 characters or fewer."
        }), 400

    try:
        review = save_review_decision(
            audit_id=audit_id,
            finding_index=finding_index,
            decision=decision,
            reviewer_comment=reviewer_comment.strip()
        )
        return jsonify({
            "message": "Review decision saved successfully.",
            "review": review
        }), 200

    except ValueError as error:
        message = str(error)
        status_code = 404 if message == "Audit not found" else 400
        return jsonify({"error": message}), status_code

    except Exception:
        app.logger.exception("Saving human review failed")
        return jsonify({
            "error": "Unable to save review decision. Check backend logs."
        }), 500


@app.get("/api/audits/<int:audit_id>/reviews")
def get_audit_reviews(audit_id):
    # Return 404 when the requested audit does not exist.
    audit = get_audit(audit_id)

    if audit is None:
        return jsonify({"error": "Audit not found."}), 404

    try:
        reviews = list_review_decisions(audit_id)
        return jsonify({
            "audit_id": audit_id,
            "reviews": reviews
        }), 200

    except Exception:
        app.logger.exception("Retrieving human reviews failed")
        return jsonify({
            "error": "Unable to retrieve review decisions."
        }), 500


# --------------------------------------------------
# AUDIT HISTORY API
# --------------------------------------------------

@app.get("/api/audits")
def audit_history():
    return jsonify({
        "audits": list_audits()
    }), 200


@app.get("/api/audits/<int:audit_id>")
def audit_details(audit_id):
    audit = get_audit(audit_id)

    if audit is None:
        return jsonify({
            "error": "Audit not found."
        }), 404

    return jsonify(audit), 200

# --------------------------------------------------
# PDF AUDIT REPORT API
# --------------------------------------------------

@app.get("/api/audits/<int:audit_id>/report.pdf")
def download_audit_report(audit_id):
    audit = get_audit(audit_id)

    if audit is None:
        return jsonify({"error": "Audit not found."}), 404

    try:
        reviews = list_review_decisions(audit_id)

        # Match saved review decisions to their finding indexes.
        reviews_by_index = {
            review["finding_index"]: review
            for review in reviews
        }

        findings = audit.get("findings", [])
        if isinstance(findings, str):
            import json
            findings = json.loads(findings)

        buffer = BytesIO()

        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.8 * cm,
            leftMargin=1.8 * cm,
            topMargin=1.8 * cm,
            bottomMargin=1.8 * cm,
            title=f"DocuVeritas AI Audit Report {audit_id}",
        )

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=20,
            leading=25,
            spaceAfter=12,
        ))
        styles.add(ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading2"],
            fontSize=13,
            leading=17,
            spaceBefore=12,
            spaceAfter=7,
        ))
        styles.add(ParagraphStyle(
            name="SmallBody",
            parent=styles["BodyText"],
            fontSize=9,
            leading=13,
            spaceAfter=5,
            wordWrap="CJK",
        ))

        def safe_text(value):
            if value is None or value == "":
                return "Not available"
            return escape(str(value)).replace("\n", "<br/>")

        def paragraph(label, value):
            return Paragraph(
                f"<b>{safe_text(label)}:</b> {safe_text(value)}",
                styles["SmallBody"],
            )

        story = [
            Paragraph("DocuVeritas AI", styles["ReportTitle"]),
            Paragraph(
                "Document Consistency and Contradiction Audit Report",
                styles["Heading2"],
            ),
            Spacer(1, 10),
            paragraph("Audit ID", audit_id),
            paragraph("Document A", audit.get("document_a")),
            paragraph("Document B", audit.get("document_b")),
            paragraph("Created at", audit.get("created_at")),
            paragraph("Claims in Document A", audit.get("claims_a_count")),
            paragraph("Claims in Document B", audit.get("claims_b_count")),
            paragraph("Total possible pairs", audit.get("possible_pairs")),
            paragraph("Candidate pairs analyzed", audit.get("candidate_pairs")),
            Spacer(1, 10),
            Paragraph("Findings", styles["SectionHeading"]),
        ]

        if not findings:
            story.append(Paragraph(
                "No candidate findings were recorded for this audit.",
                styles["SmallBody"],
            ))

        for index, finding in enumerate(findings):
            claim_a = finding.get("claim_a", {})
            claim_b = finding.get("claim_b", {})
            context = finding.get("context_analysis") or {}
            nli = finding.get("nli_analysis") or {}
            review = reviews_by_index.get(index, {})

            story.append(Paragraph(
                f"Finding {index + 1}",
                styles["Heading3"],
            ))

            story.append(paragraph(
                "Document A claim",
                claim_a.get("text", "Not available"),
            ))
            story.append(paragraph(
                "Document B claim",
                claim_b.get("text", "Not available"),
            ))
            story.append(paragraph(
                "Semantic similarity",
                finding.get("similarity"),
            ))
            story.append(paragraph(
                "Context result",
                context.get("classification", context.get("status", "Not available")),
            ))
            story.append(paragraph(
                "Context explanation",
                context.get("reason", context.get("message", "Not available")),
            ))

            if nli:
                story.append(paragraph(
                    "AI prediction",
                    nli.get("label", nli.get("prediction", nli.get("predicted_label", "Not available"))),
                ))
                story.append(paragraph(
                    "AI scores",
                    nli.get("scores", nli.get("probabilities", "Not available")),
                ))
            else:
                story.append(paragraph(
                    "AI prediction",
                    "Not performed for this pair",
                ))

            decision = review.get("decision")
            decision_labels = {
                "confirmed_contradiction": "Confirmed contradiction",
                "false_positive": "False positive",
                "needs_review": "Needs further review",
            }

            story.append(paragraph(
                "Human review",
                decision_labels.get(decision, "Pending review"),
            ))
            story.append(paragraph(
                "Reviewer comment",
                review.get("reviewer_comment", ""),
            ))
            story.append(Spacer(1, 8))

        story.extend([
            Spacer(1, 12),
            Paragraph("Important Note", styles["SectionHeading"]),
            Paragraph(
                "AI-generated findings are preliminary and may contain errors. "
                "Review the original documents and supporting context before "
                "making important decisions. Human-review statuses reflect "
                "the decisions saved in this audit.",
                styles["SmallBody"],
            ),
        ])

        pdf.build(story)
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"docuveritas_audit_{audit_id}.pdf",
        )

    except Exception:
        app.logger.exception("PDF audit report generation failed")
        return jsonify({
            "error": "Unable to generate the PDF report. Check the backend terminal."
        }), 500
    
if __name__ == "__main__":
    app.run(debug=True, port=5000)
