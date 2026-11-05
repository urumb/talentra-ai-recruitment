from app.main import score, profile, find_experience

CARD = {"criteria": [{"label": "Skills", "type": "skills", "values": ["Java", "Kafka"], "weight": 60},
                     {"label": "Exp", "type": "experience", "min": 5, "weight": 25},
                     {"label": "Notice", "type": "notice", "max": 60, "weight": 15}]}

def test_score_excludes_identity_and_matches_evidence():
    card = {"criteria": [{"label": "Skills", "type": "skills", "values": ["Java"], "weight": 100}]}
    a = {"skills": ["Java"], "experience": 0, "notice_days": 90, "raw_text": "Java developer"}
    b = {**a, "name": "Different name", "age": 99, "gender": "F", "marital_status": "x"}
    assert score(a, card)[0] == score(b, card)[0] == 100
    assert score(a, card)[1]["Skills"]["quote"]

def test_unknown_when_absent_and_never_invented():
    text = "Jane\nBackend engineer. Worked with Java."
    s, ev = score({"raw_text": text, "skills": ["Java"], "source_document": "a.pdf"}, CARD)
    assert ev["Exp"]["status"] == "unknown" and ev["Exp"]["quote"] is None and ev["Exp"]["page"] is None
    assert ev["Notice"]["status"] == "unknown"
    assert ev["Skills"]["status"] == "partial" and ev["Skills"]["matched"] == ["Java"]
    assert s == 30.0

def test_page_numbers_only_for_pdf_and_are_real():
    text = "Intro\fSecond page: Java and Kafka here\f"
    ev = score({"raw_text": text, "skills": [], "source_document": "x.pdf"}, CARD)[1]["Skills"]
    assert ev["page"] == 2 and "Kafka" in ev["quote"] or "Java" in ev["quote"]
    assert score({"raw_text": text, "skills": [], "source_document": "x.docx"}, CARD)[1]["Skills"]["page"] is None

def test_deterministic():
    c = {"raw_text": "Java Kafka 8 years of experience. Notice period: 30 days", "skills": [], "source_document": "a.pdf"}
    assert score(c, CARD) == score(dict(c), CARD) and score(c, CARD)[0] == 100

def test_profile_extraction():
    p = profile("Asha Rao\nasha@x.com +91 9876543210\n7 years of experience in Java\nImmediate joiner")
    assert (p["email"], p["phone"], p["experience"], p["notice_days"], p["name"]) == ("asha@x.com", "9876543210", 7.0, 0, "Asha Rao")
    q = profile("Some text with no facts")
    assert q["email"] is None and q["experience"] is None and q["notice_days"] is None and q["confidence"] == "Low"

def test_experience_requires_experience_context():
    assert find_experience("I lived in Pune for 10 years")[0] is None
