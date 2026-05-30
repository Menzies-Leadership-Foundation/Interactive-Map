"""Generate the 17-page A4 draft PDF for Menzies Leadership Foundation.

Brand palette and content sourced from /mnt/workspace/output/index.html
(FALLBACK_ELEMENTS / FALLBACK_CONNECTIONS).
"""
import re
from datetime import date
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    PageBreak, KeepTogether, Table, TableStyle, Flowable, NextPageTemplate,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Palette ──────────────────────────────────────────────────────────────
NAVY   = HexColor('#0f1f35')
NAVY2  = HexColor('#172844')
GOLD   = HexColor('#c8963e')
GOLDL  = HexColor('#e8b96a')
CREAM  = HexColor('#f7f3ed')
CREAM2 = HexColor('#ede7dd')
SLATE  = HexColor('#4a5d73')
TEXT   = HexColor('#1a2635')
TEXTM  = HexColor('#4a5568')
TEXTD  = HexColor('#8898aa')

CAT_COLOURS = {
    'Community resilience':          HexColor('#3b9ede'),
    'Indigenous self-determination': HexColor('#e8b84a'),
    'Education outcomes':            HexColor('#5cb85c'),
    'Youth development':             HexColor('#e87c3e'),
    'Insight and influence':         HexColor('#d9534f'),
    'Technology leadership':         HexColor('#9b72cf'),
    '':                              HexColor('#8898aa'),
}

# ── Data (live from the Google Sheet, with HTML embed as fallback) ───────
# build_pdf.py lives in working/, so the repo root is its parent's parent.
REPO_ROOT = Path(__file__).resolve().parent.parent

def _locate_index_html():
    """Find the interactive-map index.html anywhere in the repo, and use its
    folder for output so the generated PDF lands beside it (the map's download
    link is relative). Works regardless of layout: root, /docs, /output, etc."""
    preferred = [
        REPO_ROOT / 'index.html',
        REPO_ROOT / 'docs' / 'index.html',
        REPO_ROOT / 'output' / 'index.html',
    ]
    for p in preferred:
        if p.is_file() and 'FALLBACK_ELEMENTS' in p.read_text(errors='ignore'):
            return p
    # Repo-wide search for the map's data marker, skipping any packaged bundle.
    for p in sorted(REPO_ROOT.rglob('index.html')):
        if 'mlf-github' in str(p):
            continue
        try:
            if 'FALLBACK_ELEMENTS' in p.read_text(errors='ignore'):
                return p
        except Exception:
            continue
    return REPO_ROOT / 'output' / 'index.html'  # conventional fallback

INDEX_PATH = _locate_index_html()
OUTPUT_DIR = INDEX_PATH.parent

# Cover logo (navy MLF "Leadership" emblem) — lives beside this script so the
# GitHub runner finds it via a repo-relative path. Replaces the brand text line.
LOGO_PATH = Path(__file__).resolve().parent / 'mlf_logo.png'

import json
import csv
import io
import urllib.request

CSV_ELEMENTS_URL    = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vQJBJjfHVzeooUl9Z2fMJI6e9h_NvOme7GN4k59X0BAkQ0eikwHXokOeCLJX8nS3Q/pub?gid=1554973704&single=true&output=csv'
CSV_CONNECTIONS_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vQJBJjfHVzeooUl9Z2fMJI6e9h_NvOme7GN4k59X0BAkQ0eikwHXokOeCLJX8nS3Q/pub?gid=740560254&single=true&output=csv'

CONN_TYPE_MAP = {
    'Initiative Contribution': 'Level of Leadership',
    'Lever Contribution':      'Lever',
    'Output Contribution':     'Output',
    'Partner Contribution':    'Partner',
    'Workstream Contribution': 'Workstream',
    'Hypothesis':              'Hypothesis',
}

def _fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8')

def _build_elements(rows):
    out = {}
    for r in rows:
        label = (r.get('Label') or '').strip()
        if not label:
            continue
        tags = r.get('Tags') or ''
        years = sorted({int(m) for m in re.findall(r'\b(20[12]\d)\b', tags)})
        desc = (r.get('Description') or '').strip()
        url  = (r.get('URL') or '').strip()
        # Mirror the HTML's "Learn more here" auto-link injection.
        if url:
            m = re.search(r'((?:Read|Watch|Access|View|Listen to|Learn more\b)[^\n<]{0,60}?)here\.\s*$',
                          desc, re.I)
            if m:
                desc = desc[:m.start()] + f'{m.group(1)}<a href="{url}" target="_blank">here</a>.'
            elif 'href=' not in desc and desc:
                desc = desc.rstrip() + f'\n\nLearn more <a href="{url}" target="_blank">here</a>.'
        out[label] = {
            'type':     (r.get('Type') or '').strip(),
            'category': (r.get('Category') or '').strip(),
            'size':     float(r.get('Size') or 1) if (r.get('Size') or '').strip() else 1,
            'description': desc,
            'years':    years,
            'url':      url,
        }
    return out

def _build_connections(rows):
    out = []
    for r in rows:
        f = (r.get('From') or '').strip(); t = (r.get('To') or '').strip()
        if not f or not t: continue
        raw_type = (r.get('Type') or '').strip()
        out.append({
            'from': f, 'to': t,
            'type': CONN_TYPE_MAP.get(raw_type, raw_type),
            'size': int(r.get('Size') or 1) if (r.get('Size') or '').strip() else 1,
        })
    return out

def _csv_to_dicts(text):
    return list(csv.DictReader(io.StringIO(text)))

