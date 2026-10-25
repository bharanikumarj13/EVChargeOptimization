from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.reporting_service import ReportingService
from app.core.security import validate_export_filename

router = APIRouter(prefix="/reports", tags=["Reporting & Exports"])


@router.get("/summary")
def get_reports_summary(db: Session = Depends(get_db)):
    service = ReportingService(db)
    return service.get_summary_metrics()


@router.get("/allocations.csv")
def export_allocations_csv(
    filename: str = "evcharge_allocations.csv",
    db: Session = Depends(get_db),
):
    service = ReportingService(db)
    csv_content = service.generate_allocations_csv()
    safe_filename = validate_export_filename(filename)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "Cache-Control": "no-cache",
        },
    )
