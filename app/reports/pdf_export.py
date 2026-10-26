import io
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and draw total page numbers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            super().showPage()
        super().save()

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#718096"))
        footer_text = f"Page {self._pageNumber} of {page_count}  |  Smart Attendance Verification System"
        self.drawRightString(792 - 40, 25, footer_text)
        self.drawString(40, 25, "CONFIDENTIAL - Official Academic Attendance Record")
        self.restoreState()


def build_pdf_attendance_report(report_data):
    """
    Renders an institutional, print-ready PDF monthly attendance report in landscape orientation.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1B365D")
    )
    subtitle_style = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#4A5568")
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1B365D"),
        spaceAfter=6
    )
    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11
    )
    cell_bold_style = ParagraphStyle(
        "TableCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11
    )
    cell_danger = ParagraphStyle(
        "TableCellDanger",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#C53030")
    )

    elements = []

    # Title & Header
    elements.append(Paragraph("SMART ATTENDANCE SYSTEM - MONTHLY ACADEMIC REPORT", title_style))
    elements.append(Paragraph(
        f"Period: <b>{report_data['month_name']} {report_data['year']}</b> &nbsp;|&nbsp; "
        f"Generated: {report_data['generated_at'].strftime('%Y-%m-%d %H:%M UTC')}",
        subtitle_style
    ))
    elements.append(Spacer(1, 10))

    # Metadata summary banner table
    summary_data = [
        [
            Paragraph("<b>Subject:</b>", cell_bold_style),
            Paragraph(f"{report_data['subject'].subject_code} - {report_data['subject'].subject_name}", cell_style),
            Paragraph("<b>Total Sessions Held:</b>", cell_bold_style),
            Paragraph(str(report_data["total_sessions"]), cell_bold_style),
        ],
        [
            Paragraph("<b>Class / Section:</b>", cell_bold_style),
            Paragraph(report_data['class'].name, cell_style),
            Paragraph("<b>Total Enrolled Students:</b>", cell_bold_style),
            Paragraph(str(report_data["total_enrolled"]), cell_style),
        ],
        [
            Paragraph("<b>Faculty:</b>", cell_bold_style),
            Paragraph(f"Prof. {report_data['staff'].user.full_name} ({report_data['staff'].staff_id})", cell_style),
            Paragraph("<b>Class Attendance Average:</b>", cell_bold_style),
            Paragraph(f"<b>{report_data['class_average']}%</b>" if report_data['class_average'] is not None else "N/A", cell_bold_style),
        ],
        [
            Paragraph("<b>Eligibility Threshold:</b>", cell_bold_style),
            Paragraph(f"{report_data['threshold']:.0f}%", cell_style),
            Paragraph("<b>Below Threshold (<75%):</b>", cell_bold_style),
            Paragraph(f"<font color='#C53030'><b>{report_data['below_threshold_count']} students</b></font>", cell_style),
        ]
    ]

    summary_table = Table(summary_data, colWidths=[120, 240, 160, 200])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 14))

    # Student Attendance Table
    elements.append(Paragraph("STUDENT ATTENDANCE TABLE", section_heading))

    table_data = [[
        Paragraph("<b>Student ID</b>", cell_bold_style),
        Paragraph("<b>Full Name</b>", cell_bold_style),
        Paragraph("<b>Held</b>", cell_bold_style),
        Paragraph("<b>Present</b>", cell_bold_style),
        Paragraph("<b>Absent</b>", cell_bold_style),
        Paragraph("<b>Attendance %</b>", cell_bold_style),
        Paragraph("<b>Status</b>", cell_bold_style),
        Paragraph("<b>Additional Sessions Needed</b>", cell_bold_style),
    ]]

    for s in report_data["students"]:
        pct_style = cell_danger if s["is_low"] else cell_bold_style
        status_text = "<font color='#C53030'><b>LOW</b></font>" if s["is_low"] else "<font color='#22543D'><b>ELIGIBLE</b></font>"
        needed_text = str(s["sessions_needed"]) if s["is_low"] else "-"

        table_data.append([
            Paragraph(s["student_id"], cell_style),
            Paragraph(s["student_name"], cell_style),
            Paragraph(str(s["sessions_held"]), cell_style),
            Paragraph(str(s["present_count"]), cell_style),
            Paragraph(str(s["absent_count"]), cell_style),
            Paragraph(s["percentage_display"], pct_style),
            Paragraph(status_text, cell_style),
            Paragraph(needed_text, pct_style if s["is_low"] else cell_style),
        ])

    col_widths = [85, 175, 50, 50, 50, 85, 80, 145]
    records_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    records_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1B365D")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        ('TOPPADDING', (0, 0), (-1, 0), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0, 1), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(records_table)

    # Low attendance planning section
    if report_data["low_attendance_students"]:
        elements.append(Spacer(1, 14))
        elements.append(Paragraph("LOW ATTENDANCE WARNING & PLANNING ESTIMATES", section_heading))
        note_text = (
            "<i>Note: 'Additional Sessions Needed' indicates the minimum consecutive sessions the student must attend "
            "to reach the 75% threshold, assuming all subsequent sessions are held and attended. "
            "This is a planning estimate and does not guarantee eligibility if more sessions are added.</i>"
        )
        elements.append(Paragraph(note_text, subtitle_style))
        elements.append(Spacer(1, 6))

    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()
