
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DATABASE_PATH = Path(__file__).parent / "docuveritas.db"


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# --------------------------------------------------
# INITIALIZE DATABASE
# --------------------------------------------------

def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_a TEXT NOT NULL,
                document_b TEXT NOT NULL,
                created_at TEXT NOT NULL,
                claims_a_count INTEGER NOT NULL,
                claims_b_count INTEGER NOT NULL,
                possible_pairs INTEGER NOT NULL,
                candidate_pairs INTEGER NOT NULL,
                contradiction_count INTEGER NOT NULL,
                findings_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS review_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id INTEGER NOT NULL,
                finding_index INTEGER NOT NULL,
                decision TEXT NOT NULL CHECK (
                    decision IN (
                        'confirmed_contradiction',
                        'false_positive',
                        'needs_review'
                    )
                ),
                reviewer_comment TEXT DEFAULT '',
                reviewed_at TEXT NOT NULL,

                FOREIGN KEY (audit_id)
                    REFERENCES audits(id)
                    ON DELETE CASCADE,

                UNIQUE (audit_id, finding_index)
            );
        """)


# --------------------------------------------------
# SAVE AUDIT
# --------------------------------------------------

def save_audit(
    document_a,
    document_b,
    claims_a_count,
    claims_b_count,
    possible_pairs,
    candidate_pairs,
    findings
):
    contradiction_count = sum(
        1 for item in findings
        if (item.get("nli_analysis") or {}).get("prediction")
        == "contradiction"
    )

    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO audits (
                document_a,
                document_b,
                created_at,
                claims_a_count,
                claims_b_count,
                possible_pairs,
                candidate_pairs,
                contradiction_count,
                findings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            document_a,
            document_b,
            created_at,
            claims_a_count,
            claims_b_count,
            possible_pairs,
            candidate_pairs,
            contradiction_count,
            json.dumps(findings, ensure_ascii=False)
        ))

        return cursor.lastrowid


# --------------------------------------------------
# LIST AUDITS
# --------------------------------------------------

def list_audits(limit=50):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                id,
                document_a,
                document_b,
                created_at,
                claims_a_count,
                claims_b_count,
                possible_pairs,
                candidate_pairs,
                contradiction_count
            FROM audits
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(row) for row in rows]


# --------------------------------------------------
# GET SINGLE AUDIT
# --------------------------------------------------

def get_audit(audit_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM audits WHERE id = ?",
            (audit_id,)
        ).fetchone()

        if row is None:
            return None

        audit = dict(row)

        audit["findings"] = json.loads(
            audit.pop("findings_json")
        )

        return audit


# --------------------------------------------------
# SAVE OR UPDATE HUMAN REVIEW DECISION
# --------------------------------------------------

def save_review_decision(
    audit_id,
    finding_index,
    decision,
    reviewer_comment=""
):
    allowed_decisions = {
        "confirmed_contradiction",
        "false_positive",
        "needs_review"
    }

    if decision not in allowed_decisions:
        raise ValueError("Invalid review decision")

    if type(finding_index) is not int:
        raise ValueError("Finding index must be an integer")

    if type(audit_id) is not int:
        raise ValueError("Audit ID must be an integer")

    if not isinstance(reviewer_comment, str):
        raise ValueError("Reviewer comment must be a string")

    reviewed_at = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:

        # Verify that the audit exists
        audit = conn.execute("""
            SELECT findings_json
            FROM audits
            WHERE id = ?
        """, (audit_id,)).fetchone()

        if audit is None:
            raise ValueError("Audit not found")

        # Verify that the finding index exists
        findings = json.loads(audit["findings_json"])

        if not (0 <= finding_index < len(findings)):
            raise ValueError("Invalid finding index")

        # Insert a new decision or update an existing one
        conn.execute("""
            INSERT INTO review_decisions (
                audit_id,
                finding_index,
                decision,
                reviewer_comment,
                reviewed_at
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(audit_id, finding_index)
            DO UPDATE SET
                decision = excluded.decision,
                reviewer_comment = excluded.reviewer_comment,
                reviewed_at = excluded.reviewed_at
        """, (
            audit_id,
            finding_index,
            decision,
            reviewer_comment,
            reviewed_at
        ))

    return {
        "audit_id": audit_id,
        "finding_index": finding_index,
        "decision": decision,
        "reviewer_comment": reviewer_comment,
        "reviewed_at": reviewed_at
    }


# --------------------------------------------------
# GET HUMAN REVIEW DECISIONS FOR AN AUDIT
# --------------------------------------------------

def list_review_decisions(audit_id):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                id,
                audit_id,
                finding_index,
                decision,
                reviewer_comment,
                reviewed_at
            FROM review_decisions
            WHERE audit_id = ?
            ORDER BY finding_index
        """, (audit_id,)).fetchall()

        return [dict(row) for row in rows]


# --------------------------------------------------
# RUN DIRECTLY TO INITIALIZE DATABASE
# --------------------------------------------------

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")
