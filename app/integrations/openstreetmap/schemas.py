from pydantic import BaseModel


class ReverseGeocodingResponse(BaseModel):
    source: str = "OpenStreetMap/Nominatim"
    latitude: float
    longitude: float
    display_name: str | None
    municipality: str | None
    state: str | None
    country: str | None
    cached: bool
    fetched_at: str
