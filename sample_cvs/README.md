# Sample CVs (synthetic)

All people are fictional: emails use `example.com`, phone numbers are `90000001xx`. Regenerate with `python backend/scripts/make_sample_cvs.py`.

Upload **everything except `sana_iqbal_kyc.pdf`** to the *Senior Java Developer* requisition (Uploads tab), and `sana_iqbal_kyc.pdf` to *KYC Analyst*. Expected results:

| File | What it demonstrates |
|---|---|
| `vikram_sethi_table_cv.docx` | DOCX where details sit in a table; scores 90 |
| `neha_kapoor.pdf` | Text PDF; scores 80 (45-day notice, "REST APIs" skill) |
| `karan_malhotra.pdf` | Non-matching profile stays listed with a low score; "Immediate joiner" read as 0 days notice |
| `ritika_bansal_duplicate.docx` | Same email as seeded candidate CND-91022, so it lands in **Duplicates**, not the ranking |
| `scanned_amit_verma.pdf` | Image-only PDF: needs Tesseract OCR (fails with a clear per-file message if Tesseract is missing) |
| `corrupt_example.pdf` | Corrupt file: that document fails with its own error and a Retry button; the rest of the batch continues |
| `sample_jd.txt` | Paste into the Requisitions form to try JD extraction (needs an LLM key) |