def _load_from_sheets():
    el_csv = _fetch(CSV_ELEMENTS_URL)
    cn_csv = _fetch(CSV_CONNECTIONS_URL)
    elements    = _build_elements(_csv_to_dicts(el_csv))
    connections = _build_connections(_csv_to_dicts(cn_csv))
    return elements, connections

def _load_from_html():
    src = INDEX_PATH.read_text()
    el_match = re.search(r'const FALLBACK_ELEMENTS\s*=\s*(\{.*?\});\s*\nconst FALLBACK_CONNECTIONS', src, re.S)
    cn_match = re.search(r'const FALLBACK_CONNECTIONS\s*=\s*(\[.*?\]);\s*\n', src, re.S)
    return json.loads(el_match.group(1)), json.loads(cn_match.group(1))

def load_data():
    """Live Google Sheet first; embedded HTML data if the sheet is unreachable."""
    try:
        elements, connections = _load_from_sheets()
        if elements and connections:
            print('✓ Loaded live data from Google Sheets')
            return elements, connections
    except Exception as e:
        print(f'⚠ Sheet fetch failed ({e!s}); falling back to embedded data')
    elements, connections = _load_from_html()
    print('✓ Loaded embedded fallback data from index.html')
    return elements, connections

ELEMENTS, CONNECTIONS = load_data()

# Pull the cover strings live from the interactive map's landing page.
def load_cover_text():
    src = INDEX_PATH.read_text()
    cover = {}
    # <title> = "<full title> — <brand>"
    t = re.search(r'<title>([^<]+)</title>', src)
    if t:
        # Split only on a spaced dash separator, so the hyphen inside a compound
        # word like "Future-Fit" is not mistaken for the title/brand divider.
        bits = re.split(r'\s+[—–-]\s+', t.group(1).strip(), maxsplit=1)
        cover['full_title'] = bits[0].strip()
        cover['brand']      = bits[1].strip() if len(bits) > 1 else ''
    # Splash divs inside <div id="loading"> — first child = title, second = subtitle
    sp = re.search(r'<div id="loading"[^>]*>(.*?)</div>\s*<style>', src, re.S)
    if sp:
        block = sp.group(1)
        divs = re.findall(r'<div[^>]*>([^<]+)</div>', block)
        if divs:
            cover['splash_title'] = divs[0].strip()
        if len(divs) >= 2:
            cover['splash_sub']   = divs[1].strip()
    # Prefer splash title (matches the visible "Fostering Future-Fit Leadership" exactly)
    cover['title'] = cover.get('splash_title') or cover.get('full_title', '')
    cover['subtitle'] = cover.get('splash_sub', '')
    return cover
COVER = load_cover_text()

def title_split(title):
    """Split the cover title into two display lines: first word on top, rest below."""
    parts = title.split(' ', 1)
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], parts[1]

def load_slide(slide_id):
    """Extract the left-hand title-slide content from an interactive-map slide.
    Returns {eyebrow, title, paragraphs[], items[]} sourced from the HTML."""
    src = INDEX_PATH.read_text()
    m = re.search(rf'<div class="slide[^"]*" id="{slide_id}"[^>]*>(.*?)</div></div>',
                  src, re.S)
    if not m:
        return {}
    block = m.group(1)
    def strip_tags(s):
        s = re.sub(r'<br\s*/?>', '\n', s, flags=re.I)
        # Keep <b>/<i> for inline emphasis — reportlab handles them
        return s.strip()
    out = {}
    ey = re.search(r'<div class="ey">([^<]+)</div>', block)
    if ey: out['eyebrow'] = ey.group(1).strip()
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', block, re.S)
    if h1: out['title'] = re.sub(r'<[^>]+>', '', h1.group(1)).strip()
    body = re.search(r'<div class="bd">(.*?)</div>', block, re.S)
    if body:
        b = body.group(1)
        out['paragraphs'] = [strip_tags(p) for p in re.findall(r'<p>(.*?)</p>', b, re.S)]
        items = re.findall(r'<li>(.*?)</li>', b, re.S)
        out['items'] = [strip_tags(i) for i in items]
    return out
SLIDE1 = load_slide('slide1')

# Map each initiative → primary workstream(s) via its partners.
# Connection pattern: Partner → Workstream (type='Workstream'); Partner → Initiative (type='Partner').
def _init_workstreams():
    partner_ws = {}  # partner_name -> set(workstreams)
    for c in CONNECTIONS:
        if c.get('type') == 'Workstream':
            partner_ws.setdefault(c['from'], set()).add(c['to'])
    init_ws = {}     # init_name -> ordered list of workstreams (most-cited first)
    init_partners = {}
    for c in CONNECTIONS:
        if c.get('type') == 'Partner':
            init_partners.setdefault(c['to'], []).append(c['from'])
    for init, partners in init_partners.items():
        counts = {}
        for p in partners:
            for ws in partner_ws.get(p, ()):
                counts[ws] = counts.get(ws, 0) + 1
        if counts:
            init_ws[init] = sorted(counts, key=lambda w: -counts[w])
    return init_ws
INIT_WS = _init_workstreams()

CAT_HEX = {
    'Community resilience':          '#3b9ede',
    'Indigenous self-determination': '#e8b84a',
    'Education outcomes':            '#5cb85c',
    'Youth development':             '#e87c3e',
    'Insight and influence':         '#d9534f',
    'Technology leadership':         '#9b72cf',
    '':                              '#8898aa',
}
WORKSTREAM_HEX = {
    'Innovation': '#3b9ede',
    'Insight':    '#5cb85c',
    'Influence':  '#d9534f',
}

def years_label(years):
    if not years:
        return ''
    ys = sorted(set(years))
    if len(ys) == 1:
        return f'({ys[0]})'
    return f'({ys[0]}–{ys[-1]})'

