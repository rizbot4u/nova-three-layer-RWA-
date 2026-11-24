import os
from datetime import datetime, timezone
from fpdf import FPDF


def generate_pdf_report(report_id: str, report_type: str, data: dict,
                        output_dir: str = "./reports") -> str:
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, f"{report_id}.pdf")

    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "NOVA TOKENISATION CORE", ln=1, align="C")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "REGULATORY AUDIT REPORT", ln=1, align="C")
    pdf.ln(5)

    # Metadata
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Report ID: {report_id}", ln=1)
    pdf.cell(0, 6, f"Type: {report_type}", ln=1)
    pdf.cell(0, 6, f"Generated: {datetime.now(timezone.utc).isoformat()}", ln=1)
    pdf.cell(0, 6, "Standard: FCA DSS / MiCA / VARA aligned", ln=1)
    pdf.ln(5)

    # Metrics
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Summary Metrics:", ln=1)
    pdf.set_font("Helvetica", "", 10)

    for k, v in data.items():
        # Safe: cast everything to str, strip non-latin-1 chars
        safe_key = str(k).encode("latin-1", "replace").decode("latin-1")
        safe_val = str(v).encode("latin-1", "replace").decode("latin-1")
        pdf.cell(0, 6, f"- {safe_key}: {safe_val}", ln=1)

    pdf.output(pdf_path)
    return pdf_path
