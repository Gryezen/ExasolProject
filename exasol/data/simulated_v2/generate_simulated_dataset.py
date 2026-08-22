#!/usr/bin/env python3
"""
generate_simulated_dataset.py — build a synthetic "dashboard uploads" corpus
for the Agentic Document Intelligence Platform.

v2: documents are long, narrative/bureaucratic prose (fields are buried in
sentences, not laid out in clean tables), and every document has ~10% of its
data fields corrupted with a realistic error (typo, transposed digits, OCR
character confusion, swapped day/month, currency slip) — independent of the
separate, larger, deliberate cross-document mismatches from v1 (kept, lower
rate). The idea is to give the extraction agent something genuinely messy to
parse, and to give the reasoning/confidence-gate agents both kinds of error
they need to catch: small in-document noise and larger cross-document
contradictions.

Produces N case folders (default 50 — documents are longer now, so fewer
cases keeps the corpus a sane size), each modeling one citizen/vendor upload
session containing 2-5 related documents drawn from:

    Birth certificates, Land records, Tax forms, Legal notices, Contracts,
    Identity documents, Applications, Scanned handwritten forms

Output layout:

    <output_dir>/
      uploads/
        case_0001/
          application.pdf
          identity_document.pdf
          tax_form.pdf
        ...
      manifest.json     # full structured record: every case, every file,
                         # every field's correct value vs. what's actually
                         # written in the document, and whether it was
                         # corrupted
      manifest.csv       # flat per-case summary for spreadsheet browsing

Usage:
    python generate_simulated_dataset.py --n-cases 50 --output-dir ./simulated_dataset --seed 42 --corrupt-rate 0.10
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import textwrap
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.pdfgen import canvas as pdfcanvas

fake = Faker("en_IN")
STYLES = getSampleStyleSheet()

TITLE_STYLE = ParagraphStyle(
    "DocTitle", parent=STYLES["Heading1"], alignment=TA_CENTER, fontSize=14, spaceAfter=4,
)
SUBTITLE_STYLE = ParagraphStyle(
    "DocSubtitle", parent=STYLES["Normal"], alignment=TA_CENTER, fontSize=9,
    textColor=colors.grey, spaceAfter=14,
)
BODY_STYLE = ParagraphStyle(
    "Body", parent=STYLES["Normal"], fontSize=10, leading=15, alignment=TA_JUSTIFY, spaceAfter=9,
)
PARA_HEAD_STYLE = ParagraphStyle(
    "ParaHead", parent=STYLES["Normal"], fontSize=10, leading=15, spaceAfter=2, spaceBefore=6,
    textColor=colors.HexColor("#333333"),
)

INDIAN_DISTRICTS = [
    "Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem", "Vellore",
    "Bengaluru Urban", "Mysuru", "Hyderabad", "Warangal", "Pune", "Nagpur",
    "Lucknow", "Kanpur", "Jaipur", "Kochi", "Thiruvananthapuram",
]

OFFICES = [
    "Office of the Revenue Divisional Officer",
    "Municipal Corporation, Civil Registration Wing",
    "Sub-Registrar Office",
    "District Collectorate",
    "Tahsildar Office",
    "Regional Transport & Identity Office",
]

CORRUPT_RATE = 0.10  # overridden by --corrupt-rate


# ---------------------------------------------------------------------------
# Entity model — one per case, shared across that case's documents
# ---------------------------------------------------------------------------

@dataclass
class Entity:
    name: str
    dob: datetime
    father_name: str
    mother_name: str
    address: str
    district: str
    id_number: str
    phone: str
    annual_income: int
    vendor_name: str = ""
    gstin: str = ""


def make_entity() -> Entity:
    return Entity(
        name=fake.name(),
        dob=fake.date_of_birth(minimum_age=18, maximum_age=75),
        father_name=fake.name_male(),
        mother_name=fake.name_female(),
        address=fake.address().replace("\n", ", "),
        district=random.choice(INDIAN_DISTRICTS),
        id_number=" ".join(fake.numerify("####") for _ in range(3)),
        phone=fake.phone_number(),
        annual_income=random.choice([180000, 240000, 320000, 450000, 600000, 850000]),
        vendor_name=fake.company(),
        gstin=fake.bothify(text="##???####?#Z#").upper(),
    )


# ---------------------------------------------------------------------------
# Noise / corruption engine
# ---------------------------------------------------------------------------

OCR_CONFUSIONS = {"O": "0", "0": "O", "I": "1", "1": "I", "l": "1",
                   "S": "5", "5": "S", "B": "8", "8": "B", "Z": "2", "2": "Z"}


def _corrupt_chars(s: str) -> str:
    """Character-level corruption for freeform text (names, addresses)."""
    if len(s) < 3:
        return s
    chars = list(s)
    idxs = [i for i, c in enumerate(chars) if c.isalnum()]
    if not idxs:
        return s
    op = random.choice(["transpose", "omit", "double", "ocr", "case"])
    i = random.choice(idxs)
    if op == "transpose" and i < len(chars) - 1:
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
    elif op == "omit":
        del chars[i]
    elif op == "double":
        chars.insert(i, chars[i])
    elif op == "ocr" and chars[i] in OCR_CONFUSIONS:
        chars[i] = OCR_CONFUSIONS[chars[i]]
    elif op == "case" and chars[i].isalpha():
        chars[i] = chars[i].upper() if chars[i].islower() else chars[i].lower()
    else:
        del chars[i]
    return "".join(chars)


def _corrupt_digits(s: str) -> str:
    """Digit-level corruption for ID-like strings (keeps non-digit chars)."""
    chars = list(s)
    idxs = [i for i, c in enumerate(chars) if c.isdigit()]
    if not idxs:
        return _corrupt_chars(s)
    op = random.choice(["transpose", "omit", "replace"])
    i = random.choice(idxs)
    if op == "transpose" and i < len(chars) - 1 and chars[i + 1].isdigit():
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
    elif op == "omit":
        del chars[i]
    else:
        chars[i] = random.choice("0123456789")
    return "".join(chars)


def _corrupt_amount(n: int) -> int:
    op = random.choice(["extra_zero", "drop_digit", "digit_shift", "decimal_shift"])
    s = str(n)
    if op == "extra_zero":
        pos = random.randint(1, len(s))
        s = s[:pos] + "0" + s[pos:]
    elif op == "drop_digit" and len(s) > 1:
        pos = random.randint(0, len(s) - 1)
        s = s[:pos] + s[pos + 1:]
    elif op == "digit_shift":
        pos = random.randint(0, len(s) - 1)
        s = s[:pos] + random.choice("0123456789") + s[pos + 1:]
    else:  # decimal_shift
        n2 = n * 10 if random.random() < 0.5 else max(1, n // 10)
        s = str(n2)
    try:
        val = int(s)
        return val if val > 0 else n
    except ValueError:
        return n


def _corrupt_date(d: datetime) -> datetime:
    op = random.choice(["swap_day_month", "year_off", "day_off"])
    day, month, year = d.day, d.month, d.year
    if op == "swap_day_month" and day <= 12:
        day, month = month, day
    elif op == "year_off":
        year += random.choice([-1, 1])
    else:
        day = max(1, min(28, day + random.choice([-2, -1, 1, 2])))
    try:
        return datetime(year, month, day)
    except ValueError:
        return d


def format_value(value, kind: str) -> str:
    if kind == "amount":
        return f"Rs. {value:,.2f}"
    if kind == "date":
        return value.strftime("%d-%m-%Y")
    return str(value)


def corrupt_value(value, kind: str):
    if kind == "amount":
        return _corrupt_amount(value)
    if kind == "date":
        return _corrupt_date(value)
    if kind == "id":
        return _corrupt_digits(value)
    return _corrupt_chars(value)  # name / address / text


def process_fields(fields: list[tuple[str, object, str]], corrupt_rate: float = None):
    """fields: list of (field_name, correct_value, kind).
    Returns (display: dict[name -> str for use in prose], ground_truth: list[dict])."""
    rate = CORRUPT_RATE if corrupt_rate is None else corrupt_rate
    n = len(fields)
    n_corrupt = max(1, round(n * rate)) if n > 0 else 0
    corrupt_idxs = set(random.sample(range(n), min(n_corrupt, n))) if n else set()

    display: dict[str, str] = {}
    ground_truth = []
    for i, (name, value, kind) in enumerate(fields):
        is_corrupt = i in corrupt_idxs
        shown_value = corrupt_value(value, kind) if is_corrupt else value
        display[name] = format_value(shown_value, kind)
        ground_truth.append({
            "field_name": name,
            "kind": kind,
            "correct_value": format_value(value, kind),
            "displayed_value": display[name],
            "is_corrupted": is_corrupt,
        })
    return display, ground_truth


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def random_date(start_years_ago=2, end_days_ago=1) -> datetime:
    start = datetime.now() - timedelta(days=365 * start_years_ago)
    end = datetime.now() - timedelta(days=end_days_ago)
    delta = end - start
    return start + timedelta(days=random.randint(0, max(delta.days, 1)))


def money(n: int) -> str:
    return f"Rs. {n:,.2f}"


def doc_header_flow(title: str, office: str, ref_no: str) -> list:
    return [
        Paragraph(office, SUBTITLE_STYLE),
        Paragraph(title, TITLE_STYLE),
        Paragraph(f"Reference No: {ref_no}  |  Generated: {random_date(0, 1).strftime('%d %B %Y')}", SUBTITLE_STYLE),
        HRFlowable(width="100%", color=colors.HexColor("#999999"), thickness=0.75),
        Spacer(1, 8),
    ]


def paragraphs_flow(paragraphs: list[str]) -> list:
    flow = []
    for p in paragraphs:
        flow.append(Paragraph(p.replace("\n", "<br/>"), BODY_STYLE))
    return flow


def render_pdf(path: Path, flowables: list) -> None:
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=24 * mm, rightMargin=24 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
    )
    doc.build(flowables)


def filler_paragraph(min_sentences=5, max_sentences=9) -> str:
    return fake.paragraph(nb_sentences=random.randint(min_sentences, max_sentences))


def write_doc(out_dir: Path, base_name: str, title: str, office: str, ref_no: str,
              paragraphs: list[str], as_txt: bool, footer: str | None = None) -> str:
    if as_txt:
        fname = f"{base_name}.txt"
        text = f"{office}\n{title}\nReference No: {ref_no}\nGenerated: {random_date(0, 1).strftime('%d %B %Y')}\n"
        text += "-" * 70 + "\n\n"
        text += "\n\n".join(paragraphs)
        if footer:
            text += "\n\n" + footer
        (out_dir / fname).write_text(text)
        return fname

    flow = doc_header_flow(title, office, ref_no)
    flow += paragraphs_flow(paragraphs)
    if footer:
        flow.append(Spacer(1, 10))
        flow.append(Paragraph(footer, SUBTITLE_STYLE))
    fname = f"{base_name}.pdf"
    render_pdf(out_dir / fname, flow)
    return fname


# ---------------------------------------------------------------------------
# Document generators — long, narrative, field-values-buried-in-prose.
# Each returns (filename, ground_truth_fields, [extra return values...])
# ---------------------------------------------------------------------------

def gen_birth_certificate(e: Entity, out_dir: Path, ref_no: str, as_txt: bool):
    fields = [
        ("child_name", e.name, "name"),
        ("date_of_birth", e.dob, "date"),
        ("father_name", e.father_name, "name"),
        ("mother_name", e.mother_name, "name"),
        ("registration_number", fake.bothify(text="BC-####-????"), "id"),
        ("date_of_registration", random_date(1, 30), "date"),
        ("district", e.district, "text"),
        ("place_of_birth", f"{e.district} District Government Hospital", "text"),
    ]
    d, gt = process_fields(fields)
    office = OFFICES[1]

    paragraphs = [
        f"This is to certify that, in accordance with the provisions of the Registration of "
        f"Births and Deaths Act, 1969, and the rules framed thereunder, the birth of a child "
        f"has been duly registered in the records maintained by this office, and that the "
        f"particulars recorded below have been transcribed from the original entry appearing "
        f"in Register No. {fake.bothify('##/####')} maintained for the year "
        f"{d['date_of_registration'][-4:]}.",

        f"The child, whose name has been recorded in the register as {d['child_name']}, was "
        f"born on {d['date_of_birth']} at {d['place_of_birth']}, situated within the "
        f"jurisdiction of {d['district']} district. The father of the child is recorded as "
        f"{d['father_name']}, and the mother is recorded as {d['mother_name']}, both residing "
        f"within the said district at the time of the occurrence of the birth event described "
        f"herein.",

        f"The entry corresponding to this birth bears Registration Number {d['registration_number']}, "
        f"and the said entry was made in this office on {d['date_of_registration']}, following "
        f"receipt of the requisite intimation from the reporting institution. No corrections, "
        f"amendments, or subsequent endorsements have been made to this entry since the date "
        f"of original registration, save as may otherwise be separately noted in the margin of "
        f"the register itself.",

        filler_paragraph(4, 7),

        "This certificate is issued free of charge on this occasion under the seal of this "
        "office and is valid for all official purposes, including but not limited to school "
        "admission, passport application, and other identity-verification processes, subject "
        "always to cross-verification against the original register maintained herein, which "
        "shall prevail in the event of any discrepancy between this extract and the original "
        "entry.",
    ]
    footer = '<i>Issuing Registrar — ' + office + '</i>'
    fname = write_doc(out_dir, "birth_certificate", "EXTRACT OF BIRTH REGISTER / BIRTH CERTIFICATE", office, ref_no, paragraphs, as_txt, footer)
    return fname, gt


def gen_land_record(e: Entity, out_dir: Path, ref_no: str, as_txt: bool, amount_override: int | None = None):
    value = amount_override if amount_override is not None else random.choice([850000, 1200000, 2500000, 4200000, 7800000])
    extent = round(random.uniform(0.2, 4.5), 2)
    fields = [
        ("owner_name", e.name, "name"),
        ("survey_number", fake.bothify(text="SY-###/#?"), "id"),
        ("patta_number", fake.bothify(text="PT-#####"), "id"),
        ("registered_value", value, "amount"),
        ("district", e.district, "text"),
    ]
    d, gt = process_fields(fields)
    classification = random.choice(["dry land", "wet land", "residential plot", "agricultural land"])
    encumbrance = random.choice(["free from all encumbrances", "free from all encumbrances",
                                  "free from all encumbrances", "subject to a mortgage pending clearance"])

    paragraphs = [
        f"Extract from the Register of Land Records maintained under the Digital India Land "
        f"Records Modernization Programme, prepared in respect of the immovable property "
        f"comprised in Survey Number {d['survey_number']}, situated in the {d['district']} "
        f"district, and recorded in the name of {d['owner_name']} as the registered owner "
        f"pursuant to the chain of title traced through the mutation entries appearing in "
        f"the village accounts.",

        f"The extent of the said property, as measured and recorded during the most recent "
        f"resurvey, is {extent} acres, classified in the land-use register as {classification}. "
        f"The property is bounded, according to the field-measurement book, on the north by "
        f"{fake.street_name()}, on the south by land comprised in an adjoining survey number, "
        f"on the east by a public pathway, and on the west by land belonging to a neighbouring "
        f"pattadar, all as more particularly delineated in the accompanying village map, which "
        f"is not reproduced in this extract.",

        f"The property stands registered at a value of {d['registered_value']} for the purposes "
        f"of stamp duty and registration fee computation as on the date this extract was drawn, "
        f"and the corresponding Patta Number allotted to the holding is {d['patta_number']}. As "
        f"per the encumbrance particulars available with this office as on date, the property "
        f"is {encumbrance}.",

        filler_paragraph(4, 7),

        "This extract has been generated from the digitised land records database and is "
        "furnished for the limited purpose of official verification. It does not, by itself, "
        "confer or extinguish any title, right, or interest in the property, and applicants "
        "are advised to obtain a certified copy of the patta and encumbrance certificate from "
        "the jurisdictional Sub-Registrar Office before relying on this extract for any "
        "transactional purpose.",
    ]
    fname = write_doc(out_dir, "land_record", "LAND OWNERSHIP RECORD — EXTRACT", "Sub-Registrar Office", ref_no, paragraphs, as_txt)
    return fname, gt, value


def gen_income_certificate(e: Entity, out_dir: Path, ref_no: str, as_txt: bool, income_override: int | None = None):
    income = income_override if income_override is not None else e.annual_income
    fy = f"{datetime.now().year - 1}-{str(datetime.now().year)[2:]}"
    fields = [
        ("applicant_name", e.name, "name"),
        ("father_name", e.father_name, "name"),
        ("address", e.address, "address"),
        ("annual_income", income, "amount"),
        ("issued_on", random_date(1, 5), "date"),
    ]
    d, gt = process_fields(fields)
    purpose = random.choice(["a welfare scheme application", "an educational scholarship application", "a bank loan application"])

    paragraphs = [
        f"This is to certify, on the basis of enquiries made and declarations furnished, that "
        f"{d['applicant_name']}, son/daughter of {d['father_name']}, residing at {d['address']}, "
        f"has been assessed by this office in connection with {purpose} submitted by the "
        f"applicant for the purpose of determining eligibility under the income criteria "
        f"prescribed for the scheme in question.",

        f"The total annual income of the applicant's family, computed from all sources "
        f"including salary, agricultural income, and any other declared income for the "
        f"financial year {fy}, has been assessed at {d['annual_income']}. This assessment "
        f"has been arrived at after due enquiry through the village administrative officer "
        f"and cross-verification of the documents furnished in support of the application, "
        f"including salary slips and land revenue records where applicable.",

        filler_paragraph(4, 6),

        f"This certificate was issued on {d['issued_on']} and remains valid for a period of "
        f"one year from the date of issue, or until superseded by a fresh assessment, "
        f"whichever occurs earlier. It is issued strictly for the stated purpose and is not "
        f"transferable for any other use without fresh verification by the issuing authority.",
    ]
    fname = write_doc(out_dir, "income_certificate", "INCOME CERTIFICATE", random.choice(OFFICES), ref_no, paragraphs, as_txt)
    return fname, gt, income


def gen_property_tax_receipt(e: Entity, out_dir: Path, ref_no: str, as_txt: bool, amount_override: int | None = None):
    amount = amount_override if amount_override is not None else random.choice([4200, 6800, 9500, 15200, 22000])
    fields = [
        ("assessee_name", e.name, "name"),
        ("property_id", fake.bothify(text="PID-######"), "id"),
        ("address", e.address, "address"),
        ("tax_amount_paid", amount, "amount"),
        ("payment_date", random_date(0, 2), "date"),
    ]
    d, gt = process_fields(fields)
    assessment_year = f"{datetime.now().year}-{str(datetime.now().year + 1)[2:]}"
    mode = random.choice(["online payment gateway (UPI)", "bank counter challan", "net banking transfer"])

    paragraphs = [
        f"Receipt issued by the Revenue Wing of the Municipal Corporation acknowledging "
        f"payment of property tax in respect of the holding registered under Property "
        f"Identification Number {d['property_id']}, standing in the name of "
        f"{d['assessee_name']} as the assessee of record, situated at {d['address']}.",

        f"The amount of {d['tax_amount_paid']} was received towards the property tax "
        f"assessment for the year {assessment_year}, the payment having been effected "
        f"through {mode} on {d['payment_date']}. The amount so paid has been credited "
        f"against the outstanding demand raised in the half-yearly assessment register "
        f"maintained by this office.",

        filler_paragraph(3, 6),

        "This receipt is generated electronically through the Corporation's revenue "
        "management system and does not require a physical signature to be considered "
        "valid for record purposes. Assessees are advised to retain this receipt for "
        "future reference, including for property-transfer and no-dues certification "
        "purposes.",
    ]
    fname = write_doc(out_dir, "property_tax_receipt", "PROPERTY TAX PAYMENT RECEIPT", "Municipal Corporation, Revenue Wing", ref_no, paragraphs, as_txt)
    return fname, gt, amount


def gen_gst_invoice(e: Entity, out_dir: Path, ref_no: str, as_txt: bool, amount_override: int | None = None):
    total = amount_override if amount_override is not None else random.choice([45000, 78000, 125000, 260000, 410000])
    taxable = round(total * 0.86)
    gst = total - taxable
    fields = [
        ("vendor_name", e.vendor_name, "name"),
        ("gstin", e.gstin, "id"),
        ("billed_to", e.name, "name"),
        ("invoice_date", random_date(0, 10), "date"),
        ("total_invoice_value", total, "amount"),
    ]
    d, gt = process_fields(fields)
    terms = random.choice(["Net 30 days from the date of invoice", "Net 45 days from the date of invoice", "payable immediately upon receipt"])
    service = random.choice(["professional consulting services", "software implementation and support services",
                              "logistics and freight-forwarding services", "facility management services",
                              "annual maintenance and support services"])

    paragraphs = [
        f"Tax invoice raised by {d['vendor_name']} (GSTIN {d['gstin']}) in favour of "
        f"{d['billed_to']}, in respect of {service} rendered during the billing period "
        f"immediately preceding the date of this invoice, {d['invoice_date']}, and in "
        f"accordance with the terms of the underlying service agreement executed between "
        f"the parties.",

        f"The taxable value of the services rendered, before the application of Goods and "
        f"Services Tax at the applicable rate of 18%, amounts to Rs. {taxable:,.2f}, to "
        f"which a further sum of Rs. {gst:,.2f} has been added towards CGST and SGST "
        f"components in equal measure, arriving at a total invoice value, inclusive of all "
        f"applicable taxes, of {d['total_invoice_value']}.",

        filler_paragraph(3, 6),

        f"Payment against this invoice is due on the following terms: {terms}. Any delay "
        f"in payment beyond the agreed terms shall attract interest at the rate specified "
        f"in the underlying agreement, without prejudice to any other remedy available to "
        f"the vendor under applicable law.",
    ]
    fname = write_doc(out_dir, "gst_invoice", "TAX INVOICE", d["vendor_name"], ref_no, paragraphs, as_txt)
    return fname, gt, total


def gen_legal_notice(e: Entity, out_dir: Path, ref_no: str, as_txt: bool):
    subject = random.choice([
        "non-payment of outstanding dues",
        "encroachment upon registered property",
        "breach of contractual obligations",
        "failure to vacate leased premises",
    ])
    fields = [
        ("addressee_name", e.name, "name"),
        ("address", e.address, "address"),
        ("notice_date", random_date(0, 15), "date"),
        ("advocate_name", fake.name(), "name"),
        ("enrolment_number", fake.bothify("??/####/????"), "id"),
    ]
    d, gt = process_fields(fields)

    paragraphs = [
        f"To, {d['addressee_name']}, presently residing at {d['address']}.",

        f"Under instructions received from and on behalf of our client, and further to "
        f"correspondence exchanged between the parties over the preceding weeks concerning "
        f"the matter of {subject}, we are constrained to issue this formal notice calling "
        f"upon you to remedy the breach complained of within a period of fifteen days from "
        f"the date of receipt of this notice, dated {d['notice_date']}.",

        f"Our client's grievance, briefly stated, is that despite repeated reminders and "
        f"opportunities extended in good faith, you have failed and neglected to address "
        f"the matter of {subject}, thereby causing continuing loss and inconvenience to our "
        f"client, who reserves all rights and remedies available in law, including the right "
        f"to initiate civil proceedings for recovery of damages and, where applicable, "
        f"criminal proceedings, without any further notice to you in that regard.",

        filler_paragraph(4, 7),

        f"You are hereby called upon to comply with the demands set out above within the "
        f"stipulated period, failing which our client shall be left with no alternative but "
        f"to pursue such legal remedies as may be available, entirely at your risk as to "
        f"costs and consequences. This notice is issued without prejudice to any other "
        f"right or remedy available to our client, all of which are expressly reserved.",
    ]
    footer = f'<i>{d["advocate_name"]}, Advocate — Enrolment No. {d["enrolment_number"]}</i>'
    fname = write_doc(out_dir, "legal_notice", "LEGAL NOTICE", "Advocate's Chamber", ref_no, paragraphs, as_txt, footer)
    return fname, gt


def gen_contract(e: Entity, out_dir: Path, ref_no: str, as_txt: bool, amount_override: int | None = None):
    value = amount_override if amount_override is not None else random.choice([250000, 480000, 750000, 1250000, 2100000])
    term_months = random.choice([6, 12, 18, 24, 36])
    fields = [
        ("client_name", e.name, "name"),
        ("vendor_name", e.vendor_name, "name"),
        ("effective_date", random_date(1, 60), "date"),
        ("contract_value", value, "amount"),
        ("governing_law_district", e.district, "text"),
    ]
    d, gt = process_fields(fields)
    payment_terms = random.choice(["thirty (30) days from the date of each invoice",
                                    "forty-five (45) days from the date of each invoice",
                                    "on a milestone basis as set out in Schedule B"])
    service = random.choice(["consulting and advisory services", "software development and maintenance services",
                              "supply and installation of equipment", "facility management services"])

    paragraphs = [
        f"This Service Agreement (\"Agreement\") is made and entered into on "
        f"{d['effective_date']}, by and between {d['client_name']} (hereinafter referred to "
        f"as the \"Client\"), and {d['vendor_name']} (hereinafter referred to as the "
        f"\"Vendor\"), each individually a \"Party\" and collectively the \"Parties\" to "
        f"this Agreement.",

        f"WHEREAS the Client wishes to engage the Vendor to provide {service}, and the "
        f"Vendor has represented that it possesses the necessary skill, experience, and "
        f"resources to perform such services in a professional and workmanlike manner, "
        f"the Parties agree as follows.",

        f"1. Term. This Agreement shall commence on {d['effective_date']} and shall continue "
        f"in force for a period of {term_months} months thereafter, unless terminated "
        f"earlier in accordance with the provisions of this Agreement, and may be renewed "
        f"upon the mutual written consent of both Parties.",

        f"2. Consideration. In consideration of the services to be rendered under this "
        f"Agreement, the Client shall pay to the Vendor a total sum of "
        f"{d['contract_value']}, payable in accordance with the following terms: "
        f"{payment_terms}. All amounts stated are exclusive of applicable taxes unless "
        f"otherwise specified.",

        f"3. Termination. Either Party may terminate this Agreement by providing thirty "
        f"(30) days' prior written notice to the other Party. Termination shall not affect "
        f"any accrued rights or obligations of either Party as of the date of termination.",

        f"4. Governing Law. This Agreement shall be governed by and construed in "
        f"accordance with the laws applicable in India, and the Parties submit to the "
        f"exclusive jurisdiction of the courts situated in {d['governing_law_district']} "
        f"in respect of any dispute arising out of or in connection with this Agreement.",

        filler_paragraph(3, 6),
    ]
    footer = "IN WITNESS WHEREOF, the Parties have executed this Agreement as of the date first written above.  Signed for Client: ______________     Signed for Vendor: ______________"
    fname = write_doc(out_dir, "contract", "SERVICE AGREEMENT", "Contracts Desk", ref_no, paragraphs, as_txt, footer)
    return fname, gt, value


def gen_identity_document(e: Entity, out_dir: Path, ref_no: str, as_txt: bool):
    kind = random.choice(["Aadhaar-style Identity Card", "Voter Identity Card", "PAN-style Tax Identity Card"])
    fields = [
        ("name", e.name, "name"),
        ("date_of_birth", e.dob, "date"),
        ("id_number", e.id_number, "id"),
        ("address", e.address, "address"),
        ("phone", e.phone, "id"),
    ]
    d, gt = process_fields(fields)

    paragraphs = [
        f"This document serves as a specimen record confirming the identity particulars of "
        f"the bearer, issued by the Regional Identity Authority under the category of "
        f"{kind}. The particulars recorded below have been captured at the time of "
        f"enrolment and are subject to periodic verification and update as per the "
        f"applicable identity-management regulations in force.",

        f"The bearer of this document is identified in the enrolment database as "
        f"{d['name']}, born on {d['date_of_birth']}, and allotted the unique identification "
        f"number {d['id_number']} at the time of enrolment. The residential address "
        f"recorded against this enrolment is {d['address']}, and the registered contact "
        f"number on file is {d['phone']}.",

        filler_paragraph(3, 5),

        "This is a synthetic specimen document generated for software testing purposes "
        "only. It does not correspond to a real government-issued identity document, and "
        "no inference regarding an actual individual should be drawn from its contents.",
    ]
    fname = write_doc(out_dir, "identity_document", f"{kind.upper()} (SPECIMEN)", "Regional Identity Authority", ref_no, paragraphs, as_txt)
    return fname, gt


def gen_application(e: Entity, out_dir: Path, ref_no: str, purpose: str, as_txt: bool):
    fields = [
        ("applicant_name", e.name, "name"),
        ("father_name", e.father_name, "name"),
        ("address", e.address, "address"),
        ("phone", e.phone, "id"),
        ("application_date", random_date(0, 20), "date"),
    ]
    d, gt = process_fields(fields)
    office = random.choice(OFFICES)

    paragraphs = [
        f"To, The {office}, {e.district} District.",

        f"Respected Sir/Madam, I, {d['applicant_name']}, son/daughter of {d['father_name']}, "
        f"residing at {d['address']}, do hereby most respectfully submit this application "
        f"dated {d['application_date']}, requesting {purpose}, and enclose herewith copies "
        f"of the supporting documents referred to in the accompanying checklist for your "
        f"kind and favourable consideration.",

        filler_paragraph(3, 6),

        f"I may be contacted at {d['phone']} for any clarification that may be required in "
        f"connection with this application, and I undertake to furnish any further "
        f"document or information that this office may reasonably require in order to "
        f"process the application. I request that the application be processed at the "
        f"earliest possible opportunity, and I shall remain grateful for the same.",

        f"Thanking you, Yours faithfully, {d['applicant_name']}.",
    ]
    fname = write_doc(out_dir, "application", "APPLICATION", office, ref_no, paragraphs, as_txt)
    return fname, gt


def gen_scanned_handwritten_form(e: Entity, out_dir: Path, ref_no: str):
    """Simulated phone/scanner capture of a handwritten, lengthy complaint —
    italic font, slight rotation, faint vignette; stays a plain digital PDF."""
    fields = [
        ("name", e.name, "name"),
        ("address", e.address, "address"),
        ("phone", e.phone, "id"),
        ("date", random_date(0, 25), "date"),
    ]
    d, gt = process_fields(fields)

    complaint_paragraphs = [fake.paragraph(nb_sentences=random.randint(5, 8)) for _ in range(3)]

    fname = "scanned_handwritten_form.pdf"
    path = out_dir / fname
    c = pdfcanvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    c.saveState()
    c.setFillColorRGB(0.94, 0.94, 0.90)
    c.rect(0, 0, width, height, fill=1, stroke=0)
    c.restoreState()

    c.saveState()
    c.translate(width / 2, height / 2)
    c.rotate(random.uniform(-2.5, 2.5))
    c.translate(-width / 2, -height / 2)
    c.setFont("Helvetica-Oblique", 12)

    lines = [
        f"Complaint / Grievance Form  (Ref: {ref_no})",
        "",
        f"Name: {d['name']}",
        f"Address: {d['address'][:70]}",
        f"Contact: {d['phone']}",
        f"Date: {d['date']}",
        "",
        "Details of grievance:",
    ]
    for para in complaint_paragraphs:
        lines += textwrap.wrap(para, width=62)
        lines.append("")
    lines += [f"Signature: {d['name'].split()[0]}."]

    y = height - 55
    for line in lines:
        if y < 60:
            c.showPage()
            c.saveState()
            c.setFillColorRGB(0.94, 0.94, 0.90)
            c.rect(0, 0, width, height, fill=1, stroke=0)
            c.restoreState()
            c.saveState()
            c.translate(width / 2, height / 2)
            c.rotate(random.uniform(-2.5, 2.5))
            c.translate(-width / 2, -height / 2)
            c.setFont("Helvetica-Oblique", 12)
            y = height - 55
        c.drawString(55, y, line)
        y -= 18

    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(55, 35, "[Synthetic scan simulation — generated for testing, not a real handwritten submission]")
    c.restoreState()
    c.save()
    return fname, gt


# ---------------------------------------------------------------------------
# Scenario bundles
# ---------------------------------------------------------------------------

SCENARIOS = ["welfare_application", "land_transaction", "vendor_contract", "certificate_request", "legal_dispute"]
SCENARIO_WEIGHTS = [0.28, 0.20, 0.22, 0.15, 0.15]


def build_case(case_dir: Path, case_id: str) -> dict:
    case_dir.mkdir(parents=True, exist_ok=True)
    e = make_entity()
    scenario = random.choices(SCENARIOS, weights=SCENARIO_WEIGHTS, k=1)[0]
    files: list[dict] = []
    discrepancy = None

    def add(fname, doc_type, gt_fields):
        files.append({"filename": fname, "document_type": doc_type, "fields": gt_fields})

    if scenario == "welfare_application":
        income_app = e.annual_income
        income_cert = income_app
        if random.random() < 0.16:
            income_cert = int(income_app * random.choice([0.6, 1.6, 2.2]))
            discrepancy = {"type": "income_mismatch",
                            "description": f"Declared income in application ({money(income_app)}) does not match income certificate ({money(income_cert)})"}
        fname, gt = gen_application(e, case_dir, f"APP-{case_id}", "sanction of an income-based welfare benefit", as_txt=random.random() < 0.3)
        add(fname, "application", gt)
        fname, gt = gen_identity_document(e, case_dir, f"ID-{case_id}", as_txt=random.random() < 0.2)
        add(fname, "identity_document", gt)
        fname, gt, _ = gen_income_certificate(e, case_dir, f"INC-{case_id}", as_txt=random.random() < 0.3, income_override=income_cert)
        add(fname, "tax_form", gt)
        if random.random() < 0.4:
            fname, gt = gen_birth_certificate(e, case_dir, f"BC-{case_id}", as_txt=random.random() < 0.2)
            add(fname, "birth_certificate", gt)

    elif scenario == "land_transaction":
        land_value = random.choice([850000, 1200000, 2500000, 4200000, 7800000])
        tax_amount = random.choice([4200, 6800, 9500, 15200, 22000])
        fname, gt, _ = gen_land_record(e, case_dir, f"LR-{case_id}", as_txt=random.random() < 0.25, amount_override=land_value)
        add(fname, "land_record", gt)
        fname, gt = gen_identity_document(e, case_dir, f"ID-{case_id}", as_txt=random.random() < 0.2)
        add(fname, "identity_document", gt)
        fname, gt, _ = gen_property_tax_receipt(e, case_dir, f"PT-{case_id}", as_txt=random.random() < 0.3, amount_override=tax_amount)
        add(fname, "tax_form", gt)
        if random.random() < 0.3:
            fname, gt = gen_legal_notice(e, case_dir, f"LN-{case_id}", as_txt=random.random() < 0.4)
            add(fname, "legal_notice", gt)

    elif scenario == "vendor_contract":
        c_fname, c_gt, contract_value = gen_contract(e, case_dir, f"CT-{case_id}", as_txt=random.random() < 0.2)
        invoice_value = contract_value
        if random.random() < 0.2:
            invoice_value = contract_value + random.choice([-45000, 32000, 68000, 91000])
            discrepancy = {"type": "amount_mismatch",
                            "description": f"Invoice total ({money(invoice_value)}) does not match contract value ({money(contract_value)})"}
        add(c_fname, "contract", c_gt)
        fname, gt, _ = gen_gst_invoice(e, case_dir, f"INV-{case_id}", as_txt=random.random() < 0.25, amount_override=invoice_value)
        add(fname, "tax_form", gt)
        fname, gt = gen_identity_document(e, case_dir, f"ID-{case_id}", as_txt=random.random() < 0.2)
        add(fname, "identity_document", gt)
        if random.random() < 0.3:
            fname, gt = gen_legal_notice(e, case_dir, f"LN-{case_id}", as_txt=random.random() < 0.4)
            add(fname, "legal_notice", gt)

    elif scenario == "certificate_request":
        fname, gt = gen_birth_certificate(e, case_dir, f"BC-{case_id}", as_txt=random.random() < 0.2)
        add(fname, "birth_certificate", gt)
        fname, gt = gen_application(e, case_dir, f"APP-{case_id}", "issuance of a certified copy of the birth certificate", as_txt=random.random() < 0.3)
        add(fname, "application", gt)
        fname, gt = gen_identity_document(e, case_dir, f"ID-{case_id}", as_txt=random.random() < 0.2)
        add(fname, "identity_document", gt)

    else:  # legal_dispute
        c_fname, c_gt, _ = gen_contract(e, case_dir, f"CT-{case_id}", as_txt=random.random() < 0.2)
        add(c_fname, "contract", c_gt)
        fname, gt = gen_legal_notice(e, case_dir, f"LN-{case_id}", as_txt=random.random() < 0.35)
        add(fname, "legal_notice", gt)
        fname, gt = gen_scanned_handwritten_form(e, case_dir, f"SC-{case_id}")
        add(fname, "scanned_handwritten_form", gt)
        if random.random() < 0.35:
            fname, gt, _ = gen_land_record(e, case_dir, f"LR-{case_id}", as_txt=random.random() < 0.25)
            add(fname, "land_record", gt)

    if scenario != "legal_dispute" and random.random() < 0.12:
        fname, gt = gen_scanned_handwritten_form(e, case_dir, f"SC-{case_id}")
        add(fname, "scanned_handwritten_form", gt)

    total_fields = sum(len(f["fields"]) for f in files)
    corrupted_fields = sum(1 for f in files for fld in f["fields"] if fld["is_corrupted"])

    return {
        "case_id": case_id,
        "folder": case_dir.name,
        "scenario": scenario,
        "entity_name": e.name,
        "district": e.district,
        "uploaded_at": random_date(2, 1).strftime("%Y-%m-%d %H:%M:%S"),
        "file_count": len(files),
        "total_fields": total_fields,
        "corrupted_field_count": corrupted_fields,
        "corrupted_field_rate": round(corrupted_fields / total_fields, 3) if total_fields else 0.0,
        "files": files,
        "has_intentional_cross_document_discrepancy": discrepancy is not None,
        "cross_document_discrepancy": discrepancy,
    }


def main() -> int:
    global CORRUPT_RATE
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-cases", type=int, default=50)
    parser.add_argument("--output-dir", type=str, default="./simulated_dataset")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--corrupt-rate", type=float, default=0.10, help="Fraction of fields per document that get a realistic error (typo/OCR/date-swap/amount-slip)")
    args = parser.parse_args()

    random.seed(args.seed)
    Faker.seed(args.seed)
    CORRUPT_RATE = args.corrupt_rate

    out_root = Path(args.output_dir)
    uploads_root = out_root / "uploads"
    uploads_root.mkdir(parents=True, exist_ok=True)

    manifest = []
    for i in range(1, args.n_cases + 1):
        case_id = f"{i:04d}"
        case_dir = uploads_root / f"case_{case_id}"
        record = build_case(case_dir, case_id)
        manifest.append(record)
        if i % 10 == 0:
            print(f"[generate_simulated_dataset] {i}/{args.n_cases} cases generated")

    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    with (out_root / "manifest.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "folder", "scenario", "entity_name", "district", "uploaded_at",
                          "file_count", "filenames", "total_fields", "corrupted_field_count", "corrupted_field_rate",
                          "has_intentional_cross_document_discrepancy", "cross_document_discrepancy_description"])
        for r in manifest:
            writer.writerow([
                r["case_id"], r["folder"], r["scenario"], r["entity_name"], r["district"], r["uploaded_at"],
                r["file_count"], "; ".join(fl["filename"] for fl in r["files"]),
                r["total_fields"], r["corrupted_field_count"], r["corrupted_field_rate"],
                r["has_intentional_cross_document_discrepancy"],
                r["cross_document_discrepancy"]["description"] if r["cross_document_discrepancy"] else "",
            ])

    total_files = sum(r["file_count"] for r in manifest)
    total_fields = sum(r["total_fields"] for r in manifest)
    total_corrupted = sum(r["corrupted_field_count"] for r in manifest)
    n_cross_doc = sum(1 for r in manifest if r["has_intentional_cross_document_discrepancy"])
    scenario_counts: dict[str, int] = {}
    for r in manifest:
        scenario_counts[r["scenario"]] = scenario_counts.get(r["scenario"], 0) + 1

    print(f"\nDone. {len(manifest)} case folders, {total_files} files.")
    print(f"Fields: {total_fields} total, {total_corrupted} corrupted "
          f"({total_corrupted / total_fields:.1%} — target was {args.corrupt_rate:.0%} per document).")
    print(f"{n_cross_doc} cases also have a larger, deliberate cross-document discrepancy.")
    print(f"Scenario mix: {scenario_counts}")
    print(f"Output: {out_root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
