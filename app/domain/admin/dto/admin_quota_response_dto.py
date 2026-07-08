from datetime import datetime

from app.schemas.base import BaseDTO


# -- QuotaItem (one table row) -----------------------------------
class QuotaItemDTO(BaseDTO):
    quota_allocation_id: str
    train_id: str
    train_number: str  # "12951"
    train_name: str  # "Mumbai Rajdhani"
    train_display: str  # "12951 Mumbai Rajdhani" (TRAIN column)
    train_class: str  # CLASS pill
    general_pct: int  # GENERAL
    tatkal_pct: int  # TATKAL
    ladies_pct: int  # LADIES
    premium_tatkal_pct: int  # PREMIUM TATKAL
    total_pct: int  # sum of the four (always 100 when valid)
    created_at: datetime
