from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import models
from app.db.base import Base
from app.db.session import create_db_engine
from app.services.entitlement_ledger import InsufficientEntitlement
from app.services.ledger_service import LedgerService


def _session_factory(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path}/race.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    setup = factory()
    setup.add(models.Merchant(id="mch_aurum", name="Aurum Audio"))
    setup.commit()
    ledger = LedgerService(setup)
    ledger.open_incident("mch_aurum", "inc_right_audio", 499900)
    setup.commit()
    setup.close()
    return factory


def test_parallel_reserves_only_one_consumes_remaining(tmp_path) -> None:
    factory = _session_factory(tmp_path)

    def attempt(i: int) -> str:
        session = factory()
        try:
            ledger = LedgerService(session)
            ledger.reserve(
                "mch_aurum",
                "inc_right_audio",
                499900,
                f"agent_{i:02d}_reserve_v1",
            )
            session.commit()
            return "reserved"
        except InsufficientEntitlement:
            session.rollback()
            return "blocked"
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(attempt, range(8)))

    assert outcomes.count("reserved") == 1
    assert outcomes.count("blocked") == 7

    session = factory()
    entitlement = session.get(models.Entitlement, ("mch_aurum", "inc_right_audio"))
    reserved_rows = session.scalars(
        select(models.RemedyReservation).where(
            models.RemedyReservation.merchant_id == "mch_aurum",
            models.RemedyReservation.status == "RESERVED",
        )
    ).all()
    session.close()
    assert entitlement is not None
    assert entitlement.reserved_minor == 499900
    assert entitlement.settled_minor == 0
    assert len(reserved_rows) == 1
