"""Reference-led invoice presentation. No database access or accounting calculations.

Coordinates are points on a single A4 grid, measured from the top of the page.
Text remains selectable; the contours, mountains and page furniture are vectors.
The item table uses ReportLab's measured row splitting, including oversized cells.
"""
from __future__ import annotations

import base64
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from math import cos, sin
from random import Random
import re
from xml.sax.saxutils import escape

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle

PAGE_W, PAGE_H = A4
MARGIN = 20
WIDTH = PAGE_W - 2 * MARGIN
GAP = 11
BOTTOM = PAGE_H - 43

PALETTES = {
    "blue_classic": dict(primary="#074D82", accent="#03B6DA", pale="#EFF8FD", line="#C6DFEC", ink="#092556"),
    "blue_topographic": dict(primary="#103F5B", accent="#03ACC2", pale="#F1F7FA", line="#CDDFE7", ink="#082C44"),
    "green_gold_premium": dict(primary="#004C43", accent="#BD922C", pale="#EFF6F3", line="#C4DCD5", ink="#003D36"),
}


def text(value, fallback="-"):
    return escape(str(value).strip() if value is not None and str(value).strip() else fallback).replace("\n", "<br/>")


def date(value):
    try:
        return datetime.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(value or "-")


def money(value):
    # Formatting only: totals and item amounts are supplied by the canonical adapter.
    return f"{Decimal(str(value if value is not None else 0)):,.2f}"


def words_once(value):
    """Normalize the suffix only; never recompute or reinterpret the supplied words."""
    words = re.sub(r"(?:\s+only[.\s]*)+$", "", str(value or "").strip(), flags=re.I)
    return text(words) + " <b>Only.</b>" if words else "-"


