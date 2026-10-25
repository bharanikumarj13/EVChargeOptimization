from typing import List
from sqlalchemy.orm import Session
from app.models.forecast_snapshot import ForecastSnapshot
from app.schemas.forecast import ForecastIntervalItem


class ForecastSnapshotRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_forecast_id(self, forecast_id: str) -> List[ForecastSnapshot]:
        return (
            self.db.query(ForecastSnapshot)
            .filter(ForecastSnapshot.forecast_id == forecast_id)
            .order_by(ForecastSnapshot.interval_start, ForecastSnapshot.station_id)
            .all()
        )

    def save_snapshot(self, snapshot_id: str, items: List[ForecastIntervalItem]) -> List[ForecastSnapshot]:
        created = []
        for item in items:
            snapshot = ForecastSnapshot(
                snapshot_id=snapshot_id,
                forecast_id=item.forecast_id,
                scenario_id=item.scenario_id,
                station_id=item.station_id,
                interval_start=item.interval_start,
                interval_end=item.interval_end,
                interval_minutes=item.interval_minutes,
                predicted_arrivals=item.predicted_arrivals,
                predicted_energy_kwh=item.predicted_energy_kwh,
                model_version=item.model_version,
                generated_at=item.generated_at,
            )
            self.db.add(snapshot)
            created.append(snapshot)
        self.db.commit()
        return created
