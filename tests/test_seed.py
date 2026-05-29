def test_seed_users_data_has_required_fields():
    from seed.seed_users import USERS

    for u in USERS:
        assert "email" in u
        assert "role" in u
        assert "password" in u


def test_seed_areas_data_quality():
    from seed.seed_areas import AREAS

    for a in AREAS:
        assert a["data_quality"] == "estimated"
        assert a["source"] == "base demonstrativa acadêmica"


def test_seed_incidents_have_required_codes():
    from seed.seed_incidents import INCIDENTS

    codes = [i["code"] for i in INCIDENTS]
    assert "IGN-CE-2026-0041" in codes


def test_seed_areas_count():
    from seed.seed_areas import AREAS

    assert len(AREAS) == 8


def test_seed_reports_count():
    from seed.seed_reports import REPORTS_DATA

    assert len(REPORTS_DATA) == 12


def test_seed_users_count():
    from seed.seed_users import USERS

    assert len(USERS) == 4


def test_seed_teams_count():
    from seed.seed_teams import TEAMS

    assert len(TEAMS) == 6


def test_seed_incidents_count():
    from seed.seed_incidents import INCIDENTS

    assert len(INCIDENTS) == 5


def test_seed_resources_count():
    from seed.seed_resources import RESOURCES

    assert len(RESOURCES) == 8


def test_seed_missions_count():
    from seed.seed_missions import MISSIONS

    assert len(MISSIONS) == 3


def test_seed_all_imports():
    from seed.seed_all import run_all  # noqa: F401
    from seed.seed_areas import seed_areas  # noqa: F401
    from seed.seed_esg import seed_esg  # noqa: F401
    from seed.seed_incidents import seed_incidents  # noqa: F401
    from seed.seed_missions import seed_missions  # noqa: F401
    from seed.seed_reports import seed_reports  # noqa: F401
    from seed.seed_resources import seed_resources  # noqa: F401
    from seed.seed_teams import seed_teams  # noqa: F401
    from seed.seed_users import seed_users  # noqa: F401


def test_seed_reports_has_converted_status():
    from seed.seed_reports import REPORTS_DATA

    statuses = [r["status"] for r in REPORTS_DATA]
    assert "converted" in statuses
    assert statuses.count("validated") >= 3
    assert statuses.count("pending") >= 4
    assert statuses.count("discarded") >= 2


def test_seed_reports_has_anonymous():
    from seed.seed_reports import REPORTS_DATA

    anonymous_count = sum(1 for r in REPORTS_DATA if r.get("is_anonymous", False))
    assert anonymous_count >= 2


def test_seed_areas_have_geometry_wkt():
    from seed.seed_areas import AREAS

    for a in AREAS:
        assert "geometry_wkt" in a
        assert a["geometry_wkt"].startswith("MULTIPOLYGON")
        assert "buffer_wkt" in a
        assert a["buffer_wkt"].startswith("MULTIPOLYGON")


def test_seed_incidents_have_location_fields():
    from seed.seed_incidents import INCIDENTS

    for inc in INCIDENTS:
        assert "latitude" in inc
        assert "longitude" in inc
        assert "code" in inc
        assert "severity" in inc
        assert "status" in inc


def test_seed_esg_data():
    from seed.seed_esg import ESG

    assert ESG["area_name"] == "RPPN Elias Andrade"
    assert ESG["monitored_area_ha"] == 1250.5
    assert "ods_15" in ESG["ods"]
    assert ESG["ods"]["ods_15"] is True
