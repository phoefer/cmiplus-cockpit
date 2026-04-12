"""
CMIplus Intelligence Cockpit - Weekly PDF Report Generator
Reads briefing.json + flagship-analyses.json and produces a PDF
Output: reports/weekly/CMIplus_Intelligence_YYYY-MM-DD.pdf
"""

import json, os, datetime, textwrap
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

# ── Colors ────────────────────────────────────────────────────────────────────
NAVY      = colors.HexColor("#0a1f3d")
RBI_RED   = colors.HexColor("#c8102e")
GOLD      = colors.HexColor("#9a6f28")
URGENT    = colors.HexColor("#c8102e")
WATCH     = colors.HexColor("#b86000")
FYI       = colors.HexColor("#1a7a48")
LIGHT_BG  = colors.HexColor("#f4f5f7")
BORDER    = colors.HexColor("#dde1e7")
TEXT      = colors.HexColor("#1a1d23")
MUTED     = colors.HexColor("#8a909e")
WHITE     = colors.white

W, H = A4
MARGIN = 18*mm

# ── Styles ────────────────────────────────────────────────────────────────────
def make_styles():
    s = getSampleStyleSheet()
    def add(name, **kw):
        s.add(ParagraphStyle(name=name, **kw))

    add('Cover_Title',  fontSize=28, textColor=WHITE,     fontName='Helvetica-Bold',
        leading=34, spaceAfter=6, alignment=TA_LEFT)
    add('Cover_Sub',    fontSize=14, textColor=colors.HexColor("#a0b8d8"),
        fontName='Helvetica', leading=18, spaceAfter=4, alignment=TA_LEFT)
    add('Cover_Date',   fontSize=11, textColor=colors.HexColor("#7090b0"),
        fontName='Helvetica', leading=14, alignment=TA_LEFT)
    add('Sec_Head',     fontSize=16, textColor=NAVY, fontName='Helvetica-Bold',
        leading=20, spaceBefore=14, spaceAfter=6)
    add('CK_Sub_Head',     fontSize=12, textColor=NAVY, fontName='Helvetica-Bold',
        leading=15, spaceBefore=8, spaceAfter=4)
    add('Item_Title',   fontSize=11, textColor=TEXT, fontName='Helvetica-Bold',
        leading=14, spaceAfter=2)
    add('CK_Body',         fontSize=9,  textColor=TEXT, fontName='Helvetica',
        leading=13, spaceAfter=4, alignment=TA_JUSTIFY)
    add('Body_Small',   fontSize=8,  textColor=MUTED, fontName='Helvetica',
        leading=11, spaceAfter=2)
    add('CK_Bullet',       fontSize=9,  textColor=TEXT, fontName='Helvetica',
        leading=13, leftIndent=10, spaceAfter=2,
        bulletIndent=2, bulletFontName='Helvetica')
    add('RBI_Label',    fontSize=7,  textColor=GOLD, fontName='Helvetica-Bold',
        leading=10, spaceAfter=2, spaceBefore=4,
        textTransform='uppercase', letterSpacing=0.5)
    add('RBI_Text',     fontSize=9,  textColor=colors.HexColor("#5a4010"),
        fontName='Helvetica', leading=13, spaceAfter=4, alignment=TA_JUSTIFY)
    add('Exec_Text',    fontSize=10, textColor=WHITE, fontName='Helvetica',
        leading=15, spaceAfter=0, alignment=TA_JUSTIFY)
    add('Reg_Deadline', fontSize=8,  textColor=URGENT, fontName='Helvetica-Bold',
        leading=10, spaceAfter=2)
    add('Reg_Area',     fontSize=7,  textColor=colors.HexColor("#0a5090"),
        fontName='Helvetica-Bold', leading=10, spaceAfter=2,
        textTransform='uppercase')
    add('Footer_Text',  fontSize=7,  textColor=MUTED, fontName='Helvetica',
        leading=9, alignment=TA_CENTER)
    add('Quote_Text',   fontSize=9,  textColor=NAVY, fontName='Helvetica-Oblique',
        leading=13, leftIndent=8, spaceAfter=2)
    add('Quote_Attr',   fontSize=7,  textColor=MUTED, fontName='Helvetica',
        leading=10, leftIndent=8, spaceAfter=4)
    return s

