from app.main import score
def test_score_excludes_identity_and_matches_evidence():
    card={"criteria":[{"label":"Skills","type":"skills","values":["Java"],"weight":100}]}
    a={"skills":["Java"],"experience":0,"notice_days":90,"raw_text":"Java developer"}
    b={**a,"name":"Different name","age":99}
    assert score(a,card)[0]==score(b,card)[0]==100
    assert score(a,card)[1]["Skills"]["quote"]
