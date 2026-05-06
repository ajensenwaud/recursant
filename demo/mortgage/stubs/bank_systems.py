"""Stub bank systems — single Flask app simulating 4 backend systems.

Endpoints:
    POST /customer-master/verify  — Verify customer BAN + PIN
    POST /kyc/verify-identity     — Verify identity documents
    POST /credit/assess-capacity  — Calculate max loan from salary
    POST /credit/decide           — Approve/deny based on LTV
    POST /core-banking/disburse   — Disburse approved loan
    GET  /health                  — Healthcheck
"""

import random
import string
import uuid

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/customer-master/verify", methods=["POST"])
def verify_customer():
    """Verify customer BAN and PIN against Customer Master."""
    data = request.get_json(silent=True) or {}
    ban = data.get("ban", "")
    pin = data.get("pin", "")

    if not ban or not pin:
        return jsonify({"status": "error", "message": "BAN and PIN are required"}), 400

    return jsonify({
        "status": "verified",
        "customer_name": "Jane Smith",
        "ban": ban,
        "account_type": "premium",
        "customer_since": "2018-03-15",
    })


@app.route("/kyc/verify-identity", methods=["POST"])
def verify_identity():
    """Verify identity documents against KYC system."""
    data = request.get_json(silent=True) or {}

    return jsonify({
        "status": "verified",
        "document_type": data.get("document_type", "passport"),
        "name": data.get("name", "Jane Smith"),
        "verification_id": str(uuid.uuid4())[:8],
        "risk_score": "low",
    })


@app.route("/credit/assess-capacity", methods=["POST"])
def assess_credit_capacity():
    """Calculate maximum loan amount from annual salary."""
    data = request.get_json(silent=True) or {}
    annual_salary = data.get("annual_salary", 0)

    try:
        annual_salary = float(annual_salary)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid salary"}), 400

    if annual_salary <= 0:
        return jsonify({"status": "error", "message": "Salary must be positive"}), 400

    max_loan = annual_salary * 4.5

    return jsonify({
        "status": "assessed",
        "annual_salary": annual_salary,
        "max_loan_amount": max_loan,
        "assessment_id": str(uuid.uuid4())[:8],
    })


@app.route("/credit/decide", methods=["POST"])
def credit_decision():
    """Make credit decision based on LTV ratio."""
    data = request.get_json(silent=True) or {}
    loan_amount = data.get("loan_amount", 0)
    property_value = data.get("property_value", 0)

    try:
        loan_amount = float(loan_amount)
        property_value = float(property_value)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid amounts"}), 400

    if property_value <= 0:
        return jsonify({"status": "error", "message": "Property value must be positive"}), 400

    ltv = (loan_amount / property_value) * 100

    if ltv <= 90:
        return jsonify({
            "status": "approved",
            "loan_amount": loan_amount,
            "property_value": property_value,
            "ltv_ratio": round(ltv, 1),
            "interest_rate": 4.5 if ltv <= 75 else 5.2,
            "term_years": 25,
            "decision_id": str(uuid.uuid4())[:8],
        })
    else:
        return jsonify({
            "status": "declined",
            "loan_amount": loan_amount,
            "property_value": property_value,
            "ltv_ratio": round(ltv, 1),
            "reason": f"LTV ratio {ltv:.1f}% exceeds maximum 90%",
            "decision_id": str(uuid.uuid4())[:8],
        })


@app.route("/compliance/check-regulations", methods=["POST"])
def check_regulations():
    """Check lending regulations — LTV and DTI ratio checks."""
    data = request.get_json(silent=True) or {}

    try:
        loan_amount = float(data.get("loan_amount", 0))
        property_value = float(data.get("property_value", 0))
        annual_income = float(data.get("annual_income", 0))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid numeric values"}), 400

    if property_value <= 0 or annual_income <= 0:
        return jsonify({"status": "error", "message": "Property value and income must be positive"}), 400

    ltv = (loan_amount / property_value) * 100
    # Assume standard monthly mortgage payment (25yr, 5% rate) for DTI
    monthly_payment = loan_amount * 0.00585  # approximate factor
    monthly_income = annual_income / 12
    dti = (monthly_payment / monthly_income) * 100 if monthly_income > 0 else 100

    violations = []
    if ltv > 95:
        violations.append(f"LTV ratio {ltv:.1f}% exceeds regulatory maximum of 95%")
    if dti > 45:
        violations.append(f"DTI ratio {dti:.1f}% exceeds regulatory maximum of 45%")

    return jsonify({
        "status": "checked",
        "ltv_ratio": round(ltv, 1),
        "dti_ratio": round(dti, 1),
        "violations": violations,
        "compliant": len(violations) == 0,
    })


@app.route("/compliance/verify-documents", methods=["POST"])
def verify_documents():
    """Check that all required documents have been provided."""
    data = request.get_json(silent=True) or {}
    provided_raw = data.get("document_types_provided", "")

    if isinstance(provided_raw, list):
        provided = {d.strip().lower() for d in provided_raw}
    else:
        provided = {d.strip().lower() for d in str(provided_raw).split(",") if d.strip()}

    required = {"passport", "payslip"}
    missing = required - provided

    return jsonify({
        "status": "checked",
        "documents_provided": sorted(provided),
        "documents_required": sorted(required),
        "missing_documents": sorted(missing),
        "complete": len(missing) == 0,
    })


@app.route("/compliance/calculate-score", methods=["POST"])
def calculate_compliance_score():
    """Calculate a compliance score (0-100) based on findings."""
    data = request.get_json(silent=True) or {}
    findings = data.get("findings", "")
    if isinstance(findings, list):
        findings = " ".join(findings)
    findings_lower = findings.lower()

    score = 100

    # Deduct for violations
    if "violation" in findings_lower or "exceeds" in findings_lower:
        score -= 30
    if "missing" in findings_lower:
        score -= 20
    if "non-compliant" in findings_lower or "non compliant" in findings_lower:
        score -= 25
    if "fail" in findings_lower:
        score -= 15

    score = max(0, min(100, score))

    if score >= 80:
        verdict = "PASS"
    elif score >= 50:
        verdict = "REVIEW"
    else:
        verdict = "FAIL"

    return jsonify({
        "status": "scored",
        "compliance_score": score,
        "suggested_verdict": verdict,
    })


@app.route("/core-banking/disburse", methods=["POST"])
def disburse_loan():
    """Disburse an approved mortgage loan."""
    data = request.get_json(silent=True) or {}
    ref = "MORT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

    return jsonify({
        "status": "disbursed",
        "reference": ref,
        "loan_amount": data.get("loan_amount", 0),
        "disbursement_date": "2026-02-15",
        "first_payment_date": "2026-03-15",
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "bank-systems-stub"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6000)