# ── Helpers ────────────────────────────────────────────────────────────────────
def rel_color(relevance):
    return {
        'urgent': URGENT,
        'watch':  WATCH,
        'fyi':    FYI,
    }.get(relevance, FYI)

def badge_table(relevance, source='', date='', rank=None):
    rel = relevance.upper() if relevance else 'FYI'
    col = rel_color(relevance)
    rank_str = f"#{rank:02d}" if rank else ''
    meta = '  |  '.join(filter(None, [source, date, rank_str]))
    data = [[
        Paragraph(f'<font color="white"><b> {rel} </b></font>',
                  ParagraphStyle('bt', fontSize=7, fontName='Helvetica-Bold',
                                 leading=9, alignment=TA_CENTER)),
        Paragraph(f'<font color="#8a909e">{meta}</font>',
                  ParagraphStyle('bm', fontSize=7, fontName='Helvetica',
                                 leading=9)),
    ]]
    t = Table(data, colWidths=[30*mm, None])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(0,0), col),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0),(-1,-1), 2),
        ('BOTTOMPADDING', (0,0),(-1,-1), 2),
        ('LEFTPADDING', (0,0),(0,0), 3),
        ('RIGHTPADDING', (0,0),(0,0), 3),
        ('LEFTPADDING', (1,0),(1,0), 6),
    ]))
    return t

def stripe_box(content_elems, color=NAVY, width=3):
    """Wrap elements in a left-stripe box."""
    inner_w = W - 2*MARGIN - width*mm - 4*mm
    data = [[Table([[e] for e in content_elems],
                   colWidths=[inner_w])]]
    t = Table(data, colWidths=[width*mm + 4*mm + inner_w])
    t.setStyle(TableStyle([
        ('LINEAFTER',   (0,0),(0,-1), 0.1, colors.white),
        ('LINEBEFORE',  (0,0),(0,-1), width, color),
        ('LEFTPADDING', (0,0),(-1,-1), width*mm + 4),
        ('RIGHTPADDING',(0,0),(-1,-1), 0),
        ('TOPPADDING',  (0,0),(-1,-1), 3),
        ('BOTTOMPADDING',(0,0),(-1,-1), 3),
        ('BACKGROUND',  (0,0),(-1,-1), colors.HexColor("#f8f9fa")),
    ]))
    return t

def header_band(title, subtitle='', bg=NAVY):
    data = [[
        Paragraph(f'<font color="white"><b>{title}</b></font>',
                  ParagraphStyle('hb', fontSize=13, fontName='Helvetica-Bold',
                                 leading=16, textColor=WHITE)),
        Paragraph(f'<font color="#7090b0">{subtitle}</font>',
                  ParagraphStyle('hs', fontSize=9, fontName='Helvetica',
                                 leading=12, textColor=MUTED, alignment=TA_RIGHT)),
    ]]
    t = Table(data, colWidths=[120*mm, None])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), bg),
        ('TOPPADDING', (0,0),(-1,-1), 8),
        ('BOTTOMPADDING', (0,0),(-1,-1), 8),
        ('LEFTPADDING', (0,0),(0,0), 10),
        ('RIGHTPADDING', (-1,0),(-1,0), 10),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
    ]))
    return t

