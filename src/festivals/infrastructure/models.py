from datetime import date, datetime
from sqlalchemy import  CheckConstraint, DateTime, String, BigInteger, Date, func, Text
from sqlalchemy.orm import Mapped, mapped_column
from shared.core.models import Base

class Festival(Base):
    __tablename__ = "festivals"

    __table_args__ = (
        CheckConstraint(
            "starts_on < ends_on",
            name="ck_festivals_date_range"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        )

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    
    venue: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(), 
        nullable=True,
    )

    starts_on: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    ends_on: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )





    