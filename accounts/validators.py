"""
Reusable validators for the KYC/certificate file uploads (driver Aadhar,
license, vehicle RC; farmer ISO certificate). Keeps every upload field on
the same size cap and allowed-extension list instead of trusting whatever
the browser sends.
"""
import io
import os

from django.core.exceptions import ValidationError

MAX_UPLOAD_SIZE_MB = 5
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png')


def validate_kyc_document(uploaded_file):
    """Rejects files that aren't a PDF/JPG/PNG or are over the size cap."""
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError(
            f'Unsupported file type "{ext or "unknown"}". Please upload a PDF, JPG, or PNG.'
        )
    if uploaded_file.size > MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError(f'File is too large. Maximum size is {MAX_UPLOAD_SIZE_MB} MB.')


# ---------------------------------------------------------------------------
# Content check: is the uploaded license_document actually a driving licence?
#
# Uses CLIP (openai/clip-vit-base-patch32) for zero-shot image classification.
# No training/fine-tuning needed — we just ask CLIP which of a fixed list of
# text labels the image looks most like, and reject if the top match isn't
# "driving license".
#
# The model is loaded once per process (module-level cache) since loading it
# fresh on every upload would be extremely slow.
# ---------------------------------------------------------------------------

_CLIP_MODEL = None
_CLIP_PROCESSOR = None

DL_CANDIDATE_LABELS = [
    'a driving license card',
    'an Aadhar identity card',
    'a PAN card',
    'a vehicle registration certificate (RC book)',
    'a passport',
    'a random photo unrelated to any document',
    'a blank or mostly empty page',
]
DRIVING_LICENSE_LABEL = 'a driving license card'

# Reject if CLIP isn't at least this confident the image is a driving licence.
# Lower this if genuine licenses are getting rejected too often; raise it if
# wrong documents are slipping through.
DL_CONFIDENCE_THRESHOLD = 0.40


def _get_clip():
    """Lazily load and cache the CLIP model + processor (heavy, ~600MB)."""
    global _CLIP_MODEL, _CLIP_PROCESSOR
    if _CLIP_MODEL is None:
        from transformers import CLIPModel, CLIPProcessor
        _CLIP_MODEL = CLIPModel.from_pretrained('openai/clip-vit-base-patch32')
        _CLIP_PROCESSOR = CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')
    return _CLIP_MODEL, _CLIP_PROCESSOR


def _load_first_page_as_image(uploaded_file):
    """Returns a PIL.Image for both image uploads and PDF uploads (first page)."""
    from PIL import Image

    ext = os.path.splitext(uploaded_file.name)[1].lower()
    uploaded_file.seek(0)
    raw = uploaded_file.read()
    uploaded_file.seek(0)  # leave the file pointer as we found it

    if ext == '.pdf':
        import fitz  # PyMuPDF
        doc = fitz.open(stream=raw, filetype='pdf')
        page = doc.load_page(0)
        pix = page.get_pixmap()
        return Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')

    return Image.open(io.BytesIO(raw)).convert('RGB')


def validate_is_driving_license(uploaded_file):
    """
    Rejects the upload unless CLIP's top guess for the image is
    "a driving license card" with at least DL_CONFIDENCE_THRESHOLD confidence.

    Runs AFTER validate_kyc_document in the field's validators list, so by
    the time this runs we already know it's a PDF/JPG/PNG under the size cap.
    """
    try:
        image = _load_first_page_as_image(uploaded_file)
    except Exception:
        raise ValidationError('Could not read this file. Please upload a clear photo or scan.')

    model, processor = _get_clip()

    inputs = processor(text=DL_CANDIDATE_LABELS, images=image, return_tensors='pt', padding=True)
    outputs = model(**inputs)
    probs = outputs.logits_per_image.softmax(dim=1)[0]

    scores = {label: float(probs[i]) for i, label in enumerate(DL_CANDIDATE_LABELS)}
    top_label = max(scores, key=scores.get)
    top_score = scores[top_label]

    if top_label != DRIVING_LICENSE_LABEL or top_score < DL_CONFIDENCE_THRESHOLD:
        raise ValidationError(
            'This file doesn\u2019t look like a driving license. Please upload a clear photo '
            'or scan of your driving license (front side).'
        )
