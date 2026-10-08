"""Step 13 privacy-preserving public civic statistics and rankings."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, and_, or_
from sqlalchemy.orm import Session

from app.models.grievance import Grievance, GrievanceStatus
from app.models.category import Category
from app.models.department import Department
from app.models.grievance_status_history import GrievanceStatusHistory
from app.models.resolution import Resolution, ResolutionDispute, ResolutionFeedback
from app.models.public_statistics import CivicRankingConfig

RESOLVED = (GrievanceStatus.RESOLVED, GrievanceStatus.CLOSED)
LEVELS = {
    "state": Grievance.state,
    "district": Grievance.district,
    "taluka": Grievance.taluka,
    "village": Grievance.village,
}


def get_config(db: Session):
    cfg = db.query(CivicRankingConfig).first()
    if not cfg:
        cfg = CivicRankingConfig()
        db.add(cfg)
        db.flush()
    return cfg


def _filtered(q, filters, date_from=None, date_to=None):
    for key in ("state", "district", "taluka", "village"):
        value = filters.get(key)
        if value:
            q = q.filter(LEVELS[key] == value)
    if filters.get("category_id"):
        q = q.filter(Grievance.category_id == filters["category_id"])
    if filters.get("department_id"):
        q = q.filter(Grievance.department_id == filters["department_id"])
    if date_from is not None:
        q = q.filter(Grievance.submitted_at >= date_from)
    if date_to is not None:
        q = q.filter(Grievance.submitted_at < date_to)
    return q


def _safe_count(db, filters, date_from=None, date_to=None):
    return _filtered(db.query(func.count(Grievance.id)), filters, date_from, date_to).scalar() or 0


def _suppressed(db, filters, date_from=None, date_to=None):
    total = _safe_count(db, filters, date_from, date_to)
    threshold = get_config(db).minimum_sample_size
    return total < threshold, total, threshold


def _duration_days_expr(db, start_col, end_col):
    """Return a dialect-portable SQL expression for elapsed days."""
    if db.bind.dialect.name == "sqlite":
        return func.julianday(start_col) - func.julianday(end_col)
    return func.extract("epoch", start_col - end_col) / 86400.0


def _duration_hours_expr(db, start_col, end_col):
    if db.bind.dialect.name == "sqlite":
        return (func.julianday(start_col) - func.julianday(end_col)) * 24.0
    return func.extract("epoch", start_col - end_col) / 3600.0


def _metric_rows(db, filters):
    """Return status counts and timing metrics using SQL aggregation."""
    rows = dict(
        _filtered(
            db.query(Grievance.status, func.count(Grievance.id)).group_by(Grievance.status),
            filters,
        ).all()
    )
    ids_subq = _filtered(db.query(Grievance.id.label("id")), filters).subquery()
    resolution_rows = (
        db.query(
            func.avg(
                _duration_days_expr(db, Resolution.resolution_date, Grievance.submitted_at)
            )
        )
        .join(Grievance, Resolution.grievance_id == Grievance.id)
        .join(ids_subq, ids_subq.c.id == Grievance.id)
        .filter(Resolution.resolution_date.isnot(None))
        .scalar()
    )
    first_processing = (
        db.query(
            GrievanceStatusHistory.grievance_id.label("grievance_id"),
            func.min(GrievanceStatusHistory.changed_at).label("first_processed"),
        )
        .join(ids_subq, ids_subq.c.id == GrievanceStatusHistory.grievance_id)
        .filter(GrievanceStatusHistory.old_status.isnot(None))
        .group_by(GrievanceStatusHistory.grievance_id)
        .subquery()
    )
    response_hours = (
        db.query(
            func.avg(
                _duration_hours_expr(db, first_processing.c.first_processed, Grievance.submitted_at)
            )
        )
        .join(first_processing, first_processing.c.grievance_id == Grievance.id)
        .scalar()
    )
    return rows, resolution_rows, response_hours


def summary(db: Session, filters):
    suppressed, total, threshold = _suppressed(db, filters)
    if suppressed:
        return {"insufficient_data": True, "minimum_sample_size": threshold, "total_grievances": None}

    rows, avg_resolution, avg_response = _metric_rows(db, filters)

    def n(status):
        return rows.get(status, rows.get(getattr(status, "value", status), 0)) or 0

    resolved = n(GrievanceStatus.RESOLVED)
    closed = n(GrievanceStatus.CLOSED)
    final = resolved + closed
    pending = n(GrievanceStatus.SUBMITTED) + n(GrievanceStatus.UNDER_REVIEW) + n(GrievanceStatus.ASSIGNED)
    in_progress = n(GrievanceStatus.IN_PROGRESS)
    rejected = n(GrievanceStatus.REJECTED)

    ids_subq = _filtered(db.query(Grievance.id.label("id")), filters).subquery()
    disputed = (
        db.query(func.count(func.distinct(ResolutionDispute.grievance_id)))
        .join(ids_subq, ids_subq.c.id == ResolutionDispute.grievance_id)
        .scalar()
        or 0
    )
    dispute_rate = round(disputed * 100 / final, 2) if final else 0

    return {
        "insufficient_data": False,
        "minimum_sample_size": threshold,
        "total_grievances": total,
        "resolved_grievances": resolved,
        "closed_grievances": closed,
        "pending_grievances": pending,
        "in_progress_grievances": in_progress,
        "rejected_grievances": rejected,
        "resolution_rate": round(final * 100 / total, 2) if total else 0,
        "pending_rate": round(pending * 100 / total, 2) if total else 0,
        "dispute_rate": dispute_rate,
        "average_resolution_days": round(float(avg_resolution), 2) if avg_resolution is not None else None,
        "average_response_hours": round(float(avg_response), 2) if avg_response is not None else None,
    }


def breakdown(db, filters, kind):
    suppressed, _, threshold = _suppressed(db, filters)
    if suppressed:
        return {"insufficient_data": True, "minimum_sample_size": threshold, "items": []}
    model = Category if kind == "category" else Department
    fk = Grievance.category_id if kind == "category" else Grievance.department_id
    q = _filtered(
        db.query(
            model.id,
            model.name,
            func.count(Grievance.id),
            func.sum(case((Grievance.status.in_(RESOLVED), 1), else_=0)),
        )
        .join(Grievance, fk == model.id)
        .group_by(model.id, model.name),
        filters,
    )
    items = []
    for id_, name, total, done in q.all():
        if total < threshold:
            continue
        items.append(
            {
                "id": str(id_),
                "name": name,
                "total": total,
                "resolved_or_closed": int(done or 0),
                "resolution_rate": round((done or 0) * 100 / total, 2),
            }
        )
    return {"insufficient_data": False, "minimum_sample_size": threshold, "items": items}


def trends(db, filters, period="monthly"):
    suppressed, _, threshold = _suppressed(db, filters)
    if suppressed:
        return {"insufficient_data": True, "minimum_sample_size": threshold, "period": period, "items": []}
    dialect = db.bind.dialect.name
    if period not in {"daily", "weekly", "monthly", "yearly"}:
        raise ValueError("Unsupported trend period")
    fmt = {"daily": "%Y-%m-%d", "weekly": "%Y-W%W", "monthly": "%Y-%m", "yearly": "%Y"}[period]
    bucket = (
        func.strftime(fmt, Grievance.created_at)
        if dialect == "sqlite"
        else func.to_char(
            Grievance.created_at,
            {"daily": "YYYY-MM-DD", "weekly": 'IYYY-"W"IW', "monthly": "YYYY-MM", "yearly": "YYYY"}[period],
        )
    )
    q = _filtered(
        db.query(bucket.label("period"), func.count(Grievance.id)).group_by(bucket).order_by(bucket),
        filters,
    )
    items = []
    prev = None
    for p, c in q.all():
        c = int(c)
        # Suppress individual buckets, not only the whole selected geography.
        if c < threshold:
            continue
        change = None if prev in (None, 0) else round((c - prev) * 100 / prev, 2)
        items.append({"period": p, "total": c, "change_percent": change})
        prev = c
    return {"insufficient_data": False, "minimum_sample_size": threshold, "period": period, "items": items}


def locations(db, filters):
    result = {}
    ordered_levels = list(LEVELS)
    for level, col in LEVELS.items():
        parent_filters = {
            k: v
            for k, v in filters.items()
            if k in LEVELS and ordered_levels.index(k) < ordered_levels.index(level)
        }
        q = _filtered(
            db.query(col)
            .filter(col.isnot(None), col != "")
            .distinct()
            .order_by(col),
            parent_filters,
        )
        result[level + "s"] = [x[0] for x in q.all()]
    return result


def _score_metrics(db: Session, level, filters, date_from=None, date_to=None):
    """Compute scores with one aggregate query per metric, avoiding per-location N+1 queries."""
    col = LEVELS[level]
    cfg = get_config(db)
    threshold = cfg.minimum_sample_size

    base = _filtered(
        db.query(
            Grievance.id.label("grievance_id"),
            col.label("location"),
            Grievance.status,
            Grievance.submitted_at,
        ).filter(col.isnot(None), col != ""),
        filters,
        date_from,
        date_to,
    ).subquery()

    groups = (
        db.query(
            base.c.location,
            func.count(base.c.grievance_id).label("total"),
            func.sum(case((base.c.status.in_(RESOLVED), 1), else_=0)).label("done"),
        )
        .group_by(base.c.location)
        .all()
    )
    groups = [g for g in groups if g.total >= threshold]
    if not groups:
        return []

    resolution_by_location = (
        db.query(
            base.c.location.label("location"),
            func.avg(_duration_days_expr(db, Resolution.resolution_date, base.c.submitted_at)).label("days"),
        )
        .join(Resolution, Resolution.grievance_id == base.c.grievance_id)
        .group_by(base.c.location)
        .all()
    )
    rating_by_location = (
        db.query(base.c.location.label("location"), func.avg(ResolutionFeedback.rating).label("rating"))
        .join(ResolutionFeedback, ResolutionFeedback.grievance_id == base.c.grievance_id)
        .filter(ResolutionFeedback.rating.isnot(None))
        .group_by(base.c.location)
        .all()
    )
    dispute_by_location = (
        db.query(base.c.location.label("location"), func.count(func.distinct(ResolutionDispute.grievance_id)).label("disputes"))
        .join(ResolutionDispute, ResolutionDispute.grievance_id == base.c.grievance_id)
        .group_by(base.c.location)
        .all()
    )

    timing = {x.location: float(x.days) for x in resolution_by_location if x.days is not None}
    ratings = {x.location: float(x.rating) for x in rating_by_location if x.rating is not None}
    disputes = {x.location: int(x.disputes or 0) for x in dispute_by_location}

    items = []
    for loc, total, done in groups:
        total = int(total)
        done = int(done or 0)
        resolution_rate = done * 100 / total
        days = timing.get(loc)
        timeliness = max(0.0, 100.0 - (days / cfg.timeliness_target_days * 100.0)) if days is not None else 0.0
        rating = ratings.get(loc)
        satisfaction = rating / 5 * 100 if rating is not None else 0.0
        dispute_count = disputes.get(loc, 0)
        low_dispute = max(0.0, 100.0 - (dispute_count * 100 / max(done, 1)))
        score = (
            resolution_rate * cfg.resolution_weight
            + timeliness * cfg.timeliness_weight
            + satisfaction * cfg.satisfaction_weight
            + low_dispute * cfg.dispute_weight
        )
        items.append(
            {
                "location": loc,
                "score": round(score, 2),
                "resolution_rate": round(resolution_rate, 2),
                "average_resolution_days": round(days, 2) if days is not None else None,
                "timeliness_score": round(timeliness, 2),
                "citizen_satisfaction": round(satisfaction, 2) if rating is not None else None,
                "low_dispute_score": round(low_dispute, 2),
                "grievance_volume": total,
            }
        )
    items.sort(key=lambda x: (-x["score"], -x["grievance_volume"], x["location"]))
    for i, item in enumerate(items, 1):
        item["rank"] = i
    return items


def rankings(db, level, filters):
    cfg = get_config(db)
    return {
        "level": level,
        "minimum_sample_size": cfg.minimum_sample_size,
        "methodology": methodology(db),
        "items": _score_metrics(db, level, filters),
    }


def category_rankings(db, level, category_id, filters):
    if not category_id:
        raise ValueError("category_id is required")
    scoped = dict(filters)
    scoped["category_id"] = category_id
    result = rankings(db, level, scoped)
    result["category_id"] = str(category_id)
    result["leaderboard_type"] = "category"
    return result


def _period_bounds(period="monthly"):
    now = datetime.now(timezone.utc)
    if period == "monthly":
        current_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        previous_start = (current_start - timedelta(days=1)).replace(day=1)
    elif period == "weekly":
        current_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        previous_start = current_start - timedelta(days=7)
    elif period == "yearly":
        current_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        previous_start = current_start.replace(year=current_start.year - 1)
    else:
        current_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        previous_start = current_start - timedelta(days=1)
    return previous_start, current_start, now


def most_improved(db, level, filters, period="monthly"):
    previous_start, current_start, current_end = _period_bounds(period)
    current = _score_metrics(db, level, filters, current_start, current_end)
    previous = _score_metrics(db, level, filters, previous_start, current_start)
    current_by_location = {x["location"]: x for x in current}
    previous_by_location = {x["location"]: x for x in previous}
    threshold = get_config(db).minimum_sample_size
    items = []
    for location, current_item in current_by_location.items():
        previous_item = previous_by_location.get(location)
        if not previous_item:
            continue
        old_score = previous_item["score"]
        new_score = current_item["score"]
        change = round(new_score - old_score, 2)
        pct = round(change * 100 / abs(old_score), 2) if old_score else None
        items.append(
            {
                "location": location,
                "previous_score": old_score,
                "current_score": new_score,
                "improvement": change,
                "improvement_percent": pct,
                "grievance_volume": current_item["grievance_volume"],
            }
        )
    items.sort(key=lambda x: (-x["improvement"], -(x["improvement_percent"] or 0), x["location"]))
    for i, item in enumerate(items, 1):
        item["rank"] = i
    return {
        "level": level,
        "period": period,
        "minimum_sample_size": threshold,
        "items": items,
        "methodology": methodology(db),
    }


def methodology(db):
    c = get_config(db)
    return {
        "resolution_performance_weight": c.resolution_weight,
        "timeliness_weight": c.timeliness_weight,
        "citizen_satisfaction_weight": c.satisfaction_weight,
        "low_dispute_weight": c.dispute_weight,
        "minimum_sample_size": c.minimum_sample_size,
        "timeliness_target_days": c.timeliness_target_days,
        "formula": "score = resolution_rate*w1 + timeliness_score*w2 + satisfaction_score*w3 + low_dispute_score*w4",
        "components": [
            {"name": "Resolution performance", "weight": c.resolution_weight},
            {"name": "Timeliness", "weight": c.timeliness_weight},
            {"name": "Citizen satisfaction", "weight": c.satisfaction_weight},
            {"name": "Low dispute/reopen rate", "weight": c.dispute_weight},
        ],
        "sla_note": "SLA is excluded from the official score because Steps 1-12 contain no authoritative SLA target field.",
        "ranking_principle": "Locations are ranked by normalized performance, not raw grievance volume; locations below the minimum sample size are excluded.",
    }