def chips_markup(category, workstreams):
    """Inline chip row: coloured dot + label for category and each workstream."""
    parts = []
    if category:
        hexc = CAT_HEX.get(category, '#8898aa')
        parts.append(f'<font color="{hexc}" size="11">●</font> <font color="#4a5568"><b>{category}</b></font>')
    for ws in workstreams:
        whex = WORKSTREAM_HEX.get(ws, '#c8963e')
        parts.append(f'<font color="{whex}" size="11">●</font> <font color="#4a5568">{ws}</font>')
    return '   '.join(parts)

# ── Helpers ───────────────────────────────────────────────────────────────
def clean_desc(text, url=''):
    """Convert embedded <a> tags into reportlab <link> tags; normalise newlines."""
    if not text:
        return ''
    t = text.strip()
    # Convert <a href="X">label</a> → <link href="X"><b><u>label</u></b></link>
    def a_to_link(m):
        href = m.group(1)
        body = m.group(2)
        return f'<link href="{href}" color="#c8963e"><b><u>{body}</u></b></link>'
    t = re.sub(r'<a\s+[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', a_to_link, t)
    # Replace newlines with paragraph breaks
    t = t.replace('\r\n', '\n').replace('\r', '\n')
    return t

def para_split(text):
    """Split body text into paragraphs (double newline or single)."""
    if not text:
        return []
    # Normalize: collapse 3+ newlines to 2
    t = re.sub(r'\n{2,}', '\n\n', text)
    parts = [p.strip() for p in t.split('\n\n') if p.strip()]
    out = []
    for p in parts:
        # Convert single newlines to <br/> within paragraph
        p = p.replace('\n', '<br/>')
        out.append(p)
    return out

def link_here(text, url):
    """Wrap the LAST occurrence of 'here' (case-insensitive) with a hyperlink.
    Skipped if the text already contains a <link> tag (embedded anchor was kept)."""
    if not url or not text:
        return text
    if '<link ' in text:
        return text
    matches = list(re.finditer(r'\bhere\b', text, re.I))
    if not matches:
        return text
    m = matches[-1]
    link = f'<link href="{url}" color="#c8963e"><b><u>{m.group(0)}</u></b></link>'
    return text[:m.start()] + link + text[m.end():]

def workstream_split(desc):
    """For workstream descriptions (Innovation / Insight / Influence) the data has
    pattern: [lead] / [header (often with first item glued onto it)] / [item 2] / [item 3].
    Returns (lead, header, items[])."""
    paras = para_split(clean_desc(desc))
    if not paras:
        return '', '', []
    lead = paras[0]
    rest = paras[1:]
    if not rest:
        return lead, '', []
    first = rest[0]; others = rest[1:]
    header = ''; first_item = ''
    if ':' in first:
        h, _, item = first.partition(':')
        header, first_item = h.strip(), item.strip()
    else:
        # No colon — fall back to detecting "wordWord" gluing (lowercase then uppercase)
        m = re.search(r'([a-z])([A-Z][a-z])', first[:120])
        if m:
            cut = m.start() + 1
            header, first_item = first[:cut].strip(), first[cut:].strip()
        else:
            first_item = first
    items = []
    if first_item:
        items.append(first_item)
    items.extend(others)
    return lead, header, items

def link_paragraph(label, url, body_text, body_style, link_style):
    """Build flowables: description paragraphs; the existing 'here' is hyperlinked."""
    flows = []
    cleaned = link_here(clean_desc(body_text), url)
    for p in para_split(cleaned):
        flows.append(Paragraph(p, body_style))
        flows.append(Spacer(0, 3))
    return flows

# ── Styles ────────────────────────────────────────────────────────────────
ST_COVER_TITLE = ParagraphStyle('cover_title', fontName='Helvetica-Bold', fontSize=36,
                                 textColor=TEXT, leading=42, alignment=TA_CENTER, spaceAfter=14)
ST_COVER_SUB   = ParagraphStyle('cover_sub', fontName='Helvetica', fontSize=14,
                                 textColor=TEXTM, leading=20, alignment=TA_CENTER, spaceAfter=10)
ST_COVER_KICKER= ParagraphStyle('cover_kicker', fontName='Helvetica-Bold', fontSize=10,
                                 textColor=GOLD, leading=14, alignment=TA_CENTER, spaceAfter=24)

ST_EYEBROW = ParagraphStyle('eyebrow', fontName='Helvetica-Bold', fontSize=8.5,
                             textColor=GOLD, leading=12, spaceAfter=6)
ST_H1 = ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=22,
                        textColor=TEXT, leading=28, spaceAfter=10)
ST_H2 = ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=14,
                        textColor=TEXT, leading=18, spaceBefore=8, spaceAfter=6)
ST_H3 = ParagraphStyle('h3', fontName='Helvetica-Bold', fontSize=11,
                        textColor=TEXT, leading=14, spaceBefore=6, spaceAfter=3)
ST_CAT = ParagraphStyle('cat', fontName='Helvetica-Bold', fontSize=8.5,
                         textColor=GOLD, leading=11, spaceAfter=4)
ST_BODY = ParagraphStyle('body', fontName='Helvetica', fontSize=9.5,
                          textColor=TEXTM, leading=14, alignment=TA_JUSTIFY, spaceAfter=4)
ST_BODY_TIGHT = ParagraphStyle('body_tight', fontName='Helvetica', fontSize=9,
                          textColor=TEXTM, leading=13, alignment=TA_LEFT, spaceAfter=3)
