import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

PDF_OUTPUT_DIR = os.environ.get('PDF_OUTPUT_DIR', '/tmp/recursant/pdfs')


class PDFGeneratorError(Exception):
    pass


class PDFGenerator:

    @staticmethod
    def generate_annex_iv_pdf(doc):
        os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)

        html = PDFGenerator._render_annex_iv_html(doc)

        filename = f"annex_iv_{doc.agent_id}_v{doc.version}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join(PDF_OUTPUT_DIR, filename)

        try:
            from weasyprint import HTML
            HTML(string=html).write_pdf(filepath)
        except ImportError:
            logger.warning("weasyprint not installed, generating HTML fallback")
            filepath = filepath.replace('.pdf', '.html')
            with open(filepath, 'w') as f:
                f.write(html)
        except Exception as e:
            raise PDFGeneratorError(f"PDF generation failed: {e}")

        logger.info(f"Generated PDF: {filepath}")
        return filepath

    @staticmethod
    def _render_annex_iv_html(doc):
        data = doc.document_data or {}
        manual = doc.manual_sections or {}

        s1 = data.get('section_1_general_description', {})
        s2a = data.get('section_2a_development', {})
        s2c = data.get('section_2c_validation_testing', {})
        s3a = data.get('section_3a_accuracy', {})
        s3b = data.get('section_3b_known_risks', {})
        s3c = data.get('section_3c_human_oversight', {})
        s5 = data.get('section_5_risk_management', {})
        s6 = data.get('section_6_lifecycle', {})
        s9 = data.get('section_9_post_market', {})

        def _manual(key):
            return manual.get(key, {}).get('content', '<em>Not provided</em>')

        capabilities_html = ''
        for cap in s1.get('capabilities', []):
            capabilities_html += f"<li><strong>{cap.get('name', '')}</strong>: {cap.get('description', '')}</li>\n"

        scans_html = ''
        for scan in s2c.get('security_scans', []):
            status = 'PASS' if scan.get('all_blocking_passed') else 'FAIL'
            scans_html += (
                f"<tr><td>{scan.get('id', '')[:8]}</td>"
                f"<td>{status}</td>"
                f"<td>{scan.get('passed_tests', 0)}/{scan.get('total_tests', 0)}</td>"
                f"<td>{scan.get('created_at', '')}</td></tr>\n"
            )

        evals_html = ''
        for ev in s2c.get('evaluations', []):
            score = ev.get('weighted_score', 'N/A')
            evals_html += (
                f"<tr><td>{ev.get('id', '')[:8]}</td>"
                f"<td>{score}</td>"
                f"<td>{'PASS' if ev.get('all_blocking_passed') else 'FAIL'}</td>"
                f"<td>{ev.get('created_at', '')}</td></tr>\n"
            )

        risks_html = ''
        for risk in s3b.get('failed_security_tests', []):
            risks_html += (
                f"<tr><td>{risk.get('test_case_name', '')}</td>"
                f"<td>{risk.get('category', '')}</td>"
                f"<td>{risk.get('severity', '')}</td></tr>\n"
            )

        guardrails_html = ''
        for g in s3c.get('guardrail_assignments', []):
            guardrails_html += (
                f"<tr><td>{g.get('guardrail_id', '')[:8]}</td>"
                f"<td>{g.get('scope', '')}</td>"
                f"<td>{g.get('enforcement_mode', '')}</td></tr>\n"
            )

        audit_html = ''
        for a in s6.get('audit_trail', [])[:20]:
            audit_html += (
                f"<tr><td>{a.get('action', '')}</td>"
                f"<td>{a.get('performed_by', '')}</td>"
                f"<td>{a.get('created_at', '')}</td></tr>\n"
            )

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Annex IV Technical Documentation - {s1.get('agent_name', 'Agent')}</title>
<style>
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; margin: 40px; color: #333; line-height: 1.6; }}
    h1 {{ color: #0A0F1C; border-bottom: 3px solid #14B8A6; padding-bottom: 10px; }}
    h2 {{ color: #0F9690; margin-top: 30px; border-bottom: 1px solid #E8F4F2; padding-bottom: 5px; }}
    h3 {{ color: #0A0F1C; }}
    table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 0.9em; }}
    th {{ background-color: #0A0F1C; color: white; }}
    .cover {{ text-align: center; margin: 100px 0; page-break-after: always; }}
    .cover h1 {{ font-size: 2.5em; border: none; }}
    .cover .meta {{ color: #666; font-size: 1.1em; margin: 10px 0; }}
    .risk-badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; color: white; font-weight: bold; }}
    .risk-high {{ background-color: #ef4444; }}
    .risk-limited {{ background-color: #f59e0b; }}
    .risk-minimal {{ background-color: #22c55e; }}
    .risk-unacceptable {{ background-color: #991b1b; }}
    .section {{ page-break-inside: avoid; }}
    .signature {{ margin-top: 40px; padding: 20px; background: #f8f9fa; border: 1px solid #ddd; }}
</style>
</head>
<body>

<div class="cover">
    <h1>EU AI Act - Annex IV<br>Technical Documentation</h1>
    <p class="meta"><strong>{s1.get('agent_name', 'Agent')}</strong> v{s1.get('agent_version', '1.0.0')}</p>
    <p class="meta">
        Risk Category: <span class="risk-badge risk-{s1.get('eu_risk_category', 'minimal')}">{(s1.get('eu_risk_category', 'N/A') or 'N/A').upper()}</span>
    </p>
    <p class="meta">Document Version: {doc.version}</p>
    <p class="meta">Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
    <p class="meta">Status: {doc.status.value.upper()}</p>
</div>

<h1>Table of Contents</h1>
<ol>
    <li>General Description</li>
    <li>Development and Design
        <ol type="a">
            <li>Development Methodology</li>
            <li>Data Requirements</li>
            <li>Validation and Testing</li>
        </ol>
    </li>
    <li>Performance and Safety
        <ol type="a">
            <li>Accuracy Metrics</li>
            <li>Known Risks</li>
            <li>Human Oversight</li>
            <li>Input Specifications</li>
        </ol>
    </li>
    <li>Metrics Appropriateness</li>
    <li>Risk Management</li>
    <li>Lifecycle Changes</li>
    <li>Applied Standards</li>
    <li>Declaration of Conformity</li>
    <li>Post-Market Monitoring</li>
</ol>

<div class="section">
<h2>1. General Description</h2>
<p><strong>Name:</strong> {s1.get('agent_name', 'N/A')}</p>
<p><strong>Version:</strong> {s1.get('agent_version', 'N/A')}</p>
<p><strong>Description:</strong> {s1.get('description', 'N/A')}</p>
<p><strong>Endpoint Type:</strong> {s1.get('endpoint_type', 'N/A')}</p>
<p><strong>Risk Tier:</strong> {s1.get('risk_tier', 'N/A')}</p>
<p><strong>Data Sensitivity:</strong> {s1.get('data_sensitivity', 'N/A')}</p>
<p><strong>EU AI Act Risk Category:</strong> {(s1.get('eu_risk_category', 'N/A') or 'N/A').upper()}</p>
<p><strong>Use Domain:</strong> {s1.get('use_domain', 'N/A')}</p>

<h3>Capabilities</h3>
<ul>{capabilities_html if capabilities_html else '<li>No capabilities defined</li>'}</ul>

<h3>Intended Purpose (Manual)</h3>
{_manual('section_1_intended_purpose')}
</div>

<div class="section">
<h2>2a. Development Methodology</h2>
<p><strong>Version History:</strong> {len(s2a.get('version_history', []))} versions recorded</p>
{_manual('section_2a_methodology')}
</div>

<div class="section">
<h2>2b. Data Requirements</h2>
{_manual('section_2b_data')}
</div>

<div class="section">
<h2>2c. Validation and Testing</h2>
<h3>Security Scans</h3>
<table>
<tr><th>Scan ID</th><th>Result</th><th>Tests</th><th>Date</th></tr>
{scans_html if scans_html else '<tr><td colspan="4">No security scans recorded</td></tr>'}
</table>

<h3>Evaluations</h3>
<table>
<tr><th>Eval ID</th><th>Score</th><th>Result</th><th>Date</th></tr>
{evals_html if evals_html else '<tr><td colspan="4">No evaluations recorded</td></tr>'}
</table>
</div>

<div class="section">
<h2>3a. Accuracy Metrics</h2>
<p><strong>Evaluation Scores:</strong></p>
<table>
<tr><th>Eval ID</th><th>Weighted Score</th><th>Blocking Passed</th></tr>
{''.join(f"<tr><td>{e.get('id', '')[:8]}</td><td>{e.get('weighted_score', 'N/A')}</td><td>{'Yes' if e.get('all_blocking_passed') else 'No'}</td></tr>" for e in s3a.get('evaluation_scores', []))}
</table>
{_manual('section_3a_interpretation')}
</div>

<div class="section">
<h2>3b. Known Risks</h2>
<h3>Failed Security Tests</h3>
<table>
<tr><th>Test Case</th><th>Category</th><th>Severity</th></tr>
{risks_html if risks_html else '<tr><td colspan="3">No failed tests</td></tr>'}
</table>
{_manual('section_3b_mitigation')}
</div>

<div class="section">
<h2>3c. Human Oversight</h2>
<h3>Guardrail Assignments</h3>
<table>
<tr><th>Guardrail</th><th>Scope</th><th>Enforcement</th></tr>
{guardrails_html if guardrails_html else '<tr><td colspan="3">No guardrails assigned</td></tr>'}
</table>
{_manual('section_3c_procedures')}
</div>

<div class="section">
<h2>3d. Input Specifications</h2>
<p><strong>Capability Schemas:</strong> {len(s1.get('capabilities', []))} capabilities with schema definitions</p>
{_manual('section_3d_additional')}
</div>

<div class="section">
<h2>4. Metrics Appropriateness</h2>
{_manual('section_4_justification')}
</div>

<div class="section">
<h2>5. Risk Management</h2>
<p><strong>Internal Risk Tier:</strong> {s5.get('risk_tier', 'N/A')}</p>
<p><strong>Data Sensitivity:</strong> {s5.get('data_sensitivity', 'N/A')}</p>
<p><strong>Classification:</strong> {s5.get('classification', 'N/A')}</p>
{_manual('section_5_narrative')}
</div>

<div class="section">
<h2>6. Lifecycle Changes</h2>
<p><strong>Total Versions:</strong> {s6.get('version_count', 0)}</p>
<h3>Audit Trail (Recent)</h3>
<table>
<tr><th>Action</th><th>Performed By</th><th>Date</th></tr>
{audit_html if audit_html else '<tr><td colspan="3">No audit entries</td></tr>'}
</table>
</div>

<div class="section">
<h2>7. Applied Standards</h2>
{_manual('section_7_standards')}
</div>

<div class="section">
<h2>8. Declaration of Conformity</h2>
{_manual('section_8_declaration')}
</div>

<div class="section">
<h2>9. Post-Market Monitoring</h2>
<p><strong>Total Guardrail Events:</strong> {s9.get('guardrail_events_total', 0)}</p>
<p><strong>Adversarial Test Runs:</strong> {s9.get('adversarial_test_count', 0)}</p>
{_manual('section_9_narrative')}
</div>

<div class="signature">
<p><strong>Document Signature:</strong> {doc.signature or 'Unsigned'}</p>
<p><strong>Algorithm:</strong> {doc.signature_algorithm or 'N/A'}</p>
{'<p><strong>Approved By:</strong> ' + (doc.approved_by or '') + '</p>' if doc.approved_by else ''}
{'<p><strong>Approved At:</strong> ' + (doc.approved_at.strftime('%Y-%m-%d %H:%M UTC') if doc.approved_at else '') + '</p>' if doc.approved_at else ''}
</div>

</body>
</html>"""

        return html