def kpi_row(items):
    """items = [(label, value, color), ...]"""
    cells = []
    for label, value, col in items:
        cells.append(Table([[
            Paragraph(f'<font color="{col.hexval()}" size="22"><b>{value}</b></font>',
                      ParagraphStyle('kv', fontSize=22, fontName='Helvetica-Bold',
                                     leading=26, alignment=TA_CENTER)),
            Paragraph(f'<font color="#8a909e">{label}</font>',
                      ParagraphStyle('kl', fontSize=8, fontName='Helvetica',
                                     leading=10, alignment=TA_CENTER)),
        ]], colWidths=[(W-2*MARGIN)/len(items)],
           style=[('TOPPADDING',(0,0),(-1,-1),8),
                  ('BOTTOMPADDING',(0,0),(-1,-1),8),
                  ('BACKGROUND',(0,0),(-1,-1),colors.white),
                  ('BOX',(0,0),(-1,-1),0.5,BORDER),
                  ('ALIGN',(0,0),(-1,-1),'CENTER')]))
        cells.append(None)
    # Remove last None
    if cells and cells[-1] is None:
        cells = cells[:-1]
    col_widths = []
    n = len(items)
    kpi_w = (W-2*MARGIN) / n - 2*mm
    for i in range(n):
        col_widths.append(kpi_w)
        if i < n-1:
            col_widths.append(2*mm)
    actual_cells = [c for c in cells if c is not None]
    spacers = [Spacer(2*mm, 1) for _ in range(n-1)]
    row_data = []
    for i, cell in enumerate(actual_cells):
        row_data.append(cell)
        if i < n-1:
            row_data.append(Spacer(1,1))
    t = Table([row_data], colWidths=[kpi_w if i%2==0 else 2*mm for i in range(2*n-1)])
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
    return t

# ── Page numbering ─────────────────────────────────────────────────────────────
def on_page(canvas, doc, scan_date):
    canvas.saveState()
    # Footer line
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 14*mm, W-MARGIN, 14*mm)
    # Footer text
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 10*mm, f"CMIplus Intelligence Cockpit | Raiffeisen Bank International")
    canvas.drawString(MARGIN, 7*mm, f"Week of {scan_date} | CONFIDENTIAL - INTERNAL USE ONLY")
    canvas.drawRightString(W-MARGIN, 8.5*mm, f"Page {doc.page}")
    # Header line (not on first page)
    if doc.page > 1:
        canvas.setStrokeColor(RBI_RED)
        canvas.setLineWidth(1.5)
        canvas.line(MARGIN, H-12*mm, MARGIN+8*mm, H-12*mm)
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN+9*mm, H-12*mm, W-MARGIN, H-12*mm)
    canvas.restoreState()