ST_LINK = ParagraphStyle('link', fontName='Helvetica-Oblique', fontSize=8.5,
                          textColor=GOLD, leading=11, spaceAfter=2)
ST_NOTE = ParagraphStyle('note', fontName='Helvetica', fontSize=8.5,
                          textColor=TEXTD, leading=12, spaceAfter=4)
ST_LI = ParagraphStyle('li', fontName='Helvetica', fontSize=9.5,
                        textColor=TEXTM, leading=14, leftIndent=14, spaceAfter=3,
                        bulletIndent=2, bulletFontName='Helvetica-Bold', bulletColor=GOLD)
ST_CHIPS = ParagraphStyle('chips', fontName='Helvetica', fontSize=8.5,
                        textColor=TEXTM, leading=11, spaceAfter=3, spaceBefore=1)
ST_YEARS = ParagraphStyle('years', fontName='Helvetica', fontSize=9,
                        textColor=TEXTD, leading=11, spaceAfter=2)

# ── Custom flowables ──────────────────────────────────────────────────────
class GoldRule(Flowable):
    def __init__(self, width=48, height=2):
        super().__init__()
        self.width = width
        self.height = height
    def draw(self):
        self.canv.setFillColor(GOLD)
        self.canv.rect(0, 0, self.width, self.height, stroke=0, fill=1)
    def wrap(self, *a): return (self.width, self.height + 4)

class CategoryStripe(Flowable):
    """A thin vertical or horizontal coloured stripe."""
    def __init__(self, colour, width=180, height=3):
        super().__init__()
        self.colour = colour
        self.width = width
        self.height = height
    def draw(self):
        self.canv.setFillColor(self.colour)
        self.canv.rect(0, 0, self.width, self.height, stroke=0, fill=1)
    def wrap(self, *a): return (self.width, self.height + 2)

class HRule(Flowable):
    def __init__(self, width=180*mm, height=0.4, colour=None):
        super().__init__()
        self.width = width; self.height = height
        self.colour = colour or Color(0,0,0,alpha=0.15)
    def draw(self):
        self.canv.setStrokeColor(self.colour)
        self.canv.setLineWidth(self.height)
        self.canv.line(0, 0, self.width, 0)
    def wrap(self, *a): return (self.width, self.height + 4)

# ── Page templates / footer ───────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN_L = 22*mm
MARGIN_R = 22*mm
MARGIN_T = 22*mm
MARGIN_B = 22*mm

FOOTER_TEXT = 'Menzies Leadership Foundation  ·  Fostering Future-Fit Leadership  ·  May 2026'

def draw_footer(canvas, doc):
    canvas.saveState()
    # ── Header: small brand line at top ──
    canvas.setFont('Helvetica', 6.5)
    canvas.setFillColor(TEXTD)
    canvas.drawString(MARGIN_L, PAGE_H - MARGIN_T + 12, FOOTER_TEXT)
    canvas.setStrokeColor(Color(0, 0, 0, alpha=0.08))
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN_L, PAGE_H - MARGIN_T + 8, PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 8)
    # ── Footer: page number only ──
    canvas.setFont('Helvetica', 7.5)
    canvas.setFillColor(TEXTD)
    canvas.drawRightString(PAGE_W - MARGIN_R, MARGIN_B - 16, f'Page {doc.page}')
    canvas.restoreState()

# ── Cover mid-page separator ────────────────────────────────────────────────
# Swap COVER_SEPARATOR to change the motif beneath the subtitle.
#   'rule'    — a single thin gold line (understated, editorial)
#   'three'   — three small gold dots
#   'diamond' — a small gold diamond flanked by two short rules
#   'dots'    — the original five gold dots
#   'none'    — nothing (pure whitespace)
COVER_SEPARATOR = 'rule'

def draw_separator(canvas, cx, cy, style='rule'):
    canvas.saveState()
    canvas.setFillColor(GOLD)
    if style == 'rule':
        # Match the gold rule beneath the title: width 60, height 2.
        canvas.rect(cx - 30, cy, 60, 2, stroke=0, fill=1)
    elif style == 'three':
        for x in (-12, 0, 12):
            canvas.circle(cx + x, cy + 1, 2.2, stroke=0, fill=1)
    elif style == 'diamond':
        # short rule — gap — diamond — gap — short rule
        canvas.rect(cx - 40, cy + 1, 22, 1.2, stroke=0, fill=1)
        canvas.rect(cx + 18, cy + 1, 22, 1.2, stroke=0, fill=1)
        d = 4
        canvas.saveState()
        canvas.translate(cx, cy + 1.5)
        canvas.rotate(45)
        canvas.rect(-d / 2, -d / 2, d, d, stroke=0, fill=1)
        canvas.restoreState()
    elif style == 'dots':
        for x in (-30, -15, 0, 15, 30):
            canvas.circle(cx + x, cy + 1, 2.5, stroke=0, fill=1)
    # 'none' draws nothing
    canvas.restoreState()

