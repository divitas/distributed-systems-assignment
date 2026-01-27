# buyer_client/buyer_api.py
from common.rpc import send_request

class BuyerAPI:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

    def create_account(self, username: str, password: str):
        return send_request(self.host, self.port, {
            "type": "Buyer.CreateAccount",
            "session_id": None,
            "payload": {"username": username, "password": password}
        })

    def login(self, username: str, password: str):
        return send_request(self.host, self.port, {
            "type": "Buyer.Login",
            "session_id": None,
            "payload": {"username": username, "password": password}
        })

    def logout(self, session_id: str):
        return send_request(self.host, self.port, {
            "type": "Buyer.Logout",
            "session_id": session_id,
            "payload": {}
        })

    def search_items_for_sale(self, session_id: str, category: int, keywords: list[str]):
        return send_request(self.host, self.port, {
            "type": "Buyer.SearchItemsForSale",
            "session_id": session_id,
            "payload": {"category": category, "keywords": keywords}
        })

    def get_item(self, session_id: str, item_id: int):
        return send_request(self.host, self.port, {
            "type": "Buyer.GetItem",
            "session_id": session_id,
            "payload": {"item_id": item_id}
        })

    def add_item_to_cart(self, session_id: str, item_id: int, quantity: int):
        return send_request(self.host, self.port, {
            "type": "Buyer.AddItemToCart",
            "session_id": session_id,
            "payload": {"item_id": item_id, "quantity": quantity}
        })

    def remove_item_from_cart(self, session_id: str, item_id: int):
        return send_request(self.host, self.port, {
            "type": "Buyer.RemoveItemFromCart",
            "session_id": session_id,
            "payload": {"item_id": item_id}
        })

    def save_cart(self, session_id: str):
        return send_request(self.host, self.port, {
            "type": "Buyer.SaveCart",
            "session_id": session_id,
            "payload": {}
        })
    
    def clear_cart(self, session_id: str):
        return send_request(self.host, self.port, {
            "type": "Buyer.ClearCart",
            "session_id": session_id,
            "payload": {}
        })

    def display_cart(self, session_id: str):
        return send_request(self.host, self.port, {
            "type": "Buyer.DisplayCart",
            "session_id": session_id,
            "payload": {}
        })

    def provide_feedback(self, session_id: str, item_id: int, thumbs_up: bool):
        return send_request(self.host, self.port, {
            "type": "Buyer.ProvideFeedback",
            "session_id": session_id,
            "payload": {"item_id": item_id, "thumbs_up": thumbs_up}
        })

    def get_seller_ratings(self, session_id: str, seller_username: str):
        return send_request(self.host, self.port, {
            "type": "Buyer.GetSellerRatings",
            "session_id": session_id,
            "payload": {"seller_username": seller_username}
        })

    def get_buyer_purchases(self, session_id: str):
        return send_request(self.host, self.port, {
            "type": "Buyer.GetBuyerPurchases",
            "session_id": session_id,
            "payload": {}
        })


