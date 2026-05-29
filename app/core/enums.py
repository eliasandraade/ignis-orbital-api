from enum import StrEnum


class UserRole(StrEnum):
    PUBLICO = "publico"
    CAMPO = "campo"
    GESTOR = "gestor"
    ORGAO = "orgao"
    ADMIN = "admin"


class IncidentStatus(StrEnum):
    DETECTED = "detected"
    MONITORING = "monitoring"
    ACTIVE = "active"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    PROTOCOL_ACTIVATED = "protocol_activated"


class IncidentSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentType(StrEnum):
    FIRE = "fire"
    DEFORESTATION = "deforestation"
    FLOOD = "flood"
    ILLEGAL_MINING = "illegal_mining"
    POLLUTION = "pollution"
    OTHER = "other"


class IncidentSource(StrEnum):
    REPORT = "report"
    SENSOR = "sensor"
    SATELLITE = "satellite"
    PATROL = "patrol"
    AGENCY = "agency"


class ReportStatus(StrEnum):
    PENDING = "pending"
    VALIDATED = "validated"
    DISCARDED = "discarded"
    CONVERTED = "converted"


class ReportUrgency(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReportType(StrEnum):
    FIRE = "fire"
    DEFORESTATION = "deforestation"
    ILLEGAL_MINING = "illegal_mining"
    FLOOD = "flood"
    POLLUTION = "pollution"
    INVASIVE_SPECIES = "invasive_species"
    WILDLIFE_TRAFFIC = "wildlife_traffic"
    OTHER = "other"


class TeamStatus(StrEnum):
    AVAILABLE = "available"
    MOBILIZED = "mobilized"
    STANDBY = "standby"
    RETURNING = "returning"
    UNAVAILABLE = "unavailable"


class TeamType(StrEnum):
    FIREFIGHTING = "firefighting"
    MONITORING = "monitoring"
    RESCUE = "rescue"
    SUPPORT = "support"
    PATROL = "patrol"


class ResourceStatus(StrEnum):
    AVAILABLE = "available"
    IN_USE = "in_use"
    MAINTENANCE = "maintenance"
    UNAVAILABLE = "unavailable"


class ResourceType(StrEnum):
    VEHICLE = "vehicle"
    EQUIPMENT = "equipment"
    PERSONNEL = "personnel"
    DRONE = "drone"
    AIRCRAFT = "aircraft"
    BOAT = "boat"
    OTHER = "other"


class MissionStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABORTED = "aborted"


class DataQuality(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ESTIMATED = "estimated"
    MOCK = "mock"


class EvidenceType(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"
    GPS_TRACK = "gps_track"
    OTHER = "other"


class ProtectedAreaCategory(StrEnum):
    APA = "APA"
    PARNA = "PARNA"
    RESEX = "RESEX"
    RPPN = "RPPN"
    REBIO = "REBIO"
    ESEC = "ESEC"
    PE = "PE"
    FLONA = "FLONA"
    ARI = "ARI"
    OTHER = "other"
