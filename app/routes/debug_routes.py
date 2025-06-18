# app/routes/debug_routes.py
from flask import Blueprint, jsonify
from app.database.database import get_db_connection

debug_bp = Blueprint("debug", __name__)


@debug_bp.route("/check-db")
def check_db():
    try:
        with get_db_connection() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()

            pending_count = conn.execute(
                "SELECT COUNT(*) FROM certif_pending_renewals"
            ).fetchone()[0]

        return jsonify(
            {"tables": [dict(t) for t in tables], "pending_count": pending_count}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
