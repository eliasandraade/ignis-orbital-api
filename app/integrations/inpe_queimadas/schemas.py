"""Internal schemas for INPE TerraBrasilis WFS fire data.

These are intermediate representations used before normalization to the
shared OrbitalAlert schema.  They model the GeoJSON properties returned by
the `ams1h:active-fire-today` WFS layer.
"""

from datetime import datetime

from pydantic import BaseModel


class InpeFocus(BaseModel):
    """A single fire focus as returned by the INPE TerraBrasilis WFS API."""

    feature_id: str
    inpe_id: int
    lat: float
    lng: float
    view_date: str
    viewed_at: datetime | None = None
    satelite: str | None = None
    municipio: str | None = None
    biome: str | None = None