# ── Cover page ─────────────────────────────────────────────────────────────────
def build_cover(briefing, styles):
    elems = []
    scan_date = briefing.get('scan_date', datetime.date.today().isoformat())
    week_label = briefing.get('week_label', f"Week of {scan_date}")
    m = briefing.get('market', [])
    t = briefing.get('thought', [])
    c = briefing.get('competitors', [])
    r = briefing.get('regulatory', [])
    all_items = m + t + c + r
    n_urgent = sum(1 for i in all_items if i.get('relevance')=='urgent')
    n_watch  = sum(1 for i in all_items if i.get('relevance')=='watch')

    # Navy cover band
    cover_data = [[
        Table([
            [Paragraph("CMIplus Intelligence Cockpit", styles['Cover_Title'])],
            [Paragraph("Cash Management Strategic Intelligence", styles['Cover_Sub'])],
            [Paragraph(week_label, styles['Cover_Date'])],
            [Spacer(1, 8*mm)],
            [Paragraph("Raiffeisen Bank International AG", styles['Cover_Date'])],
            [Paragraph("Group Product — Cash Management", styles['Cover_Date'])],
        ], colWidths=[W-2*MARGIN])
    ]]
    cover = Table(cover_data, colWidths=[W-2*MARGIN])
    cover.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), NAVY),
        ('TOPPADDING', (0,0),(-1,-1), 22*mm),
        ('BOTTOMPADDING', (0,0),(-1,-1), 22*mm),
        ('LEFTPADDING', (0,0),(-1,-1), 14*mm),
        ('RIGHTPADDING', (0,0),(-1,-1), 14*mm),
    ]))
    elems.append(cover)
    elems.append(Spacer(1, 8*mm))

    # KPI row
    kpi_data = [
        ("Market Items",  str(len(m)),  NAVY),
        ("Thought",       str(len(t)),  colors.HexColor("#1a5090")),
        ("Competitors",   str(len(c)),  colors.HexColor("#0a3060")),
        ("Regulatory",    str(len(r)),  colors.HexColor("#1a7a48")),
        ("Urgent",        str(n_urgent),URGENT),
        ("Watch",         str(n_watch), WATCH),
    ]
    col_w = (W - 2*MARGIN - 5*mm) / 6
    cells = []
    for label, value, col in kpi_data:
        cells.append(Table([
            [Paragraph(f'<font color="{col.hexval()}"><b>{value}</b></font>',
                       ParagraphStyle('kv2', fontSize=20, fontName='Helvetica-Bold',
                                      leading=24, alignment=TA_CENTER))],
            [Paragraph(label, ParagraphStyle('kl2', fontSize=7, fontName='Helvetica',
                                              leading=9, alignment=TA_CENTER,
                                              textColor=MUTED))],
        ], colWidths=[col_w-1*mm],
           style=[('TOPPADDING',(0,0),(-1,-1),6),
                  ('BOTTOMPADDING',(0,0),(-1,-1),6),
                  ('BACKGROUND',(0,0),(-1,-1),colors.white),
                  ('BOX',(0,0),(-1,-1),0.5,BORDER)]))

    kpi_t = Table([cells], colWidths=[col_w]*6)
    kpi_t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
                                ('LEFTPADDING',(0,0),(-1,-1),0),
                                ('RIGHTPADDING',(0,0),(-1,-1),1*mm)]))
    elems.append(kpi_t)
    elems.append(Spacer(1, 6*mm))

    # Executive summary box
    exec_summary = briefing.get('executive_summary', '')
    exec_data = [[
        Paragraph("EXECUTIVE SUMMARY",
                  ParagraphStyle('el', fontSize=8, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor("#7090b0"),
                                 leading=10, spaceAfter=6,
                                 letterSpacing=1)),
        Paragraph(exec_summary, styles['Exec_Text']),
    ]]
    exec_box = Table([[Table(exec_data, colWidths=[W-2*MARGIN-28*mm])]],
                     colWidths=[W-2*MARGIN])
    exec_box.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), NAVY),
        ('TOPPADDING', (0,0),(-1,-1), 12),
        ('BOTTOMPADDING', (0,0),(-1,-1), 12),
        ('LEFTPADDING', (0,0),(-1,-1), 14),
        ('RIGHTPADDING', (0,0),(-1,-1), 14),
    ]))
    elems.append(exec_box)
    elems.append(Spacer(1, 6*mm))

    # Table of contents
    toc_rows = [
        [Paragraph("<b>Section</b>", ParagraphStyle('th', fontSize=9, fontName='Helvetica-Bold',
                                                     textColor=NAVY, leading=12)),
         Paragraph("<b>Items</b>", ParagraphStyle('th2', fontSize=9, fontName='Helvetica-Bold',
                                                   textColor=NAVY, leading=12, alignment=TA_RIGHT))],
        [Paragraph("Market Intelligence", styles['CK_Body']),   Paragraph(str(len(m)), ParagraphStyle('n', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT))],
        [Paragraph("Thought Leadership",  styles['CK_Body']),   Paragraph(str(len(t)), ParagraphStyle('n', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT))],
        [Paragraph("Competitor Monitor",  styles['CK_Body']),   Paragraph(str(len(c)), ParagraphStyle('n', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT))],
        [Paragraph("Regulatory Radar",    styles['CK_Body']),   Paragraph(str(len(r)), ParagraphStyle('n', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT))],
        [Paragraph("Flagship Reports",    styles['CK_Body']),   Paragraph("4", ParagraphStyle('n', fontSize=9, fontName='Helvetica', alignment=TA_RIGHT))],
    ]
    toc = Table(toc_rows, colWidths=[W-2*MARGIN-20*mm, 20*mm])
    toc.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,0), colors.HexColor("#eef2f8")),
        ('LINEBELOW',  (0,0),(-1,0), 1, NAVY),
        ('LINEBELOW',  (0,1),(-1,-1), 0.3, BORDER),
        ('TOPPADDING', (0,0),(-1,-1), 5),
        ('BOTTOMPADDING', (0,0),(-1,-1), 5),
        ('LEFTPADDING', (0,0),(-1,-1), 8),
        ('RIGHTPADDING', (-1,0),(-1,-1), 8),
        ('ROWBACKGROUNDS', (0,1),(-1,-1), [colors.white, colors.HexColor("#fafbfc")]),
    ]))
    elems.append(Paragraph("Contents", styles['CK_Sub_Head']))
    elems.append(toc)
    elems.append(PageBreak())
    return elems

