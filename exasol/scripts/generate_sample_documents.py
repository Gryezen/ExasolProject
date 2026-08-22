"""
scripts/generate_sample_documents.py — generates the synthetic citizen
document corpus under data/sample/, in place of an external dataset.

Why synthetic instead of FUNSD / CORD / RVL-CDIP / data.gov.in:
  - FUNSD's real data lives at guillaumejaume.github.io/FUNSD/dataset.zip,
    CORD's on Hugging Face, RVL-CDIP only on Kaggle, and data.gov.in is its
    own host — none of those hosts were reachable from the sandbox this
    project was built in (network allowlist), so nothing could actually be
    downloaded into this repo.
  - Even where reachable, none of them match this project's schema: FUNSD
    is 1980s-90s US tobacco-industry forms, CORD is Indonesian retail
    receipts. Neither has a birth certificate, income certificate, or land
    record in it, and FUNSD's license is non-commercial/research-only,
    which is a bad fit for a redistributable submission repo anyway.
  - The project's own ideation notes (see Civic_Pulse-style planning docs)
    explicitly recommend NOT using a generic dataset for a hackathon demo:
    design the sample corpus around the questions you want the chat agent
    to be able to answer, and make sure a few documents are deliberately
    linked (so cross-document reasoning has something to find) and a few
    are deliberately messy (so the confidence gate has something to catch).

This script generates each document as a rendered PNG (not a real scan —
no attempt to fake authenticity), across the seven document types the
project's rule-based relationship matcher and extraction schema already
know about (see agents/relationships.py, agents/extraction.py):

    birth_certificate, income_certificate, welfare_application,
    land_record, property_tax_receipt, complaint, contractor_bid

A handful of documents are generated as intentionally linked pairs with
one field deliberately mismatched, so the demo scenario in the README
("upload two related documents, watch reasoning catch the mismatch, watch
the action agent draft a clarification") works out of the box without
manual data entry.

Usage:
    python3 scripts/generate_sample_documents.py [--count-per-type N] [--seed N]

Regenerating is safe — this script only ever writes into data/sample/ and
overwrites its own prior output.
"""

import argparse
import os
import random
import textwrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_MONO = os.path.join(FONT_DIR, "DejaVuSansMono.ttf")

OUT_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample")

DISTRICTS = ["Chennai", "Coimbatore", "Madurai", "Salem", "Tiruchirappalli", "Erode"]
FIRST_NAMES = ["Ravi", "Priya", "Arun", "Lakshmi", "Suresh", "Meena", "Karthik", "Divya", "Vijay", "Anitha"]
LAST_NAMES = ["Kumar", "Raman", "Iyer", "Nair", "Pillai", "Subramaniam", "Rajan", "Krishnan"]
OCCUPATIONS = ["Daily wage labourer", "Auto driver", "Small shop owner", "Farmer", "Domestic worker", "Tailor"]
COMPANY_SUFFIX = ["Constructions", "Infra Pvt Ltd", "Builders", "Engineering Works", "Contractors"]
PROJECTS = ["Road Widening Phase 2", "Municipal Water Pipeline", "School Building Renovation", "Bridge Repair Works"]
COMPLAINT_KINDS = [
    ("Road damage", "Large pothole causing accidents near the main junction."),
    ("Water supply issue", "No water supply for the past 5 days in the ward."),
    ("Streetlight not working", "Streetlight has been non-functional for three weeks."),
    ("Garbage collection complaint", "Garbage has not been collected from the street in over a week."),
]


def _name(rng):
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _cert_no(rng, prefix):
    return f"{prefix}-{rng.randint(100000, 999999)}"


def _date(rng, year_lo=2015, year_hi=2026):
    year = rng.randint(year_lo, year_hi)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return f"{day:02d}/{month:02d}/{year}"


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------

def _new_canvas(width=900, height=1150):
    return Image.new("RGB", (width, height), color="white")


def _draw_letterhead(draw, title, subtitle, width):
    draw.rectangle([(0, 0), (width, 6)], fill=(20, 60, 50))
    f_title = ImageFont.truetype(FONT_BOLD, 26)
    f_sub = ImageFont.truetype(FONT_REGULAR, 13)
    draw.text((width / 2, 34), title, font=f_title, fill=(20, 30, 30), anchor="mm")
    draw.text((width / 2, 62), subtitle, font=f_sub, fill=(90, 90, 90), anchor="mm")
    draw.line([(60, 82), (width - 60, 82)], fill=(180, 180, 180), width=1)


