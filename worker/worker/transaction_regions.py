from pydantic import BaseModel


class TransactionRegion(BaseModel):
    """A bounding box, in the same coordinate space as Page/TextBlock (points
    from the page's top-left corner), narrowing a page down to just the part
    that actually holds transaction rows, headers/footers/margins excluded."""

    page: int
    region: tuple[float, float, float, float]  # [x0, y0, x1, y1]


class TransactionRegionDetection(BaseModel):
    transaction_regions: list[TransactionRegion]