# ── Item renderer ──────────────────────────────────────────────────────────────
def render_item(item, styles, show_competitor=False):
    elems = []
    rel = item.get('relevance', 'fyi')
    col = rel_color(rel)
    title = item.get('title', '')
    source = item.get('source') or item.get('competitor', '')
    date_str = item.get('article_date') or item.get('date', '')
    rank = item.get('rank')
    summary = item.get('summary_detail') or item.get('summary_short', '')
    key_points = item.get('key_points', [])
    rbi = item.get('rbi_cash_management') or item.get('sowhat', '')
    deadline = item.get('deadline', '')
    reg_area = item.get('regulation_area', '')

    inner = []
    inner.append(badge_table(rel, source, date_str, rank))
    inner.append(Spacer(1, 3))
    inner.append(Paragraph(title, styles['Item_Title']))
    if reg_area:
        inner.append(Paragraph(reg_area, styles['Reg_Area']))
    if deadline and deadline != 'Ongoing':
        inner.append(Paragraph(f"Deadline: {deadline}", styles['Reg_Deadline']))
    inner.append(Paragraph(summary, styles['CK_Body']))
    if key_points:
        for kp in key_points[:3]:
            inner.append(Paragraph(f"&#x2192; {kp}", styles['CK_Bullet']))
    if rbi:
        inner.append(Paragraph("SO WHAT FOR RBI CASH MANAGEMENT", styles['RBI_Label']))
        inner.append(Paragraph(rbi, styles['RBI_Text']))

    elems.append(stripe_box(inner, color=col))
    elems.append(Spacer(1, 4*mm))
    return elems

# ── Section builder ────────────────────────────────────────────────────────────
def build_section(title, items, styles, icon='', show_competitor=False, limit=None):
    elems = []
    elems.append(header_band(f"{icon}  {title}", f"{len(items)} items"))
    elems.append(Spacer(1, 4*mm))
    shown = items[:limit] if limit else items
    for item in shown:
        elems.extend(render_item(item, styles, show_competitor))
    return elems

