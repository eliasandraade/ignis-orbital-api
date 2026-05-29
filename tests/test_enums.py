from app.core.enums import IncidentStatus, ReportStatus, UserRole


def test_user_roles_values():
    assert UserRole.ADMIN == "admin"
    assert UserRole.GESTOR == "gestor"
    assert UserRole.PUBLICO == "publico"


def test_incident_status_values():
    assert IncidentStatus.PROTOCOL_ACTIVATED == "protocol_activated"
    # CRITICAL is in IncidentSeverity, not IncidentStatus
    assert not any(member == "critical" for member in IncidentStatus)


def test_report_status_values():
    assert ReportStatus.CONVERTED == "converted"