class InvoiceTheme:
    def __init__(self, payload, logo_path=None):
        self.data = payload
        self.company = payload.get("company") or {}
        self.invoice = payload.get("invoice") or {}
        self.totals = payload.get("totals") or {}
        self.signature = payload.get("signature") or {}
        self.theme = payload.get("theme") if payload.get("theme") in PALETTES else "blue_classic"
        self.clean = self.theme == "blue_classic"
        self.gold = self.theme == "green_gold_premium"
        self.palette = PALETTES[self.theme]
        self.primary, self.accent, self.pale, self.line, self.ink = (
            colors.HexColor(self.palette[key]) for key in ("primary", "accent", "pale", "line", "ink")
        )
        self.logo = logo_path
        self.output = BytesIO()
        self.canvas = Canvas(self.output, pagesize=A4, pageCompression=1)
        self.canvas.setTitle(f"{self.invoice.get('invoice_number', '')} {payload.get('document_type', 'TAX INVOICE')}")
        self.canvas.setAuthor(str(self.company.get("name") or ""))
        self.page = 0

    def paragraph(self, value, size=9.5, bold=False, color=None, align=TA_LEFT, leading=None):
        return Paragraph(value, ParagraphStyle(
            "Invoice", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
            leading=leading or size * 1.34, textColor=color or colors.HexColor("#161E2D"),
            alignment=align, spaceBefore=0, spaceAfter=0, splitLongWords=True,
        ))

    def height(self, paragraph, width):
        return paragraph.wrap(width, PAGE_H * 100)[1]

    def put(self, paragraph, x, top, width):
        height = self.height(paragraph, width)
        paragraph.drawOn(self.canvas, x, PAGE_H - top - height)
        return height

    def line_at(self, x1, top, x2, color=None, thickness=.55):
        self.canvas.setStrokeColor(color or self.line)
        self.canvas.setLineWidth(thickness)
        self.canvas.line(x1, PAGE_H - top, x2, PAGE_H - top)

    def box(self, x, top, width, height, fill=None, stroke=None, radius=4):
        c = self.canvas
        c.setFillColor(fill or colors.white)
        c.setStrokeColor(stroke or fill or colors.white)
        c.setLineWidth(.55)
        c.roundRect(x, PAGE_H - top - height, width, height, radius, fill=1, stroke=bool(stroke))

    def polygon(self, points, fill):
        c = self.canvas
        path = c.beginPath()
        path.moveTo(points[0][0], PAGE_H - points[0][1])
        for x, y in points[1:]:
            path.lineTo(x, PAGE_H - y)
        path.close()
        c.setFillColor(fill)
        c.drawPath(path, fill=1, stroke=0)

    def contours(self, x, top, width, height, color):
        c = self.canvas
        c.saveState()
        clip = c.beginPath()
        clip.rect(x, PAGE_H - top - height, width, height)
        c.clipPath(clip, stroke=0)
        c.setStrokeColor(color)
        c.setLineWidth(.32)
        for i in range(-14, 28):
            path = c.beginPath()
            for j in range(100):
                px = j * width / 99
                py = height * .5 + i * 5 + 11 * sin(px / 35 + i * .13) + 6 * cos(px / 19 + i * .1)
                if j == 0:
                    path.moveTo(x + px, PAGE_H - top - py)
                else:
                    path.lineTo(x + px, PAGE_H - top - py)
            c.drawPath(path, stroke=1)
        c.restoreState()

    def mountains(self, top, height):
        """Pale engraved ridgelines occupy the empty right-hand geospatial panel."""
        x, width = MARGIN + WIDTH * .55, WIDTH * .48
        c = self.canvas
        c.saveState()
        c.setStrokeColor(colors.HexColor("#D4E6E1" if self.gold else "#DAECF5"))
        c.setLineWidth(.38)
        rng = Random(1729)
        peaks = [(0, .86), (.17, .65), (.25, .72), (.46, .35), (.57, .47), (.77, .05), (1, .36)]
        for layer in range(4):
            path = c.beginPath()
            for segment, ((ax, ay), (bx, by)) in enumerate(zip(peaks, peaks[1:])):
                for step in range(19):
                    t = step/18
                    jitter = rng.uniform(-.014, .014) if 0 < step < 18 else 0
                    point = (x+(ax+(bx-ax)*t)*width, PAGE_H-top-(ay+(by-ay)*t+jitter)*height-layer*12)
                    if segment == 0 and step == 0:
                        path.moveTo(*point)
                    else:
                        path.lineTo(*point)
            c.drawPath(path)
        for peak, py in peaks[2:-1]:
            for j in range(13):
                path = c.beginPath()
                sx = x + peak * width
                sy = PAGE_H - top - py * height
                path.moveTo(sx, sy)
                length = rng.uniform(25, height*.48)
                drift = (j-6)*6
                for step in range(1, 10):
                    t = step/9
                    px = sx+drift*t+rng.uniform(-3,3)*t
                    yy = sy-length*t
                    path.lineTo(px, yy)
                    if step in (4,7):
                        branch = c.beginPath()
                        branch.moveTo(px, yy)
                        branch.lineTo(px+rng.uniform(-10,10), yy-8)
                        c.drawPath(branch)
                c.drawPath(path)
        if self.gold:
            self.contours(x, top + height * .6, width, height * .65, colors.HexColor("#DFECE7"))
        c.restoreState()

    def decoration(self):
        if self.clean:
            self.line_at(MARGIN, 38, PAGE_W - MARGIN, self.line)
            self.box(0, PAGE_H - 34, PAGE_W, 30, self.pale, radius=0)
            self.polygon([(0, PAGE_H-45), (130, PAGE_H-45), (159, PAGE_H-4), (113, PAGE_H-4), (96, PAGE_H-20), (0, PAGE_H-20)], self.primary)
            self.polygon([(139, PAGE_H-39), (182, PAGE_H-39), (208, PAGE_H-4), (164, PAGE_H-4)], self.accent)
        else:
            self.contours(0, 0, PAGE_W * .68, 26, self.line)
            start = .45 if self.gold else .65
            self.polygon([(PAGE_W*start, 0), (PAGE_W, 0), (PAGE_W, 26), (PAGE_W*(start-.04), 26)], self.primary)
            self.polygon([(PAGE_W*(start-.03), 0), (PAGE_W*start, 0), (PAGE_W*(start-.04), 26), (PAGE_W*(start-.07), 26)], self.accent)
            if self.gold:
                self.polygon([(PAGE_W-45,0),(PAGE_W,0),(PAGE_W,26),(PAGE_W-20,26)], self.accent)
                for offset in range(5):
                    self.polygon([(480+offset*12, 0), (481+offset*12, 0), (507+offset*12, 26), (506+offset*12, 26)], self.accent)
            self.box(0, PAGE_H - 33, PAGE_W, 33, self.primary, radius=0)
            self.contours(0, PAGE_H-33, PAGE_W, 33, colors.HexColor("#1C605B" if self.gold else "#246078"))
            self.polygon([(PAGE_W-121, PAGE_H-33), (PAGE_W-111, PAGE_H-33), (PAGE_W-80, PAGE_H), (PAGE_W-90, PAGE_H)], colors.white)
            self.polygon([(PAGE_W-107, PAGE_H-33), (PAGE_W-82, PAGE_H-33), (PAGE_W-50, PAGE_H), (PAGE_W-75, PAGE_H)], self.accent)
        self.put(self.paragraph(f"Page {self.page}", size=6.5, color=self.ink if self.clean else colors.white, align=TA_RIGHT), PAGE_W-72, PAGE_H-22, 51)

    def next_page(self, continuation=False):
        if self.page:
            self.canvas.showPage()
        self.page += 1
        self.decoration()
        if continuation:
            left = self.paragraph(text(self.company.get("name")), 11, True, self.ink)
            h = self.put(left, MARGIN, 48, WIDTH * .63)
            right = self.paragraph(text(self.data.get("document_type", "TAX INVOICE")) + " · continued", 10, True, self.ink, TA_RIGHT)
            h = max(h, self.put(right, MARGIN + WIDTH*.65, 48, WIDTH*.35))
            h += self.put(self.paragraph(f"Invoice No: {text(self.invoice.get('invoice_number'))} &nbsp; | &nbsp; {text(date(self.invoice.get('invoice_date')))}", 8.5), MARGIN, 52+h, WIDTH)
            self.line_at(MARGIN, 61+h, PAGE_W-MARGIN, self.primary)
            return 72+h
        return 48

    def image(self, source, x, top, width, height):
        try:
            if str(source).startswith("data:"):
                source = BytesIO(base64.b64decode(str(source).split(",", 1)[1]))
            image = ImageReader(source)
            iw, ih = image.getSize()
            scale = min(width/iw, height/ih)
            dw, dh = iw*scale, ih*scale
            self.canvas.drawImage(image, x+(width-dw)/2, PAGE_H-top-(height+dh)/2,
                                  width=dw, height=dh, mask="auto")
            return True
        except (OSError, ValueError, TypeError):
            return False

    def qr(self, x, top, size):
        if self.data.get("qr_data"):
            qr = QrCodeWidget(str(self.data["qr_data"]), barBorder=1)
            x1, y1, x2, y2 = qr.getBounds()
            drawing = Drawing(size, size, transform=[size/(x2-x1), 0, 0, size/(y2-y1), 0, 0])
            drawing.add(qr)
            renderPDF.draw(drawing, self.canvas, x, PAGE_H-top-size)
        elif self.data.get("qr_image_data_uri"):
            self.image(self.data["qr_image_data_uri"], x, top, size, size)
        else:
            return
        if not self.clean:
            self.put(self.paragraph("Scan for Verification", 6.5, color=self.primary, align=TA_CENTER), x-4, top+size+3, size+8)

    def header(self):
        top = self.next_page()
        logo_width = WIDTH * .35
        if self.logo:
            self.image(str(self.logo), MARGIN, top+15, logo_width, 40)
        else:
            self.put(self.paragraph(text(self.company.get("name")), 17, True, self.primary), MARGIN, top+15, logo_width)
        company_x = MARGIN + WIDTH * .415
        company_width = WIDTH * .415
        p = self.paragraph(text(self.company.get("name")), 12.6, True, self.ink)
        y = top + 10
        y += self.put(p, company_x, y, company_width) + 4
        if self.company.get("address"):
            y += self.put(self.paragraph(text(self.company["address"]), 9.4), company_x, y, company_width) + 3
        contact = " | ".join(str(value) for value in (
            f"Ph: {self.company['phone']}" if self.company.get("phone") else None,
            f"PAN: {self.company['pan']}" if self.company.get("pan") else None,
        ) if value)
        if contact:
            y += self.put(self.paragraph(text(contact), 8.5, color=self.ink), company_x, y, company_width)
        if self.company.get("email"):
            y += self.put(self.paragraph(text(self.company["email"]), 8), company_x, y+2, company_width) + 2
        if not self.clean:
            self.canvas.setStrokeColor(self.primary)
            self.canvas.setLineWidth(.5)
            self.canvas.line(company_x-14, PAGE_H-top-14, company_x-14, PAGE_H-y)
        self.qr(PAGE_W - MARGIN - 80, top, 80)
        # The three header columns share one top baseline. Tall company details push
        # the following section down, rather than colliding with the invoice title.
        meta_top = max(136, y+14) if not self.clean else max(108, top+63)
        pairs = [
            ("INVOICE No", self.invoice.get("invoice_number")),
            ("Invoice Date", date(self.invoice.get("invoice_date"))),
            ("Work Order", self.invoice.get("po_wo_reference")),
            ("Dated", date(self.invoice.get("work_order_date"))),
            ("Dispatched on", date(self.invoice.get("dispatch_date"))),
            ("Dispatched via", self.invoice.get("dispatch_details")),
        ]
        if self.invoice.get("due_date"):
            pairs.insert(2, ("Due Date", date(self.invoice["due_date"])))
        meta_width = WIDTH * (.29 if self.clean else .34)
        rows = [[self.paragraph(text(label), 8.4, i == 0, self.ink, leading=10.3), self.paragraph(":", 8.4), self.paragraph(text(value), 7.8 if i == 0 else 8.4, leading=10.3)] for i, (label, value) in enumerate(pairs)]
        table = Table(rows, colWidths=[meta_width*.37, 7, meta_width*.63-16])
        table.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 2), ("TOPPADDING", (0,0), (-1,-1), .4), ("BOTTOMPADDING", (0,0), (-1,-1), .4),
        ]))
        mh = table.wrap(meta_width-16, PAGE_H*10)[1]+16
        if not self.clean:
            self.box(MARGIN, meta_top, meta_width, mh, self.pale)
            if self.gold:
                self.box(MARGIN, meta_top+4, 1.5, mh-8, self.accent, radius=0)
        table.drawOn(self.canvas, MARGIN+8, PAGE_H-meta_top-mh+8)
        title_x = MARGIN+WIDTH*.38
        title_width = WIDTH*.60
        if self.clean:
            title_x = PAGE_W/2-110
            title_width = 220
            title_top = max(141, y+10)
            self.box(title_x, title_top, title_width, 35, self.pale)
            self.put(self.paragraph(text(self.data.get("document_type", "TAX INVOICE")), 24, True, self.ink, TA_CENTER), title_x+5, title_top+3, title_width-10)
        else:
            title_top = meta_top+19
            title_p = self.paragraph(text(self.data.get("document_type", "TAX INVOICE")), 36, True, self.ink)
            title_h = self.put(title_p, title_x, title_top, title_width)
            self.line_at(title_x+2, title_top+title_h+8, title_x+78, self.accent, 2.5)
            self.put(self.paragraph("Original for Recipient  |  Duplicate for Transporter  |  Triplicate for Supplier", 7.7, color=colors.HexColor("#515B68")), title_x, title_top+title_h+20, title_width)
        next_top = max(meta_top+mh+10, title_top+(48 if self.clean else 82))
        if self.clean:
            self.line_at(MARGIN, next_top, PAGE_W-MARGIN, self.primary, 1.5)
            self.line_at(PAGE_W/2-24, next_top, PAGE_W/2+24, colors.white, 4)
            self.line_at(PAGE_W/2-22, next_top, PAGE_W/2+22, self.accent, 2)
            next_top += 12
        return next_top

    def party_lines(self, party):
        lines = [self.paragraph(text(party.get("name")), 11, True)]
        for key in ("address", "country"):
            if party.get(key):
                lines.append(self.paragraph(text(party[key]), 9.5))
        for label, key in (("GSTIN", "gstin"), ("PAN", "pan"), ("Attn", "contact_person"), ("Ph", "phone"), ("Email", "email")):
            if party.get(key):
                lines.append(self.paragraph(f"{label}: {text(party[key])}", 8.8))
        return lines

    def bill_to(self, top):
        width = WIDTH if self.clean else WIDTH * .56
        ship = self.data.get("ship_to")
        if ship:
            width = (WIDTH-GAP)/2
        lines = self.party_lines(self.data.get("client") or {})
        ship_lines = self.party_lines(ship) if ship else []
        content_h = max(sum(self.height(p, width-30)+2 for p in lines), sum(self.height(p, width-30)+2 for p in ship_lines))
        height = max(119 if not self.clean else 130, content_h+42)
        if not self.clean:
            self.mountains(max(155, top-80), height+75)
        for x, heading, content in [(MARGIN, "BILL TO", lines)] + ([(MARGIN+width+GAP, "SHIP TO", ship_lines)] if ship else []):
            self.box(x, top, width, height, self.pale, self.line)
            self.box(x, top, 92 if self.clean else width, 23, self.primary, radius=3)
            if not self.clean:
                self.box(x, top+16, width, 7, self.primary, radius=0)
            if self.gold:
                self.polygon([(x+width-19, top), (x+width-9, top), (x+width, top+23)], self.accent)
                self.box(x, top+23, 1.5, height-27, self.accent, radius=0)
            self.put(self.paragraph(heading, 10.5, True, colors.white), x+16, top+4, width-28)
            y = top+32
            for p in content:
                y += self.put(p, x+16, y, width-30) + 2
        return top+height+11

    def item_table(self):
        currency = self.totals.get("currency") or "INR"
        fractions = [.094, .334, .116, .121, .155, .18]
        headers = ["Sl. No.", "Items &amp; Description", "Unit", "Qty", f"Rate ({text(currency)})", f"Amount ({text(currency)})"]
        rows = [[self.paragraph(value, 9.2, True, colors.white, TA_CENTER if i != 1 else TA_LEFT) for i, value in enumerate(headers)]]
        if self.gold:
            for p in rows[0][1:]:
                p.style.leftIndent = 12
        for item in self.data.get("line_items") or []:
            description = f"<b>{text(item.get('description'))}</b>"
            if item.get("detail"):
                description += "<br/>" + text(item["detail"])
            if item.get("hsn_sac"):
                description += f"<br/><font size='7.3' color='#586773'>HSN/SAC: {text(item['hsn_sac'])}</font>"
            # Both canonical adapters provide taxable_amount. Reading `amount` here
            # previously rendered INR 0.00 despite a nonzero authoritative ERP value.
            rows.append([
                self.paragraph(text(item.get("sequence")), 9.5, align=TA_CENTER), self.paragraph(description, 9, leading=12),
                self.paragraph(text(item.get("unit")), 9.3, align=TA_CENTER),
                self.paragraph(f"{Decimal(str(item.get('quantity') or 0)):,.2f}", 9.3, align=TA_CENTER),
                self.paragraph(money(item.get("rate")), 9.1, align=TA_RIGHT),
                self.paragraph(money(item.get("taxable_amount")), 9.1, self.clean, align=TA_RIGHT),
            ])
        # Pre-split exceptionally tall descriptions. ReportLab's in-row splitting
        # retains minimum heights/vertical alignment on fragments, which can create
        # dozens of mostly empty pages for a single very long item. Measured text
        # fragments are ordinary rows; financial cells appear on the first only.
        expanded = [rows[0]]
        desc_width = WIDTH*fractions[1]-16
        for row in rows[1:]:
            description = row[1]
            first = True
            while self.height(description, desc_width) > 270:
                fragments = description.split(desc_width, 250)
                if len(fragments) < 2:
                    break
                cells = list(row) if first else ["", "", "", "", "", ""]
                cells[1] = fragments[0]
                expanded.append(cells)
                description = fragments[1]
                first = False
            cells = list(row) if first else ["", "", "", "", "", ""]
            cells[1] = description
            expanded.append(cells)
        table = Table(expanded, colWidths=[WIDTH*f for f in fractions], repeatRows=1, splitByRow=1, splitInRow=0, minRowHeights=[28]+[36]*(len(expanded)-1))
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), self.primary), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, self.pale]),
            ("GRID", (0,0), (-1,-1), .45, self.line), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8),
            ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))
        return table

    def draw_items(self, table, top):
        h = table.wrap(WIDTH, PAGE_H*100)[1]
        table.drawOn(self.canvas, MARGIN, PAGE_H-top-h)
        if self.gold:
            # Small document, cube, calculator, coin and bag marks remain vectors.
            c = self.canvas
            c.saveState()
            c.setStrokeColor(self.accent)
            c.setLineWidth(.75)
            x = MARGIN
            for index, width in enumerate(table._colWidths):
                px, py = x+6, PAGE_H-top-table._rowHeights[0]/2
                if index in (1,3):
                    c.rect(px, py-6, 8, 12, fill=0)
                    c.line(px+2,py+2,px+6,py+2)
                    for offset in (-1,-4):
                        c.line(px+2,py+offset,px+6,py+offset)
                elif index == 2:
                    p = c.beginPath()
                    p.moveTo(px+4,py+6)
                    for dx,dy in ((9,3),(9,-3),(4,-6),(-1,-3),(-1,3),(4,6),(4,0),(9,3)):
                        p.lineTo(px+dx,py+dy)
                    c.drawPath(p)
                    c.line(px-1,py+3,px+4,py)
                    c.line(px+4,py,px+4,py-6)
                elif index == 4:
                    for dy in (-4,0,4):
                        c.ellipse(px,py+dy-2,px+10,py+dy+2,fill=0)
                elif index == 5:
                    c.roundRect(px,py-6,10,10,1,fill=0)
                    c.arc(px+3,py+1,px+7,py+9,0,180)
                    c.line(px+4,py,px+7,py-3)
                x += width
            c.restoreState()
        return h

    def summary_content(self):
        left_w = (WIDTH-GAP)*.56
        right_w = WIDTH-GAP-left_w
        words = [self.paragraph("Total In Words" if self.clean else "Amount in Words", 10.3, True, self.primary),
                 self.paragraph(words_once(self.totals.get("amount_in_words")), 10)]
        legal = [self.paragraph(f"<b>{label}:</b> {text(self.company[key])}", 9.2, color=self.ink) for label, key in
                 (("Company's GST No.", "gstin"), ("HSN/SAC", "hsn_sac"), ("Company's PAN", "pan")) if self.company.get(key)]
        word_height = 25 + sum(self.height(p, left_w-28)+7 for p in words) + sum(self.height(p, left_w-28)+4 for p in legal)
        rows = [("Taxable Value", self.totals.get("taxable_amount"))]
        rows += [(row["label"], row["amount"]) for row in self.data.get("tax_lines") or []]
        rows += [("INVOICE VALUE", self.totals.get("invoice_total"))]
        heights = [max(26, self.height(self.paragraph(text(label), 9.4, True), right_w*.52-20)+14,
                       self.height(self.paragraph(money(value), 11 if i == len(rows)-1 else 10, i == len(rows)-1), right_w*.48-16)+14)
                   for i, (label, value) in enumerate(rows)]
        return left_w, right_w, words, legal, rows, heights, max(126, word_height, sum(heights))

    def summary(self, top, content):
        left_w, right_w, words, legal, rows, heights, height = content
        x = MARGIN
        self.box(x, top, left_w, height, self.pale, self.line if self.clean else None)
        if self.gold:
            self.box(x+2, top+10, 1.5, height-20, self.accent, radius=0)
        y = top+11
        for i, p in enumerate(words):
            y += self.put(p, x+14, y, left_w-28) + 7
            if i == 0 and not self.clean:
                self.line_at(x+14, y-3, x+36, self.accent, 2)
        self.line_at(x+14, y+2, x+left_w-14)
        y += 13
        for p in legal:
            y += self.put(p, x+14, y, left_w-28) + 4
        x += left_w+GAP
        self.box(x, top, right_w, height, colors.white, self.line)
        y = top
        scale = height/sum(heights)
        for i, ((label, value), row_h) in enumerate(zip(rows, heights)):
            h = row_h*scale
            final = i == len(rows)-1
            fill = (self.pale if self.clean else self.primary) if final else (self.pale if i%2 == 0 else colors.white)
            self.box(x+.4, y+.4, right_w-.8, h-.4, fill, radius=0)
            ink = colors.white if final and not self.clean else self.ink
            p = self.paragraph(text(label), 9.5, True, ink)
            self.put(p, x+11, y+(h-self.height(p, right_w*.52-18))/2, right_w*.52-18)
            p = self.paragraph(money(value), 11.3 if final else 10.2, final or self.clean, ink, TA_RIGHT)
            self.put(p, x+right_w*.52+7, y+(h-self.height(p, right_w*.48-17))/2, right_w*.48-17)
            self.line_at(x, y+h, x+right_w)
            self.canvas.setStrokeColor(self.line)
            self.canvas.line(x+right_w*.52, PAGE_H-y, x+right_w*.52, PAGE_H-y-h)
            if final and self.gold:
                self.polygon([(x+right_w*.52-5,y+5),(x+right_w*.52,y+5),(x+right_w*.52+8,y+h/2),(x+right_w*.52,y+h-5),(x+right_w*.52-5,y+h-5),(x+right_w*.52+3,y+h/2)], self.accent)
            y += h
        return top+height+11

    def sign_height(self):
        name = self.signature.get("signed_by_name") if self.signature.get("signed") else self.data.get("authorized_signatory_name")
        left_w = (WIDTH-GAP)*(.47 if self.clean else .56)
        right_w = WIDTH-GAP-left_w
        has_stamp = self.signature.get("signed") and self.signature.get("stamp_image")
        caption_w = right_w*.52+10 if has_stamp else right_w-25
        return max(85, 65+self.height(self.paragraph(text(name, ""), 7.5), caption_w))

    def sign(self, top, height):
        left_w = (WIDTH-GAP)*(.47 if self.clean else .56)
        right_w = WIDTH-GAP-left_w
        self.box(MARGIN, top, left_w, height, colors.white if self.clean else self.pale, self.line if self.clean else None)
        self.calendar(MARGIN+16, top+20)
        self.put(self.paragraph("Date &amp; Time of Invoice", 9.8, True, self.primary), MARGIN+44, top+20, left_w-56)
        raw = self.invoice.get("created_at")
        try:
            # Existing naive timestamps are preserved. A timezone-bearing ERP timestamp
            # retains its explicit offset rather than using the renderer host timezone.
            stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            formatted = stamp.strftime("%d %B %Y  |  %I:%M %p")
            if stamp.tzinfo:
                formatted += " " + stamp.strftime("%z")
        except (ValueError, TypeError):
            formatted = str(raw or "-")
        self.put(self.paragraph(text(formatted), 9.2), MARGIN+44, top+40, left_w-56)
        x = MARGIN+left_w+GAP
        self.box(x, top, right_w, height, colors.white, self.line)
        signed = self.signature.get("signed")
        asset_w = right_w*.52
        has_stamp = signed and self.signature.get("stamp_image")
        if signed and self.signature.get("signature_image"):
            self.image(self.signature["signature_image"], x+12, top+8, asset_w-12, 44)
        if has_stamp:
            self.image(self.signature["stamp_image"], x+right_w-84, top+5, 75, 75)
        line_w = asset_w if has_stamp else right_w-35
        name = self.signature.get("signed_by_name") if signed else self.data.get("authorized_signatory_name")
        name_p = self.paragraph(text(name), 7.5, color=self.ink, align=TA_CENTER) if name else None
        name_h = self.height(name_p, line_w+10) if name_p else 0
        baseline = top+height-(24+name_h if name else 31)
        self.line_at(x+15, baseline, x+15+line_w, self.ink)
        self.put(self.paragraph("Authorised Signatory", 9.5, color=self.ink, align=TA_CENTER), x+10, baseline+4, line_w+10)
        if name:
            self.put(name_p, x+10, baseline+18, line_w+10)
        if not signed:
            self.put(self.paragraph("UNSIGNED", 6.4, color=colors.HexColor("#78868D"), align=TA_RIGHT), x+right_w-71, top+8, 60)
        return top+height+12

    def calendar(self, x, top):
        self.box(x, top, 18, 20, colors.white, self.primary, 2)
        self.line_at(x, top+6, x+18, self.primary, 1.5)
        for row in range(2):
            for col in range(3):
                self.box(x+4+col*4, top+10+row*4, 2, 2, self.primary, radius=0)

    def terms_parts(self):
        sections = []
        for heading, value in (("Terms &amp; Conditions", self.data.get("terms_conditions") or self.invoice.get("payment_terms")),
                               ("Notes", self.data.get("notes") or self.invoice.get("notes"))):
            if value:
                sections += [self.paragraph(heading, 9, True, self.primary), self.paragraph(text(value), 7.8)]
        # Optional fields stay dynamic, without displacing the reference grid unless
        # the ERP actually provides them.
        extras = []
        for label, key in (("Bank", "bank_name"), ("Account", "bank_account_number"), ("Account Name", "bank_account_name"),
                           ("IFSC", "bank_ifsc"), ("SWIFT", "bank_swift"), ("Branch", "bank_branch")):
            if self.company.get(key):
                extras.append(f"{label}: {self.company[key]}")
        if extras:
            sections += [self.paragraph("Bank Details", 8.5, True, self.primary), self.paragraph(text(" | ".join(extras)), 7.5)]
        return sections

    def terms_height(self, parts):
        return max(48 if not self.clean else 0, sum(self.height(p, WIDTH*.59-10)+3 for p in parts)+14) if parts or not self.clean else 0

    def terms(self, top, parts):
        # Large notes/terms flow at readable size onto continuation pages.
        if not parts and self.clean:
            return
        self.line_at(MARGIN, top, PAGE_W-MARGIN, self.primary, .8)
        y = top+10
        thanks_w = WIDTH*.34
        self.put(self.paragraph("Thank You", 10, True, self.primary), MARGIN+WIDTH*.66, y, thanks_w)
        self.put(self.paragraph(f"For choosing {text(self.company.get('name'))}.<br/>We look forward to a long-term partnership.", 8.2, color=colors.HexColor("#505B65")), MARGIN+WIDTH*.66, y+19, thanks_w)
        for paragraph in parts:
            while self.height(paragraph, WIDTH*.59-10) > BOTTOM-y:
                fragments = paragraph.split(WIDTH*.59-10, BOTTOM-y)
                if fragments:
                    self.put(fragments[0], MARGIN+13, y, WIDTH*.59-10)
                    paragraph = fragments[1] if len(fragments)>1 else None
                y = self.next_page(True)
                if paragraph is None:
                    break
            if paragraph:
                y += self.put(paragraph, MARGIN+13, y, WIDTH*.59-10)+3

    def build(self):
        top = self.bill_to(self.header())
        table = self.item_table()
        summary = self.summary_content()
        sign_height = self.sign_height()
        terms = self.terms_parts()
        # Keep normal final sections on one page. Oversized legal text flows separately.
        tail_h = summary[-1]+11+sign_height+12+min(100, self.terms_height(terms))+11
        while True:
            available = BOTTOM-top
            h = table.wrap(WIDTH, PAGE_H*100)[1]
            if h+tail_h <= available:
                self.draw_items(table, top)
                top += h+11
                break
            if h <= available and tail_h+table._rowHeights[0]+table._rowHeights[-1] > BOTTOM-110:
                # Very long summary/notes: finish the items before flowing the tail.
                self.draw_items(table, top)
                top = self.next_page(True)
                break
            limit = available
            if h <= available:
                # Carry at least one body row with the final totals, avoiding a page
                # containing only the totals when the table can be split sensibly.
                limit = min(available, h-table._rowHeights[-1]+.01)
            pieces = table.split(WIDTH, max(0, limit))
            if not pieces:
                if top < 120:
                    # An oversized row is split by ReportLab's splitInRow support.
                    table.splitInRow = 1
                    pieces = table.split(WIDTH, max(0, available))
                    if not pieces:
                        raise ValueError("Invoice item cannot fit within the A4 printable area")
                else:
                    top = self.next_page(True)
                    continue
            first = pieces[0]
            self.draw_items(first, top)
            top = self.next_page(True)
            if len(pieces) == 1:
                break
            table = pieces[1]
        if top+summary[-1]+11+sign_height > BOTTOM:
            top = self.next_page(True)
        top = self.summary(top, summary)
        top = self.sign(top, sign_height)
        if top+min(48, self.terms_height(terms)) > BOTTOM:
            top = self.next_page(True)
        if self.terms_height(terms) <= BOTTOM-top:
            # Anchor short final-page furniture near the reference footer baseline.
            top = max(top, BOTTOM-self.terms_height(terms))
        self.terms(top, terms)
        self.canvas.save()
        self.output.seek(0)
        return self.output


def build_reference_invoice_pdf(payload, logo_path=None):
    return InvoiceTheme(payload, logo_path).build()
