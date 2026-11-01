"""
Generates a realistic mock Indian hospital discharge summary PDF.
Run once: python mock/generate_discharge_pdf.py
"""

from fpdf import FPDF
from pathlib import Path

OUTPUT = Path(__file__).parent / "discharge_summary.pdf"


class DischargePDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(0, 70, 127)
        self.cell(0, 8, "APOLLO HOSPITALS - HYDERABAD", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(80, 80, 80)
        self.cell(0, 5, "Jubilee Hills, Hyderabad - 500033 | Ph: 040-23607777 | NABH Accredited", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 70, 127)
        self.set_line_width(0.5)
        self.line(10, self.get_y() + 1, 200, self.get_y() + 1)
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(130, 130, 130)
        self.cell(0, 5, "CONFIDENTIAL - For patient and treating physician use only | Page 1 of 1", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(230, 240, 255)
        self.set_text_color(0, 50, 100)
        self.cell(0, 7, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def kv(self, label, value, col_w=55):
        self.set_font("Helvetica", "B", 9)
        self.cell(col_w, 6, label + ":", new_x="RIGHT", new_y="LAST")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    def kv2(self, pairs):
        """Two key-value pairs side by side."""
        self.set_font("Helvetica", "B", 9)
        self.cell(38, 6, pairs[0][0] + ":", new_x="RIGHT", new_y="LAST")
        self.set_font("Helvetica", "", 9)
        self.cell(57, 6, pairs[0][1], new_x="RIGHT", new_y="LAST")
        self.set_font("Helvetica", "B", 9)
        self.cell(38, 6, pairs[1][0] + ":", new_x="RIGHT", new_y="LAST")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, pairs[1][1], new_x="LMARGIN", new_y="NEXT")

    def body_text(self, text):
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def table_header(self, cols, widths):
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(210, 225, 245)
        for col, w in zip(cols, widths):
            self.cell(w, 7, col, border=1, fill=True, new_x="RIGHT", new_y="LAST")
        self.ln()

    def table_row(self, values, widths, fill=False):
        self.set_font("Helvetica", "", 8.5)
        self.set_fill_color(245, 249, 255)
        for val, w in zip(values, widths):
            self.cell(w, 6, val, border=1, fill=fill, new_x="RIGHT", new_y="LAST")
        self.ln()


def build():
    pdf = DischargePDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(10, 15, 10)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── DISCHARGE SUMMARY TITLE ──────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(180, 0, 0)
    pdf.cell(0, 7, "DISCHARGE SUMMARY", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)

    # ── PATIENT DETAILS ──────────────────────────────────────────────────
    pdf.section_title("PATIENT INFORMATION")
    pdf.kv2([("Patient Name", "Ramaiah Venkatesh"), ("Patient ID", "APH-2024-087432")])
    pdf.kv2([("Age / Gender", "62 Years / Male"), ("Blood Group", "B+")])
    pdf.kv2([("Address", "Vill. Kondapur, Dist. Nalgonda, Telangana"), ("Contact", "+91-98490-33214")])
    pdf.kv2([("Date of Admission", "18-Oct-2024"), ("Date of Discharge", "25-Oct-2024")])
    pdf.kv2([("Ward / Bed", "General Medicine - Bed 14B"), ("UHID", "UH-TG-204839")])
    pdf.kv("Preferred Language", "Telugu")
    pdf.ln(2)

    # ── DIAGNOSIS ────────────────────────────────────────────────────────
    pdf.section_title("FINAL DIAGNOSIS")
    diagnoses = [
        "1. Type 2 Diabetes Mellitus - Uncontrolled (HbA1c: 9.8%)",
        "2. Hypertension Stage II (BP at admission: 168/102 mmHg)",
        "3. Diabetic Nephropathy - Stage 3 CKD (eGFR: 42 mL/min/1.73m²)",
        "4. Lower Respiratory Tract Infection (LRTI) - Resolved",
    ]
    for d in diagnoses:
        pdf.body_text(d)

    # ── HISTORY & TREATMENT ──────────────────────────────────────────────
    pdf.section_title("CLINICAL SUMMARY")
    pdf.body_text(
        "Mr. Ramaiah Venkatesh, a 62-year-old male farmer from Nalgonda district, "
        "presented to the Emergency Department on 18-Oct-2024 with complaints of "
        "progressive breathlessness (Grade III), productive cough with yellow sputum, "
        "pedal oedema, and blood glucose of 380 mg/dL. He is a known diabetic and "
        "hypertensive for 8 years on irregular medication.\n\n"
        "During hospitalisation, patient was started on IV antibiotics (Injection "
        "Ceftriaxone 1g BD x 5 days), subcutaneous insulin (Actrapid sliding scale), "
        "IV Furosemide for oedema, and antihypertensives were optimised. Blood glucose "
        "was brought under control (FBS 118 mg/dL at discharge). Chest X-ray on "
        "25-Oct showed significant clearing of bilateral infiltrates. "
        "Pedal oedema reduced to trace levels. Patient is stable at discharge."
    )

    # ── MEDICATIONS ─────────────────────────────────────────────────────
    pdf.section_title("DISCHARGE MEDICATIONS")
    cols = ["#", "Drug Name", "Dose", "Frequency", "Duration", "Instructions"]
    widths = [8, 52, 22, 30, 22, 56]
    pdf.table_header(cols, widths)
    meds = [
        ["1", "Tab. Metformin 500mg", "500 mg", "Twice daily", "Ongoing", "After meals. Do not skip."],
        ["2", "Tab. Glimepiride 2mg", "2 mg", "Once daily", "Ongoing", "Before breakfast"],
        ["3", "Tab. Amlodipine 5mg", "5 mg", "Once daily", "Ongoing", "Morning with water"],
        ["4", "Tab. Telmisartan 40mg", "40 mg", "Once daily", "Ongoing", "Morning - monitor BP weekly"],
        ["5", "Tab. Furosemide 40mg", "40 mg", "Once daily", "14 days", "Morning. Monitor for dizziness."],
        ["6", "Tab. Azithromycin 500mg", "500 mg", "Once daily", "3 days", "Complete the full course"],
        ["7", "Tab. Calcium + Vit D3", "500mg/400IU", "Twice daily", "3 months", "After lunch and dinner"],
    ]
    for i, row in enumerate(meds):
        pdf.table_row(row, widths, fill=(i % 2 == 0))
    pdf.ln(3)

    # ── LAB RESULTS ─────────────────────────────────────────────────────
    pdf.section_title("KEY INVESTIGATIONS AT DISCHARGE")
    cols2 = ["Test", "Value", "Normal Range", "Status"]
    widths2 = [55, 35, 50, 50]
    pdf.table_header(cols2, widths2)
    labs = [
        ["Fasting Blood Sugar (FBS)", "118 mg/dL", "70-100 mg/dL", "Slightly elevated - improving"],
        ["HbA1c", "9.8%", "< 7.0%", "High - needs close monitoring"],
        ["Serum Creatinine", "1.8 mg/dL", "0.7-1.2 mg/dL", "Elevated - CKD Stage 3"],
        ["eGFR", "42 mL/min/1.73m²", "> 60", "Reduced - monitor closely"],
        ["Haemoglobin", "11.2 g/dL", "13-17 g/dL", "Mild anaemia"],
        ["Blood Pressure", "132/84 mmHg", "< 130/80 mmHg", "Improved - continue meds"],
        ["SpO2", "97% (Room Air)", "95-100%", "Normal"],
    ]
    for i, row in enumerate(labs):
        pdf.table_row(row, widths2, fill=(i % 2 == 0))
    pdf.ln(3)

    # ── FOLLOW-UP ────────────────────────────────────────────────────────
    pdf.section_title("FOLLOW-UP & INSTRUCTIONS")
    pdf.body_text(
        "FOLLOW-UP APPOINTMENTS:\n"
        "  - General Medicine OPD: Dr. Suresh Reddy - 08-Nov-2024 (10:00 AM)\n"
        "  - Nephrology OPD: Dr. Priya Rao - 15-Nov-2024 (11:30 AM)\n\n"
        "DIET INSTRUCTIONS:\n"
        "  - Strictly low-salt diet (< 2g sodium/day). Avoid pickles, papad, processed foods.\n"
        "  - Diabetic diet: Small frequent meals. Avoid rice in excess. Prefer ragi, millets.\n"
        "  - Fluid intake: 1.5 litres/day (do NOT exceed - kidney function reduced).\n\n"
        "RED FLAG SYMPTOMS - RETURN TO EMERGENCY IMMEDIATELY IF:\n"
        "  - Breathlessness worsens or you cannot lie flat\n"
        "  - Swelling of legs increases significantly\n"
        "  - Blood sugar reading below 70 mg/dL (hypoglycaemia) - sweating, confusion\n"
        "  - Blood pressure above 180/110 mmHg\n"
        "  - Chest pain or palpitations\n\n"
        "HOME MONITORING:\n"
        "  - Check blood sugar every morning before breakfast. Record in diary.\n"
        "  - Check BP every 2 days. Target: below 130/80 mmHg.\n"
        "  - Weigh yourself daily. If weight increases > 1 kg overnight, contact doctor."
    )

    # ── DOCTOR SIGN-OFF ──────────────────────────────────────────────────
    pdf.section_title("TREATING TEAM")
    pdf.kv2([("Consultant", "Dr. Suresh Reddy MD (General Medicine)"), ("Reg. No.", "TS-MCI-14892")])
    pdf.kv2([("Resident", "Dr. Anjali Sharma MBBS"), ("Date of Discharge", "25-Oct-2024")])
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 5, "Electronically signed. Physical signature on file at hospital records.", align="C")

    pdf.output(str(OUTPUT))
    print(f"PDF created: {OUTPUT}")


if __name__ == "__main__":
    build()
