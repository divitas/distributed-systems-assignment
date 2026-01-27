@dataclass
class Item:
    item_id: tuple[int, int]        # (category, unique_id)
    name: str                        # max 32 chars
    category: int
    keywords: list[str]              # up to 5, each max 8 chars
    condition: str                   # "New" or "Used"
    sale_price: float
    quantity: int
    feedback: tuple[int, int]        # (thumbs_up, thumbs_down)

@dataclass
class Seller:
    seller_id: int
    name: str                        # max 32 chars
    feedback: tuple[int, int] = (0, 0)       # (thumbs_up, thumbs_down)
    items_sold: int = 0

@dataclass
class Buyer:
    buyer_id: int
    name: str                        # max 32 chars
    items_purchased: int = 0
   