# ── Flagship summary ───────────────────────────────────────────────────────────
def build_flagship_section(analyses, styles):
    elems = []
    elems.append(header_band("Flagship Reports", "Deep analysis of key industry reports"))
    elems.append(Spacer(1, 4*mm))
    if not analyses:
        elems.append(Paragraph("No flagship analyses available. Run FORCE_FLAGSHIP=true to generate.", styles['CK_Body']))
        return elems

    for a in analyses:
        if a.get('error'):
            continue
        inner = []
        inner.append(Paragraph(
            f'<font color="#5a4010"><b>{a.get("report_title","")} {a.get("report_year","")}</b></font>',
            ParagraphStyle('ft', fontSize=11, fontName='Helvetica-Bold',
                           leading=14, spaceAfter=3)))
        exec_sum = a.get('executive_summary', '')
        if exec_sum:
            inner.append(Paragraph(exec_sum, styles['CK_Body']))

        # Key stats (max 4)
        stats = a.get('key_stats', [])[:4]
        if stats:
            inner.append(Paragraph("KEY STATISTICS", styles['RBI_Label']))
            for s in stats:
                txt = s if isinstance(s, str) else s.get('stat', str(s))
                inner.append(Paragraph(f"&#x2192; {txt}", styles['CK_Bullet']))

        # Key quotes (max 2)
        quotes = a.get('key_quotes', [])[:2]
        for q in quotes:
            txt  = q if isinstance(q, str) else q.get('text', '')
            attr = '' if isinstance(q, str) else q.get('attribution', '')
            if txt:
                inner.append(Paragraph(f'"{txt}"', styles['Quote_Text']))
                if attr:
                    inner.append(Paragraph(f"-- {attr}", styles['Quote_Attr']))

        # Top action
        actions = a.get('key_actions', [])
        if actions:
            top = actions[0]
            inner.append(Paragraph("TOP ACTION FOR CMIplus", styles['RBI_Label']))
            inner.append(Paragraph(
                f"[{top.get('urgency','?')}] {top.get('action','')}",
                styles['RBI_Text']))

        box = Table([[Table([[e] for e in inner],
                            colWidths=[W-2*MARGIN-6*mm])
                     ]], colWidths=[W-2*MARGIN])
        box.setStyle(TableStyle([
            ('BACKGROUND', (0,0),(-1,-1), colors.HexColor("#fdf8f0")),
            ('BOX', (0,0),(-1,-1), 1, colors.HexColor("#e8d8b0")),
            ('LINEBEFORE', (0,0),(0,-1), 4, GOLD),
            ('TOPPADDING', (0,0),(-1,-1), 10),
            ('BOTTOMPADDING', (0,0),(-1,-1), 10),
            ('LEFTPADDING', (0,0),(-1,-1), 12),
            ('RIGHTPADDING', (0,0),(-1,-1), 10),
        ]))
        elems.append(box)
        elems.append(Spacer(1, 4*mm))
    return elems

# ── Main ───────────────────────────────────────────────────────────────────────
def generate_pdf(briefing_path="briefing.json",
                 flagship_path="flagship-analyses.json",
                 output_dir="reports/weekly"):

    # Load data
    with open(briefing_path, encoding="utf-8") as f:
        briefing = json.load(f)
    analyses = []
    try:
        with open(flagship_path, encoding="utf-8") as f:
            analyses = json.load(f)
    except Exception:
        pass

    scan_date = briefing.get('scan_date', datetime.date.today().isoformat())

    # Output path
    os.makedirs(output_dir, exist_ok=True)
    filename = f"CMIplus_Intelligence_{scan_date}.pdf"
    out_path = os.path.join(output_dir, filename)

    styles = make_styles()

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=16*mm, bottomMargin=20*mm,
        title=f"CMIplus Intelligence Cockpit - {scan_date}",
        author="RBI Cash Management",
        subject="Weekly Intelligence Briefing",
    )

    story = []

    # 1. Cover
    story.extend(build_cover(briefing, styles))

    # 2. Market Intelligence
    market = briefing.get('market', [])
    if market:
        story.extend(build_section("Market Intelligence", market, styles, icon="○"))
        story.append(PageBreak())

    # 3. Thought Leadership
    thought = briefing.get('thought', [])
    if thought:
        story.extend(build_section("Thought Leadership", thought, styles, icon="△"))
        story.append(PageBreak())

    # 4. Regulatory Radar
    regulatory = briefing.get('regulatory', [])
    if regulatory:
        story.extend(build_section("Regulatory Radar", regulatory, styles, icon="!"))
        story.append(PageBreak())

    # 5. Competitor Monitor
    competitors = briefing.get('competitors', [])
    if competitors:
        story.extend(build_section("Competitor Monitor", competitors, styles,
                                   icon="◇", show_competitor=True))
        story.append(PageBreak())

    # 6. Flagship Reports
    story.extend(build_flagship_section(analyses, styles))

    # Build PDF
    doc.build(story,
              onFirstPage=lambda c,d: on_page(c,d,scan_date),
              onLaterPages=lambda c,d: on_page(c,d,scan_date))

    print(f"PDF generated: {out_path}")
    return out_path

if __name__ == "__main__":
    generate_pdf()
