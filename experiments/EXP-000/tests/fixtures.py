"""Fabricated conversations. No real client data is used anywhere in these tests.

Every identifier here is invented or a well-known test value (4111111111111111 is the standard
test Visa number, example.com is reserved by RFC 2606).
"""

ROWS = [
    {"conv_id": "ARTH-1", "from": "Priya Sharma", "sent_at": "2025-08-12 19:42:13",
     "body": "Hi, this is Priya Sharma. My budget is around 40 lakhs.", "speaker_role": "customer"},
    {"conv_id": "ARTH-1", "from": "Arthryx Desk", "sent_at": "2025-08-12 19:43:01",
     "body": "Thanks Priya. Reach me on 9876543210 or desk@example.com.", "speaker_role": "agent"},
    {"conv_id": "ARTH-1", "from": "Priya Sharma", "sent_at": "2025-08-12 19:45:00",
     "body": "Actually it might stretch to 45. Transfer 40k to a/c 123456789012, IFSC HDFC0001234.",
     "speaker_role": "customer"},
    {"conv_id": "ARTH-1", "from": "Priya Sharma", "sent_at": "not a date",
     "body": "Flat 4B, MG Road, Bengaluru 560001. UPI priya@okaxis, card 4111111111111111.",
     "speaker_role": "customer"},
    {"conv_id": "ARTH-2", "from": "Priya Sharma", "sent_at": "2025-09-01 10:00:00",
     "body": "Priya here again, different thread.", "speaker_role": "customer"},
    {"conv_id": "ARTH-2", "from": "Unknown Bot", "sent_at": "2025-09-01 10:00:05",
     "body": "Automated reply.", "speaker_role": ""},
]

COLUMNS_YAML = """
conversation_id: conv_id
speaker: from
timestamp: sent_at
text: body
role: speaker_role
"""

COLUMNS_YAML_NO_ROLE = """
conversation_id: conv_id
speaker: from
timestamp: sent_at
text: body
"""


def write_csv(path, rows=None):
    import csv
    rows = ROWS if rows is None else rows
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_json(path, rows=None):
    import json
    rows = ROWS if rows is None else rows
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def write_xlsx(path, rows=None):
    from openpyxl import Workbook
    rows = ROWS if rows is None else rows
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(rows[0]))
    for row in rows:
        sheet.append([row[k] for k in rows[0]])
    workbook.save(path)
    return path


def write_columns(path, body=COLUMNS_YAML):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path
