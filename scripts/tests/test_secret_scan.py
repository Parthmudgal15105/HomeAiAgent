from scripts.secret_scan import scan_text


def test_detects_sensitive_files_without_printing_contents():
    assert scan_text(".env", "secret-value")[0]["rule"] == "private-runtime-file"
    assert scan_text(".local-access.txt", "secret-value")
    assert not scan_text(".env.example", "PASSWORD=\n")


def test_detects_token_literals_and_bound_credentials_without_echoing_values():
    token = "ghp_" + "Z" * 30
    findings = scan_text("config.py", 'TOKEN="' + token + '"')
    assert findings == [{"path": "config.py", "line": 1, "rule": "provider-token"}]
    assert token not in str(findings)
    assert scan_text("config.txt", "postgresql://alice:" + "real-password" + "@db/app")
    for google_key in ('AIza' + 'Z' * 35, 'AQ.' + 'Z' * 48):
        result = scan_text('config.py', google_key)
        assert result == [{"path": "config.py", "line": 1, "rule": "provider-token"}]
        assert google_key not in str(result)


def test_explicit_test_fixtures_and_template_substitutions_are_allowed():
    assert not scan_text("tests/test.py", 'token="' + "ghp_" + "Z" * 30 + '" # secret-scan: fixture')
    assert not scan_text(".env.example", "DATABASE_URL=postgresql://aiops:REPLACE@localhost/aiops")
    assert not scan_text("compose.yml", "DATABASE_URL=postgresql://aiops:${POSTGRES_PASSWORD}@postgres/aiops")


def test_private_key_and_runtime_artifacts_are_rejected():
    assert scan_text("key.txt", "-----BEGIN " + "PRIVATE KEY-----")
    assert scan_text("data/model.bin", "runtime")
    assert scan_text("backups/config.json", "runtime")
