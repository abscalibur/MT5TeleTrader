from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    messages_read: Mapped[list["MessageRead"]] = relationship(back_populates="channel")
    interpreted_trades: Mapped[list["InterpretedTrade"]] = relationship(
        back_populates="channel",
        overlaps="interpreted_trades,message_read",
    )


class MessageRead(Base):
    __tablename__ = "messages_read"
    __table_args__ = (
        PrimaryKeyConstraint("channel_id", "message_id"),
        Index("ix_messages_read_channel_id_message_time", "channel_id", "message_time"),
        Index("ix_messages_read_processed_message_time", "processed", "message_time"),
    )

    channel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("channels.id"),
    )
    message_id: Mapped[int] = mapped_column(BigInteger)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    message_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )

    channel: Mapped[Channel] = relationship(back_populates="messages_read")
    interpreted_trades: Mapped[list["InterpretedTrade"]] = relationship(
        back_populates="message_read",
        overlaps="channel,interpreted_trades",
    )


class InterpretedTrade(Base):
    __tablename__ = "interpreted_trades"
    __table_args__ = (
        ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name="fk_interpreted_trades_channel_id_channels",
        ),
        ForeignKeyConstraint(
            ["channel_id", "message_id"],
            ["messages_read.channel_id", "messages_read.message_id"],
            name="fk_interpreted_trades_message_read",
        ),
        UniqueConstraint(
            "channel_id",
            "message_id",
            "entryprice",
            name="uq_interpreted_trades_channel_id_message_id_entryprice",
        ),
        Index("ix_interpreted_trades_channel_id", "channel_id"),
        Index("ix_interpreted_trades_symbol_side", "symbol", "side"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trade_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    entryprice: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    stoploss: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    channel: Mapped[Channel] = relationship(
        back_populates="interpreted_trades",
        foreign_keys=[channel_id],
        overlaps="interpreted_trades,message_read",
    )
    message_read: Mapped[MessageRead] = relationship(
        back_populates="interpreted_trades",
        foreign_keys=[channel_id, message_id],
        overlaps="channel,interpreted_trades,messages_read",
    )