def draw_cover(canvas, doc):
    """Cover page: white background with dark text and gold accents."""
    canvas.saveState()
    # White background (default page colour, but draw explicitly)
    canvas.setFillColor(HexColor('#ffffff'))
    canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    # Top accent bar (gold)
    canvas.setFillColor(GOLD)
    canvas.rect(0, PAGE_H - 6, PAGE_W, 6, stroke=0, fill=1)
    # Bottom accent (gold)
    canvas.rect(0, 0, PAGE_W, 6, stroke=0, fill=1)
    # Brand mark — navy MLF logo, centre-justified (replaces brand text line)
    if LOGO_PATH.is_file():
        logo_w = 46*mm                      # square emblem
        logo_h = logo_w
        canvas.drawImage(str(LOGO_PATH),
                         PAGE_W/2 - logo_w/2, PAGE_H - 78*mm,
                         width=logo_w, height=logo_h,
                         preserveAspectRatio=True, mask='auto')
    # Title — splash title from the landing page (split into two display lines)
    line1, line2 = title_split(COVER.get('title', ''))
    canvas.setFont('Helvetica-Bold', 34)
    canvas.setFillColor(TEXT)
    canvas.drawCentredString(PAGE_W/2, PAGE_H - 108*mm, line1)
    canvas.drawCentredString(PAGE_W/2, PAGE_H - 123*mm, line2)
    # Gold rule
    canvas.setFillColor(GOLD)
    canvas.rect(PAGE_W/2 - 30, PAGE_H - 136*mm, 60, 2, stroke=0, fill=1)
    # Subtitle — splash subtitle from the landing page, wrapped into two lines
    sub = COVER.get('subtitle', '')
    canvas.setFont('Helvetica-Oblique', 13)
    canvas.setFillColor(TEXTM)
    # Wrap at the natural sentence midpoint (after "address")
    if ' address ' in sub:
        a, b = sub.split(' address ', 1)
        canvas.drawCentredString(PAGE_W/2, PAGE_H - 153*mm, f'{a} address')
        canvas.drawCentredString(PAGE_W/2, PAGE_H - 160*mm, b)
    else:
        canvas.drawCentredString(PAGE_W/2, PAGE_H - 153*mm, sub)
    # Mid-page separator (swap COVER_SEPARATOR to change the motif)
    draw_separator(canvas, PAGE_W/2, PAGE_H - 221*mm, COVER_SEPARATOR)

    # ── Interactive map call-out (one sentence, clickable "here") ──
    map_url = 'https://menziesfoundation.org.au'
    prefix = 'This is a static extraction of a live interactive map available '
    here   = 'here'
    suffix = '.'
    pre_w  = canvas.stringWidth(prefix, 'Helvetica', 11)
    here_w = canvas.stringWidth(here,   'Helvetica-Bold', 11)
    total  = pre_w + here_w
    x0     = (PAGE_W - total) / 2
    y_c    = PAGE_H - 232*mm
    canvas.setFont('Helvetica', 11)
    canvas.setFillColor(TEXTM)
    canvas.drawString(x0, y_c, prefix)
    canvas.setFont('Helvetica-Bold', 11)
    canvas.setFillColor(GOLD)
    canvas.drawString(x0 + pre_w, y_c, here)
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.6)
    canvas.line(x0 + pre_w, y_c - 1.5, x0 + pre_w + here_w, y_c - 1.5)
    canvas.linkURL(map_url,
                   (x0 + pre_w, y_c - 3, x0 + pre_w + here_w, y_c + 10),
                   relative=0)
    canvas.setFont('Helvetica', 11)
    canvas.setFillColor(TEXTM)
    canvas.drawString(x0 + pre_w + here_w, y_c, suffix)

    # ── Bottom: downloaded date + site ──
    # Downloaded line matches the callout sentence font (Helvetica 11, TEXTM);
    # the site line matches the previous Downloaded size (Helvetica 9).
    # "Downloaded …" sits directly under the callout sentence (one line below);
    # the site line follows beneath it.
    canvas.setFont('Helvetica', 11)
    canvas.setFillColor(TEXTM)
    canvas.drawCentredString(PAGE_W/2, PAGE_H - 239*mm,
        f'Downloaded {date.today().strftime("%-d %B %Y")}')
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(TEXTD)
    canvas.drawCentredString(PAGE_W/2, 36*mm, 'menziesfoundation.org.au')
    canvas.restoreState()

