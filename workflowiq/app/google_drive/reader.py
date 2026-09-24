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


_COMPANY_SUFFIX_RE = re.compile(r"\s*[,.]?\s*(inc|llc|ltd|corp|co|company)\.?\s*$", re.IGNORECASE)


def _normalize_company_name(name: str) -> str:
    """Same normalization SOPBot's n8n workflow uses for Drive folder
    matching, so "Acme Inc" and "Acme" resolve to the same folder here too."""
    return _COMPANY_SUFFIX_RE.sub("", (name or "").strip().lower()).strip()


def find_customer_sop_docs(company_name: str) -> list[dict]:
    """Finds the customer's company folder under the shared SOPs root (same
    folder structure SOPBot's voice pipeline creates/reuses per company - see
    n8n workflow nodes 15a-15e) and lists every Google Doc inside it.

    Returns [] if no company name is available or no matching folder exists -
    callers should fall back to manual URL entry in that case, this is meant
    to save the operator a manual Drive search, not be a hard requirement.
    """
    root_folder_id = os.environ.get("SOPBOT_DRIVE_ROOT_FOLDER_ID", "")
    if not company_name or not root_folder_id:
        return []

    creds = _build_credentials()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    target_normalized = _normalize_company_name(company_name)

    folders = drive.files().list(
        q=f"'{root_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields="files(id, name)",
        pageSize=1000,
    ).execute().get("files", [])

    match = next((f for f in folders if _normalize_company_name(f["name"]) == target_normalized), None)
    if not match:
        return []

    docs = drive.files().list(
        q=f"'{match['id']}' in parents and mimeType = 'application/vnd.google-apps.document' and trashed = false",
        fields="files(id, name, createdTime)",
        pageSize=1000,
        orderBy="createdTime desc",
    ).execute().get("files", [])

    return [
        {"name": d["name"], "url": f"https://docs.google.com/document/d/{d['id']}/edit"}
        for d in docs
    ]