def _draw_kv_block(draw, rows, x, y, label_width=230, line_height=34, font_size=15):
    f_label = ImageFont.truetype(FONT_REGULAR, font_size)
    f_value = ImageFont.truetype(FONT_BOLD, font_size)
    for label, value in rows:
        draw.text((x, y), f"{label}:", font=f_label, fill=(70, 70, 70))
        draw.text((x + label_width, y), str(value), font=f_value, fill=(15, 15, 15))
        y += line_height
    return y


def _draw_stamp(img, text, color, center):
    stamp = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stamp)
    sd.ellipse([(6, 6), (214, 214)], outline=color + (200,), width=6)
    sd.ellipse([(20, 20), (200, 200)], outline=color + (140,), width=2)
    f = ImageFont.truetype(FONT_BOLD, 24)
    sd.text((110, 110), text, font=f, fill=color + (210,), anchor="mm")
    stamp = stamp.rotate(random.uniform(-18, 18), expand=True)
    img.paste(stamp, (center[0] - stamp.width // 2, center[1] - stamp.height // 2), stamp)


def _draw_signature(draw, x, y):
    points = [(x, y)]
    for i in range(1, 8):
        points.append((x + i * 18, y + random.randint(-14, 14)))
    draw.line(points, fill=(20, 20, 90), width=2, joint="curve")
    f = ImageFont.truetype(FONT_REGULAR, 11)
    draw.text((x, y + 18), "Authorised Signatory", font=f, fill=(90, 90, 90))


def _apply_messiness(img, rng, level):
    """level: 'clean' | 'stamped' | 'noisy' | 'rotated_low_quality'"""
    if level == "stamped":
        _draw_stamp(img, "VERIFIED", (30, 110, 60), (int(img.width * 0.78), int(img.height * 0.15)))
    elif level == "noisy":
        _draw_stamp(img, "PENDING", (170, 120, 20), (int(img.width * 0.78), int(img.height * 0.15)))
        img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
    elif level == "rotated_low_quality":
        img = img.rotate(rng.uniform(-4, 4), expand=True, fillcolor="white")
        img = img.filter(ImageFilter.GaussianBlur(radius=1.1))
        # Simulate a low-quality phone photo re-save.
        small = img.resize((img.width // 2, img.height // 2))
        img = small.resize((img.width, img.height))
    return img


def _save(img, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.convert("RGB").save(path, quality=88)


# ----------------------------------------------------------------------
# Document type generators — each returns (filename, PIL.Image, facts)
# facts is a dict of the "true" field values, used only to print a
# manifest afterwards so a demo presenter knows what to expect.
# ----------------------------------------------------------------------

def gen_birth_certificate(rng, idx, messiness):
    name = _name(rng)
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    district = rng.choice(DISTRICTS)
    _draw_letterhead(d, "BIRTH CERTIFICATE", f"Office of the Registrar of Births & Deaths, {district}", img.width)
    facts = {
        "certificate_number": _cert_no(rng, "BC"),
        "name": name,
        "date_of_birth": _date(rng, 1970, 2024),
        "gender": rng.choice(["Male", "Female"]),
        "father_name": _name(rng),
        "mother_name": _name(rng),
        "place_of_birth": f"{district} Government Hospital",
    }
    y = _draw_kv_block(d, [
        ("Certificate No", facts["certificate_number"]),
        ("Name", facts["name"]),
        ("Date of Birth", facts["date_of_birth"]),
        ("Gender", facts["gender"]),
        ("Father's Name", facts["father_name"]),
        ("Mother's Name", facts["mother_name"]),
        ("Place of Birth", facts["place_of_birth"]),
    ], 70, 130)
    _draw_signature(d, 70, y + 60)
    img = _apply_messiness(img, rng, messiness)
    return f"birth_certificate_{idx:03d}.png", img, facts


def gen_income_certificate(rng, idx, messiness, name=None, income=None):
    name = name or _name(rng)
    income = income if income is not None else rng.choice([80000, 120000, 150000, 180000, 220000])
    district = rng.choice(DISTRICTS)
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    _draw_letterhead(d, "INCOME CERTIFICATE", f"Revenue Department, {district} District", img.width)
    facts = {
        "certificate_number": _cert_no(rng, "IC"),
        "name": name,
        "annual_income": str(income),
        "occupation": rng.choice(OCCUPATIONS),
    }
    y = _draw_kv_block(d, [
        ("Certificate No", facts["certificate_number"]),
        ("Name", facts["name"]),
        ("Annual Income (Rs.)", facts["annual_income"]),
        ("Occupation", facts["occupation"]),
        ("District", district),
        ("Issue Date", _date(rng, 2024, 2026)),
    ], 70, 130)
    _draw_signature(d, 70, y + 60)
    img = _apply_messiness(img, rng, messiness)
    return f"income_certificate_{idx:03d}.png", img, facts


def gen_welfare_application(rng, idx, messiness, name=None, income=None, district=None):
    name = name or _name(rng)
    income = income if income is not None else rng.choice([300000, 400000, 500000, 600000])
    district = district or rng.choice(DISTRICTS)
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    scheme = rng.choice(["Old Age Pension Scheme", "Housing Assistance Scheme", "Farmer Support Scheme", "Widow Pension Scheme"])
    _draw_letterhead(d, "WELFARE SCHEME APPLICATION", f"{district} District Social Welfare Office", img.width)
    facts = {
        "application_id": _cert_no(rng, "WA"),
        "citizen_name": name,
        "income": str(income),
        "family_members": str(rng.randint(2, 6)),
        "district": district,
        "scheme": scheme,
    }
    y = _draw_kv_block(d, [
        ("Application ID", facts["application_id"]),
        ("Citizen Name", facts["citizen_name"]),
        ("Declared Income (Rs.)", facts["income"]),
        ("Family Members", facts["family_members"]),
        ("District", facts["district"]),
        ("Scheme Applied For", facts["scheme"]),
    ], 70, 130)
    _draw_signature(d, 70, y + 60)
    img = _apply_messiness(img, rng, messiness)
    return f"welfare_application_{idx:03d}.png", img, facts


def gen_land_record(rng, idx, messiness, owner=None):
    owner = owner or _name(rng)
    district = rng.choice(DISTRICTS)
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    _draw_letterhead(d, "LAND OWNERSHIP RECORD", f"Survey & Settlement Department, {district}", img.width)
    survey_no = f"{rng.randint(80, 400)}/{rng.randint(1, 20)}"
    facts = {
        "owner_name": owner,
        "survey_number": survey_no,
        "area_sqft": str(rng.randint(800, 5000)),
        "village": f"{rng.choice(['Perungudi', 'Velachery', 'Anna Nagar', 'Thiruvanmiyur', 'Adyar'])}",
        "district": district,
    }
    y = _draw_kv_block(d, [
        ("Owner Name", facts["owner_name"]),
        ("Survey Number", facts["survey_number"]),
        ("Area (sq ft)", facts["area_sqft"]),
        ("Village", facts["village"]),
        ("District", facts["district"]),
    ], 70, 130)
    _draw_signature(d, 70, y + 60)
    img = _apply_messiness(img, rng, messiness)
    return f"land_record_{idx:03d}.png", img, facts


def gen_property_tax_receipt(rng, idx, messiness, owner=None):
    owner = owner or _name(rng)
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    _draw_letterhead(d, "PROPERTY TAX RECEIPT", "Municipal Corporation — Revenue Section", img.width)
    facts = {
        "owner_name": owner,
        "property_id": f"PID-{rng.randint(10000, 99999)}",
        "amount_paid": str(rng.choice([3200, 4500, 5100, 6800, 7200])),
        "year": str(rng.choice([2023, 2024, 2025, 2026])),
    }
    y = _draw_kv_block(d, [
        ("Owner Name", facts["owner_name"]),
        ("Property ID", facts["property_id"]),
        ("Amount Paid (Rs.)", facts["amount_paid"]),
        ("Assessment Year", facts["year"]),
    ], 70, 130)
    _draw_signature(d, 70, y + 60)
    img = _apply_messiness(img, rng, messiness)
    return f"property_tax_receipt_{idx:03d}.png", img, facts


def gen_complaint(rng, idx, messiness):
    name = _name(rng)
    kind, desc = rng.choice(COMPLAINT_KINDS)
    district = rng.choice(DISTRICTS)
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    _draw_letterhead(d, "CITIZEN COMPLAINT", f"Public Grievance Redressal — {district}", img.width)
    facts = {
        "complaint_id": f"CG-{rng.randint(100000, 999999)}",
        "citizen_name": name,
        "department": rng.choice(["Public Works Department", "Water Board", "Electricity Board", "Sanitation Department"]),
        "description": desc,
        "district": district,
        "priority": rng.choice(["Low", "Medium", "High"]),
    }
    y = _draw_kv_block(d, [
        ("Complaint ID", facts["complaint_id"]),
        ("Citizen Name", facts["citizen_name"]),
        ("Department", facts["department"]),
        ("District", facts["district"]),
        ("Priority", facts["priority"]),
    ], 70, 130)
    f_label = ImageFont.truetype(FONT_REGULAR, 15)
    d.text((70, y + 10), "Description:", font=f_label, fill=(70, 70, 70))
    f_body = ImageFont.truetype(FONT_REGULAR, 14)
    wrapped = textwrap.fill(desc, width=60)
    d.multiline_text((70, y + 36), wrapped, font=f_body, fill=(20, 20, 20), spacing=6)
    _draw_signature(d, 70, y + 130)
    img = _apply_messiness(img, rng, messiness)
    return f"complaint_{idx:03d}.png", img, facts


def gen_contractor_bid(rng, idx, messiness):
    company = f"{rng.choice(LAST_NAMES)} {rng.choice(COMPANY_SUFFIX)}"
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    _draw_letterhead(d, "CONTRACTOR BID SUBMISSION", "Public Works Department — Tender Cell", img.width)
    facts = {
        "company_name": company,
        "bid_amount": str(rng.choice([8500000, 11200000, 11800000, 12300000, 15600000])),
        "project_name": rng.choice(PROJECTS),
        "experience_years": str(rng.randint(1, 20)),
    }
    y = _draw_kv_block(d, [
        ("Company Name", facts["company_name"]),
        ("Project", facts["project_name"]),
        ("Bid Amount (Rs.)", facts["bid_amount"]),
        ("Experience (years)", facts["experience_years"]),
    ], 70, 130)
    _draw_signature(d, 70, y + 60)
    img = _apply_messiness(img, rng, messiness)
    return f"contractor_bid_{idx:03d}.png", img, facts


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------

_MESSINESS_CYCLE = ["clean", "clean", "stamped", "noisy", "rotated_low_quality"]

SIMPLE_TYPES = {
    "birth_certificate": gen_birth_certificate,
    "complaint": gen_complaint,
    "contractor_bid": gen_contractor_bid,
}


def generate(count_per_type: int, seed: int):
    rng = random.Random(seed)
    manifest_lines = []

    def messiness_for(i):
        return _MESSINESS_CYCLE[i % len(_MESSINESS_CYCLE)]

    for type_name, fn in SIMPLE_TYPES.items():
        for i in range(count_per_type):
            filename, img, facts = fn(rng, i + 1, messiness_for(i))
            path = os.path.join(OUT_ROOT, type_name, filename)
            _save(img, path)
            manifest_lines.append(f"{type_name}/{filename}: {facts}")

    # Linked-pair categories: generate as matched sets so the rule-based
    # relationship matcher in agents/relationships.py has real pairs to
    # find, with a deliberate mismatch on roughly a third of them so the
    # reasoning agent has something to flag.
    for i in range(count_per_type):
        name = _name(rng)
        income = rng.choice([80000, 120000, 150000, 180000])
        mismatch = (i % 3 == 0)
        welfare_income = income * rng.choice([3, 4]) if mismatch else income + rng.choice([-5000, 0, 5000])

        fn1, img1, facts1 = gen_income_certificate(rng, i + 1, messiness_for(i), name=name, income=income)
        path1 = os.path.join(OUT_ROOT, "income_certificate", fn1)
        _save(img1, path1)
        manifest_lines.append(f"income_certificate/{fn1}: {facts1}")

        fn2, img2, facts2 = gen_welfare_application(
            rng, i + 1, messiness_for(i + 1), name=name, income=welfare_income, district=rng.choice(DISTRICTS)
        )
        path2 = os.path.join(OUT_ROOT, "welfare_application", fn2)
        _save(img2, path2)
        tag = " [DELIBERATE MISMATCH vs income_certificate]" if mismatch else " [consistent with income_certificate]"
        manifest_lines.append(f"welfare_application/{fn2}: {facts2}{tag}")

    for i in range(count_per_type):
        owner = _name(rng)
        fn1, img1, facts1 = gen_land_record(rng, i + 1, messiness_for(i), owner=owner)
        path1 = os.path.join(OUT_ROOT, "land_record", fn1)
        _save(img1, path1)
        manifest_lines.append(f"land_record/{fn1}: {facts1}")

        fn2, img2, facts2 = gen_property_tax_receipt(rng, i + 1, messiness_for(i + 1), owner=owner)
        path2 = os.path.join(OUT_ROOT, "property_tax_receipt", fn2)
        _save(img2, path2)
        manifest_lines.append(f"property_tax_receipt/{fn2}: {facts2}")

    manifest_path = os.path.join(OUT_ROOT, "MANIFEST.txt")
    with open(manifest_path, "w") as f:
        f.write(
            "Synthetic sample corpus — generated by scripts/generate_sample_documents.py\n"
            "Ground-truth field values below are for verifying extraction accuracy during\n"
            "the demo; they are not derived from any real person or real records.\n\n"
        )
        f.write("\n".join(manifest_lines) + "\n")

    total = len(manifest_lines)
    print(f"Generated {total} documents under {OUT_ROOT}")
    print(f"Manifest written to {manifest_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count-per-type", type=int, default=6, help="Documents per category (default: 6)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()
    generate(args.count_per_type, args.seed)
