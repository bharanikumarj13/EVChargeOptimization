from typing import List
from sqlalchemy.orm import Session
from app.models.forecast_snapshot import ForecastSnapshot
from app.schemas.forecast import ForecastIntervalItem
from app.core.exceptions import InvalidForecastError


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
        """
        Persists an immutable baseline forecast snapshot.
        If a snapshot for this forecast_id already exists:
        - If content is identical: returns existing records idempotently.
        - If content conflicts: raises InvalidForecastError rather than overwriting.
        """
        if not items:
            return []

        forecast_id = items[0].forecast_id
        existing = self.get_by_forecast_id(forecast_id)
        if existing:
            # Check length equivalence
            if len(existing) != len(items):
                raise InvalidForecastError(
                    f"Baseline forecast snapshot for '{forecast_id}' already exists with {len(existing)} intervals. "
                    f"Conflicting snapshot with {len(items)} intervals rejected."
                )

            # Check individual interval equivalence with timezone normalization
            sorted_items = sorted(items, key=lambda x: (x.interval_start, x.station_id))
            for ex, it in zip(existing, sorted_items):
                ex_start = ex.interval_start.replace(tzinfo=it.interval_start.tzinfo) if ex.interval_start.tzinfo is None else ex.interval_start
                ex_end = ex.interval_end.replace(tzinfo=it.interval_end.tzinfo) if ex.interval_end.tzinfo is None else ex.interval_end

                if (
                    ex.station_id != it.station_id
                    or abs(ex.predicted_arrivals - it.predicted_arrivals) > 0.001
                    or abs(ex.predicted_energy_kwh - it.predicted_energy_kwh) > 0.001
                    or ex_start != it.interval_start
                    or ex_end != it.interval_end
                ):
                    raise InvalidForecastError(
                        f"Baseline forecast snapshot for '{forecast_id}' already exists with immutable content. "
                        f"Conflicting snapshot content rejected."
                    )
            return existing

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