# ── Build the document ────────────────────────────────────────────────────
def build():
    out = OUTPUT_DIR / 'MLF-Future-Fit-Leadership-DRAFT.pdf'
    doc = BaseDocTemplate(
        str(out), pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title='Fostering Future-Fit Leadership',
        author='Menzies Leadership Foundation',
    )
    frame = Frame(MARGIN_L, MARGIN_B, PAGE_W - MARGIN_L - MARGIN_R,
                  PAGE_H - MARGIN_T - MARGIN_B, id='main', showBoundary=0)
    cover_tmpl   = PageTemplate(id='cover', frames=[frame], onPage=draw_cover)
    content_tmpl = PageTemplate(id='content', frames=[frame], onPage=draw_footer)
    doc.addPageTemplates([cover_tmpl, content_tmpl])

    story = []
    # ─── PAGE 1 — COVER (drawn by onPage) ────────────────────────────────
    story.append(NextPageTemplate('content'))  # switch to content template after cover
    story.append(Spacer(0, 1))  # placeholder so cover renders
    story.append(PageBreak())

    # ─── PAGE 2 — TABLE OF CONTENTS ──────────────────────────────────────
    story.append(Paragraph('Table of contents', ST_H1))
    story.append(GoldRule(48, 2))
    story.append(Spacer(0, 14))
    toc_entries = [
        ('Fostering future-fit leadership', '3',  'sec_intro'),
        ('Levels of Leadership',            '4',  'sec_levels'),
        ('Priority cohorts',                '6',  'sec_cohorts'),
        ('System levers',                   '8',  'sec_levers'),
        ('Our Workstreams',                 '10', 'sec_workstreams'),
        ('Initiatives',                     '11', 'sec_initiatives'),
        ('Outputs',                         '15', 'sec_outputs'),
        ('Partners',                        '21', 'sec_partners'),
        ('Learn more',                      '25', 'sec_learn'),
    ]
    ST_TOC = ParagraphStyle('toc', fontName='Helvetica', fontSize=11,
                            textColor=TEXT, leading=22, spaceAfter=2)
    ST_TOC_PG = ParagraphStyle('toc_pg', fontName='Helvetica-Bold', fontSize=11,
                               textColor=GOLD, leading=22, alignment=2)  # right
    toc_rows = []
    for label, page, anchor in toc_entries:
        link_label = f'<link href="#{anchor}" color="#1a2635">{label}</link>'
        link_page  = f'<link href="#{anchor}"><font color="#cccccc">·············</font>  {page}</link>'
        toc_rows.append([
            Paragraph(link_label, ST_TOC),
            Paragraph(link_page, ST_TOC_PG),
        ])
    # Subtract the Frame's 6pt L/R text inset (12pt total) so the table sits
    # inside the text frame and its items align under the heading / body text.
    toc_avail = PAGE_W - MARGIN_L - MARGIN_R - 12
    toc_tbl = Table(toc_rows,
                    colWidths=[toc_avail * 0.78, toc_avail * 0.22])
    toc_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, Color(0, 0, 0, alpha=0.08)),
    ]))
    story.append(toc_tbl)
    story.append(PageBreak())

    # ─── PAGE 3 — INTRODUCTION + CHALLENGE + HYPOTHESIS (consolidated) ───
    # H1, intro paragraphs and the numbered list are sourced from slide 1
    # of the interactive map (id="slide1" → left-hand title panel).
    intro_title = SLIDE1.get('title', 'Fostering future-fit leadership')
    story.append(Paragraph(f'<a name="sec_intro"/>{intro_title}', ST_H1))
    story.append(GoldRule(48, 2))
    story.append(Spacer(0, 10))
    for p in SLIDE1.get('paragraphs', []):
        story.append(Paragraph(p, ST_BODY))
    for idx, item in enumerate(SLIDE1.get('items', []), start=1):
        story.append(Paragraph(f'<b>{idx}.</b> {item}', ST_LI, bulletText=''))

    # ── The challenge (inline, no page break) ──
    chal = ELEMENTS.get('The 21st Century leadership challenge', {})
    story.append(Spacer(0, 12))
    story.append(HRule(PAGE_W - MARGIN_L - MARGIN_R))
    story.append(Spacer(0, 10))
    story.append(Paragraph('The 21st century leadership challenge', ST_H2))
    for p in para_split(clean_desc(chal.get('description', ''))):
        story.append(Paragraph(p, ST_BODY))
        story.append(Spacer(0, 2))

    # ── Our hypothesis (inline, no page break) ──
    hyp = ELEMENTS.get('Our leadership hypothesis', {})
    story.append(Spacer(0, 10))
    story.append(HRule(PAGE_W - MARGIN_L - MARGIN_R))
    story.append(Spacer(0, 10))
    story.append(Paragraph('A hypothesis for future-fit leadership', ST_H2))
    story.append(Spacer(0, 10))
    for p in para_split(clean_desc(hyp.get('description', ''))):
        story.append(Paragraph(p, ST_BODY))
    story.append(Spacer(0, 8))
    ffl = ELEMENTS.get('FUTURE-FIT LEADERSHIP', {})
    if ffl.get('description'):
        story.append(Paragraph('Future-fit leadership', ST_H2))
        for p in para_split(clean_desc(ffl.get('description', ''))):
            story.append(Paragraph(p, ST_BODY))
    story.append(PageBreak())

    # ─── PAGES 5–6 — LINES OF INQUIRY (continuous numbering) ─────────────
    loi_order = ['Purpose', 'Leadership of self', 'Leading with others',
                 'Leading in systems', 'Inter-cultural leadership',
                 'Developing leadership capability']
    story.append(Paragraph('<a name="sec_levels"/>Levels of Leadership', ST_H1))
    story.append(GoldRule(48, 2))
    story.append(Spacer(0, 8))
    story.append(Paragraph(
        'Our hypothesis is interrogated through multiple lines of inquiries — related to '
        'different levels of leadership required to close the complexity gap.', ST_BODY))
    story.append(Spacer(0, 8))

    ST_LOI_ITEM = ParagraphStyle('loi_item', fontName='Helvetica', fontSize=10,
                                  textColor=TEXTM, leading=14, leftIndent=22,
                                  bulletIndent=0, spaceAfter=5)

    def to_roman(n):
        vals = [(1000,'m'),(900,'cm'),(500,'d'),(400,'cd'),(100,'c'),(90,'xc'),
                (50,'l'),(40,'xl'),(10,'x'),(9,'ix'),(5,'v'),(4,'iv'),(1,'i')]
        out = ''
        for v, s in vals:
            while n >= v:
                out += s; n -= v
        return out

    roman_counter = 1
    for level_idx, name in enumerate(loi_order, start=1):
        el = ELEMENTS.get(name)
        if not el: continue
        desc = clean_desc(el.get('description', ''))
        # Split off "Our lines of Inquiry:" block from the lead description
        m = re.search(r'(?is)our\s+lines?\s+of\s+inquiry\s*:?\s*\n', desc)
        if m:
            lead = desc[:m.start()].strip()
            bullets_block = desc[m.end():].strip()
        else:
            lead = desc
            bullets_block = ''
        # Parse bullet items (lines starting with • or - or *)
        items = []
        for line in bullets_block.split('\n'):
            line = line.strip()
            if not line: continue
            line = re.sub(r'^[•\-\*]\s*', '', line)
            if line:
                items.append(line)

        block = [Paragraph(f'{level_idx}. {name}', ST_H2)]
        for p in para_split(lead):
            block.append(Paragraph(p, ST_BODY_TIGHT))
        if items:
            block.append(Spacer(0, 2))
        story.append(KeepTogether(block))

        # Emit each inquiry item with roman numerals — continuous across levels
        for item in items:
            story.append(Paragraph(
                f'<b><font color="#c8963e">{to_roman(roman_counter)}.</font></b>  {item}',
                ST_LOI_ITEM))
            roman_counter += 1
        story.append(Spacer(0, 6))
    story.append(PageBreak())

    # ─── PAGE 7 — COHORTS ────────────────────────────────────────────────
    story.append(Paragraph('<a name="sec_cohorts"/>Priority cohorts', ST_H1))
    story.append(GoldRule(48, 2))
    story.append(Spacer(0, 8))
    story.append(Paragraph(
        'We focus on four priority cohorts where leadership capability can drive systemic '
        'change at scale.', ST_BODY))
    story.append(Spacer(0, 6))
    ST_COHORT_H = ParagraphStyle('cohort_h', parent=ST_H2,
                                 spaceBefore=4, spaceAfter=3)
    ST_COHORT_BODY = ParagraphStyle('cohort_body', parent=ST_BODY_TIGHT,
                                    leading=12, spaceAfter=2)
    cohort_order = ['Citizens', 'Young people', 'Teachers', 'Indigenous women']
    for name in cohort_order:
        el = ELEMENTS.get(name)
        if not el: continue
        cat = el.get('category', '')
        hexc = CAT_HEX.get(cat, '#8898aa')
        heading = (f'{name} <font color="{hexc}" size="11">({cat})</font>'
                   if cat else name)
        story.append(KeepTogether([
            Paragraph(heading, ST_COHORT_H),
            *link_paragraph(name, el.get('url', ''), el.get('description', ''),
                            ST_COHORT_BODY, ST_LINK),
            Spacer(0, 3),
        ]))
    story.append(PageBreak())

    # ─── PAGES 8–9 — SYSTEMIC LEVERS ─────────────────────────────────────
    story.append(Paragraph('<a name="sec_levers"/>System levers', ST_H1))
    story.append(GoldRule(48, 2))
    story.append(Spacer(0, 8))
    story.append(Paragraph(
        'We identify systemic levers that can shift mental models, structures, and resource '
        'flows to strengthen leadership across Australia.', ST_BODY))
    story.append(Spacer(0, 6))
    # Group levers by category — show category once per group as a wide chip header
    levers = [(k, v) for k, v in ELEMENTS.items() if v.get('type') == 'Lever']
    lev_by_cat = {}
    for name, el in levers:
        lev_by_cat.setdefault(el.get('category', ''), []).append((name, el))
    lev_cats_order = ['Community resilience', 'Youth development', 'Education outcomes',
                      'Indigenous self-determination', 'Insight and influence',
                      'Technology leadership']
    # Append any categories present but not in the canonical order
    for c in lev_by_cat:
        if c and c not in lev_cats_order:
            lev_cats_order.append(c)
    if '' in lev_by_cat:
        lev_cats_order.append('')
    for cat in lev_cats_order:
        items = lev_by_cat.get(cat, [])
        if not items: continue
        items.sort(key=lambda kv: kv[1].get('size', 0))
        col = CAT_COLOURS.get(cat, TEXTD)
        story.append(Spacer(0, 4))
        story.append(CategoryStripe(col, PAGE_W - MARGIN_L - MARGIN_R, 4))
        story.append(Paragraph(cat.upper() or 'LEVER', ST_CAT))
        story.append(Spacer(0, 2))
        for name, el in items:
            story.append(KeepTogether([
                Paragraph(name, ST_H3),
                *[Paragraph(p, ST_BODY_TIGHT) for p in para_split(clean_desc(el.get('description', '')))],
                Spacer(0, 6),
            ]))
    story.append(PageBreak())

    # ─── PAGE 10 — WORKSTREAMS ───────────────────────────────────────────
    story.append(Paragraph('<a name="sec_workstreams"/>Our Workstreams', ST_H1))
    story.append(GoldRule(48, 2))
    story.append(Spacer(0, 8))
    for name in ['Innovation', 'Insight', 'Influence']:
        el = ELEMENTS.get(name)
        if not el: continue
        lead, header, items = workstream_split(el.get('description', ''))
        block = [Paragraph(name, ST_H2)]
        if lead:
            block.append(Paragraph(lead, ST_BODY_TIGHT))
        if header:
            block.append(Spacer(0, 3))
            block.append(Paragraph(f'<b>{header}:</b>', ST_BODY_TIGHT))
        for item in items:
            block.append(Paragraph(item, ST_LI, bulletText='•'))
        block.append(Spacer(0, 8))
        story.append(KeepTogether(block))
    story.append(PageBreak())

    # ─── PAGES 11–13 — INITIATIVES (chips for category + workstream) ─────
    story.append(Paragraph('<a name="sec_initiatives"/>Initiatives', ST_H1))
    story.append(GoldRule(48, 2))
    story.append(Spacer(0, 8))
    inits = [(k, v) for k, v in ELEMENTS.items() if v.get('type') == 'Initiative']
    cats_in_order = ['Community resilience', 'Youth development', 'Education outcomes',
                     'Indigenous self-determination', 'Insight and influence',
                     'Technology leadership']
    # Sort by category position then name; keeps similar items together without big headers
    cat_rank = {c: i for i, c in enumerate(cats_in_order)}
    inits.sort(key=lambda kv: (cat_rank.get(kv[1].get('category', ''), 99), kv[0].lower()))
    for name, el in inits:
        yl = years_label(el.get('years', []))
        title_html = f'{name} <font color="#8898aa" size="10">{yl}</font>' if yl else name
        chips = chips_markup(el.get('category', ''), INIT_WS.get(name, []))
        block = [Paragraph(title_html, ST_H3)]
        if chips:
            block.append(Paragraph(chips, ST_CHIPS))
        block.extend(link_paragraph(name, el.get('url', ''), el.get('description', ''),
                                    ST_BODY_TIGHT, ST_LINK))
        block.append(Spacer(0, 5))
        story.append(KeepTogether(block))
    story.append(PageBreak())

    # ─── PAGES 14–15 — OUTPUTS (chips for category + parent initiative) ──
    story.append(Paragraph('<a name="sec_outputs"/>Outputs', ST_H1))
    story.append(GoldRule(48, 2))
    story.append(Spacer(0, 8))
    story.append(Paragraph(
        'Reports, events, tools and resources produced by our initiatives.', ST_BODY))
    story.append(Spacer(0, 6))
    outputs = [(k, v) for k, v in ELEMENTS.items() if v.get('type') == 'Output']
    # Map each output to its parent initiative
    out_parent = {}
    for c in CONNECTIONS:
        if c.get('type') == 'Output' and ELEMENTS.get(c['from'], {}).get('type') == 'Output':
            out_parent[c['from']] = c['to']
    def out_cat(name, el):
        par = out_parent.get(name)
        if par and ELEMENTS.get(par, {}).get('category'):
            return ELEMENTS[par]['category']
        return el.get('category', '')
    outputs.sort(key=lambda kv: (cat_rank.get(out_cat(kv[0], kv[1]), 99), kv[0].lower()))
    for name, el in outputs:
        yl = years_label(el.get('years', []))
        title_html = f'{name} <font color="#8898aa" size="10">{yl}</font>' if yl else name
        cat = out_cat(name, el)
        par = out_parent.get(name)
        # Build chip row: category + workstream(s) inherited from parent + small "from" tag
        ws_list = INIT_WS.get(par, []) if par else []
        chips = chips_markup(cat, ws_list)
        if par:
            chips = (chips + '   ' if chips else '') + f'<font color="#8898aa">from <i>{par}</i></font>'
        block = [Paragraph(title_html, ST_H3)]
        if chips:
            block.append(Paragraph(chips, ST_CHIPS))
        block.extend(link_paragraph(name, el.get('url', ''), el.get('description', ''),
                                    ST_BODY_TIGHT, ST_LINK))
        block.append(Spacer(0, 5))
        story.append(KeepTogether(block))
    story.append(PageBreak())

    # ─── PAGE 16 — PARTNERS ──────────────────────────────────────────────
    story.append(Paragraph('<a name="sec_partners"/>Partners', ST_H1))
    story.append(GoldRule(48, 2))
    story.append(Spacer(0, 8))
    story.append(Paragraph(
        'We partner with universities, foundations, peak bodies and community organisations '
        'across Australia and internationally to catalyse new ways to build leadership '
        'capacity.', ST_BODY))
    story.append(Spacer(0, 8))
    partners = sorted([(k, v) for k, v in ELEMENTS.items() if v.get('type') == 'Partner'],
                      key=lambda kv: kv[0].lower())
    for name, el in partners:
        desc = clean_desc(el.get('description', ''))
        url = el.get('url', '')
        # Truncate to first paragraph for compactness, hyperlink the 'here' if present
        first_p = para_split(desc)[0] if para_split(desc) else ''
        # If first paragraph doesn't contain 'here' but a later one does, fold that in
        if url and first_p and not re.search(r'\bhere\b', first_p, re.I):
            for p in para_split(desc)[1:]:
                if re.search(r'\bhere\b', p, re.I):
                    first_p = first_p + ' ' + p
                    break
        first_p = link_here(first_p, url)
        block = [Paragraph(name, ST_H3)]
        if first_p:
            block.append(Paragraph(first_p, ST_BODY_TIGHT))
        block.append(Spacer(0, 4))
        story.append(KeepTogether(block))
    story.append(PageBreak())

    # ─── PAGE 17 — LEARN MORE ────────────────────────────────────────────
    story.append(Spacer(0, 30))
    story.append(Paragraph('<a name="sec_learn"/>Learn more', ST_H1))
    story.append(GoldRule(48, 2))
    story.append(Spacer(0, 12))
    story.append(Paragraph(
        'The <link href="https://menziesfoundation.org.au" color="#c8963e">Menzies Leadership '
        'Foundation</link> works at the intersection of practice, research and culture through '
        'three priorities:', ST_BODY))
    story.append(Spacer(0, 4))
    for txt in [
        '<b>Innovation</b> — Catalysing partnerships that build leadership capability.',
        '<b>Insights</b> — Synthesising research and data to advance the field of leadership '
        'in complexity.',
        '<b>Influence</b> — Elevating public narratives on leadership, integrity and '
        'collective responsibility.',
    ]:
        story.append(Paragraph(txt, ST_LI, bulletText='•'))
    story.append(Spacer(0, 18))
    story.append(HRule(PAGE_W - MARGIN_L - MARGIN_R))
    story.append(Spacer(0, 12))
    story.append(Paragraph(
        'Learn more about future-fit leadership and explore the interactive map at '
        '<link href="https://menziesfoundation.org.au" color="#c8963e">'
        'menziesfoundation.org.au</link>.', ST_BODY))
    story.append(Spacer(0, 40))
    story.append(Paragraph('Last updated May 2026', ST_NOTE))

    doc.build(story)
    print(f'✓ Wrote {out}')

if __name__ == '__main__':
    build()
