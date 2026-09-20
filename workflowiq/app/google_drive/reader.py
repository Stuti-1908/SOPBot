"""Fetch SOP text from a Google Doc via the Drive/Docs API using a Service Account."""
from __future__ import annotations
import os
import re
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents.readonly",
]

_DOC_ID_RE = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")


def _get_doc_id(url: str) -> str:
    m = _DOC_ID_RE.search(url)
    if not m:
        raise ValueError(f"Cannot extract document ID from URL: {url}")
    return m.group(1)


def _build_credentials():
    sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_path or not os.path.exists(sa_path):
        raise EnvironmentError(
            "GOOGLE_SERVICE_ACCOUNT_JSON must point to a valid service account key file."
        )
    return service_account.Credentials.from_service_account_file(sa_path, scopes=SCOPES)


def fetch_sop_from_drive(url: str) -> str:
    """Return plain text content of a Google Doc."""
    doc_id = _get_doc_id(url)
    creds = _build_credentials()
    docs = build("docs", "v1", credentials=creds, cache_discovery=False)

    doc = docs.documents().get(documentId=doc_id).execute()
    return _extract_text(doc)


def upload_pdf_public(pdf_path: str, name: str) -> str:
    """Uploads a PDF to Drive, makes it link-shareable, and returns a direct
    download URL. Mirrors the sharing pattern already proven in the SOPBot
    voice pipeline (n8n's "Share Doc (Anyone Reader)" nodes) - same
    role: 'reader', type: 'anyone' permission, just via the Drive API
    directly instead of an HTTP node."""
    from googleapiclient.http import MediaFileUpload

    creds = _build_credentials()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    media = MediaFileUpload(pdf_path, mimetype="application/pdf")
    file = drive.files().create(body={"name": name}, media_body=media, fields="id").execute()
    file_id = file["id"]

    drive.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()

    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _extract_text(doc: dict) -> str:
    """Walk the document body and extract plain text."""
    parts: list[str] = []
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for pe in paragraph.get("elements", []):
            text_run = pe.get("textRun")
            if text_run:
                parts.append(text_run.get("content", ""))
    return "".join(parts).strip()
