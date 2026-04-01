"""
Buyer Frontend Server - PA3 Replicated version
Stateless; runs 4 replicas. Connects to replicated customer DB and product DB.

Usage:
  python buyer_server_replicated.py --replica-id 0
  python buyer_server_replicated.py --replica-id 1
  ...
"""

import grpc
import json
import sys
import os
import argparse
import random
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import requests as http_requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'proto'))

import config
import customer_pb2
import customer_pb2_grpc
import product_pb2
import product_pb2_grpc

app = FastAPI(title="Buyer Frontend Server (PA3)")


# ========== Replica-aware gRPC clients with failover ==========

def get_customer_stub():
    """Connect to a random customer DB replica with failover."""
    replicas = list(config.CUSTOMER_DB_REPLICAS)
    random.shuffle(replicas)
    for r in replicas:
        try:
            channel = grpc.insecure_channel(
                f"{r['host']}:{r['grpc_port']}",
                options=[('grpc.connect_timeout_ms', 3000)]
            )
            stub = customer_pb2_grpc.CustomerDBStub(channel)
            # Quick connectivity check
            grpc.channel_ready_future(channel).result(timeout=2)
            return stub
        except Exception:
            continue
    raise HTTPException(status_code=503, detail="All customer DB replicas unavailable")


def get_product_stub():
    """Connect to a random product DB replica with failover."""
    replicas = list(config.PRODUCT_DB_REPLICAS)
    random.shuffle(replicas)
    for r in replicas:
        try:
            channel = grpc.insecure_channel(
                f"{r['host']}:{r['grpc_port']}",
                options=[('grpc.connect_timeout_ms', 3000)]
            )
            stub = product_pb2_grpc.ProductDBStub(channel)
            grpc.channel_ready_future(channel).result(timeout=2)
            return stub
        except Exception:
            continue
    raise HTTPException(status_code=503, detail="All product DB replicas unavailable")


def parse(response):
    return {
        'status': 'success' if response.status == 1 else 'error',
        'message': response.message,
        'data': json.loads(response.json_data) if response.json_data else {}
    }


def validate_session(session_id: str):
    stub = get_customer_stub()
    response = stub.ValidateSessionBuyer(customer_pb2.SessionRequest(session_id=session_id))
    if response.status != 1:
        raise HTTPException(status_code=401, detail=response.message)
    return json.loads(response.json_data)['buyer_id']


def call_financial_service(card_name, card_number, expiration_date, security_code):
    soap_body = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ProcessPayment>
      <name>{}</name>
      <card_number>{}</card_number>
      <expiration_date>{}</expiration_date>
      <security_code>{}</security_code>
    </ProcessPayment>
  </soap:Body>
</soap:Envelope>""".format(card_name, card_number, expiration_date, security_code)

    response = http_requests.post(
        f'http://{config.FINANCIAL_SERVICE_HOST}:{config.FINANCIAL_SERVICE_PORT}/',
        data=soap_body,
        headers={'Content-Type': 'text/xml'},
        timeout=10
    )
    return '<result>true</result>' in response.text


# ========== Request Models ==========

class CreateAccountRequest(BaseModel):
    username: str
    password: str
    buyer_name: str

class LoginRequest(BaseModel):
    username: str
    password: str

class SessionRequest(BaseModel):
    session_id: str

class SearchRequest(BaseModel):
    session_id: str
    category: int
    keywords: List[str] = []

class CartRequest(BaseModel):
    session_id: str
    item_id: str
    quantity: int

class SaveCartRequest(BaseModel):
    session_id: str

class FeedbackRequest(BaseModel):
    session_id: str
    item_id: str
    seller_id: str
    thumbs: int

class MakePurchaseRequest(BaseModel):
    session_id: str
    item_id: str
    quantity: int
    card_name: str
    card_number: str
    expiration_date: str
    security_code: str


# ========== Routes (identical API to PA2) ==========

@app.post("/buyer/create_account")
async def create_account(body: CreateAccountRequest):
    stub = get_customer_stub()
    response = stub.CreateBuyer(customer_pb2.CreateBuyerRequest(
        username=body.username, password=body.password, buyer_name=body.buyer_name
    ))
    return parse(response)

@app.post("/buyer/login")
async def login(body: LoginRequest):
    stub = get_customer_stub()
    response = stub.LoginBuyer(customer_pb2.LoginRequest(
        username=body.username, password=body.password
    ))
    return parse(response)

@app.post("/buyer/logout")
async def logout(body: SessionRequest):
    stub = get_customer_stub()
    response = stub.LogoutBuyer(customer_pb2.SessionRequest(session_id=body.session_id))
    return parse(response)

@app.post("/buyer/restore_session")
async def restore_session(body: SessionRequest):
    stub = get_customer_stub()
    response = stub.RestoreSessionBuyer(customer_pb2.SessionRequest(session_id=body.session_id))
    return parse(response)

@app.post("/buyer/search_items")
async def search_items(body: SearchRequest):
    validate_session(body.session_id)
    stub = get_product_stub()
    response = stub.SearchItems(product_pb2.SearchRequest(
        category=body.category, keywords=body.keywords
    ))
    return parse(response)

@app.get("/buyer/get_item")
async def get_item(session_id: str, item_id: str):
    validate_session(session_id)
    stub = get_product_stub()
    response = stub.GetItem(product_pb2.ItemRequest(item_id=item_id))
    return parse(response)

@app.post("/buyer/add_to_cart")
async def add_to_cart(body: CartRequest):
    buyer_id = validate_session(body.session_id)
    stub = get_customer_stub()
    response = stub.AddToCart(customer_pb2.CartRequest(
        session_id=body.session_id, buyer_id=str(buyer_id),
        item_id=body.item_id, quantity=body.quantity
    ))
    return parse(response)

@app.post("/buyer/remove_from_cart")
async def remove_from_cart(body: CartRequest):
    buyer_id = validate_session(body.session_id)
    stub = get_customer_stub()
    response = stub.RemoveFromCart(customer_pb2.CartRequest(
        session_id=body.session_id, buyer_id=str(buyer_id),
        item_id=body.item_id, quantity=body.quantity
    ))
    return parse(response)

@app.post("/buyer/save_cart")
async def save_cart(body: SaveCartRequest):
    buyer_id = validate_session(body.session_id)
    stub = get_customer_stub()
    response = stub.SaveCart(customer_pb2.SaveCartRequest(
        session_id=body.session_id, buyer_id=str(buyer_id)
    ))
    return parse(response)

@app.post("/buyer/clear_cart")
async def clear_cart(body: SessionRequest):
    validate_session(body.session_id)
    stub = get_customer_stub()
    response = stub.ClearCart(customer_pb2.SessionRequest(session_id=body.session_id))
    return parse(response)

@app.get("/buyer/display_cart")
async def display_cart(session_id: str):
    validate_session(session_id)
    stub = get_customer_stub()
    response = stub.GetCart(customer_pb2.SessionRequest(session_id=session_id))
    return parse(response)

@app.post("/buyer/provide_feedback")
async def provide_feedback(body: FeedbackRequest):
    validate_session(body.session_id)
    product_stub = get_product_stub()
    product_stub.ProvideItemFeedback(product_pb2.ItemFeedbackRequest(
        item_id=body.item_id, thumbs=body.thumbs
    ))
    customer_stub = get_customer_stub()
    feedback_type = "thumbs_up" if body.thumbs == 1 else "thumbs_down"
    response = customer_stub.UpdateSellerFeedback(customer_pb2.FeedbackRequest(
        seller_id=body.seller_id, feedback_type=feedback_type
    ))
    return parse(response)

@app.get("/buyer/get_seller_rating")
async def get_seller_rating(session_id: str, seller_id: str):
    validate_session(session_id)
    stub = get_customer_stub()
    response = stub.GetSellerRating(customer_pb2.SellerRequest(seller_id=seller_id))
    return parse(response)

@app.get("/buyer/get_purchases")
async def get_purchases(session_id: str):
    buyer_id = validate_session(session_id)
    stub = get_customer_stub()
    response = stub.GetBuyerPurchases(customer_pb2.BuyerRequest(buyer_id=str(buyer_id)))
    return parse(response)

@app.post("/buyer/make_purchase")
async def make_purchase(body: MakePurchaseRequest):
    buyer_id = validate_session(body.session_id)

    try:
        payment_approved = call_financial_service(
            body.card_name, body.card_number,
            body.expiration_date, body.security_code
        )
    except Exception as e:
        return {'status': 'error', 'message': f'Payment service unavailable: {str(e)}', 'data': {}}

    if not payment_approved:
        return {'status': 'error', 'message': 'Payment declined', 'data': {}}

    product_stub = get_product_stub()
    purchase_response = product_stub.MakePurchase(product_pb2.PurchaseRequest(
        item_id=body.item_id, buyer_id=str(buyer_id), quantity=body.quantity
    ))

    if purchase_response.status != 1:
        return parse(purchase_response)

    seller_id = json.loads(purchase_response.json_data).get('seller_id')

    customer_stub = get_customer_stub()
    customer_stub.AddPurchase(customer_pb2.AddPurchaseRequest(
        buyer_id=str(buyer_id), item_id=body.item_id,
        quantity=body.quantity, price=0.0
    ))

    if seller_id:
        customer_stub.UpdateSellerItemsSold(customer_pb2.UpdateItemsSoldRequest(
            seller_id=str(seller_id), quantity=body.quantity
        ))

    return {'status': 'success', 'message': 'Purchase completed successfully', 'data': {}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Buyer Frontend Replica')
    parser.add_argument('--replica-id', type=int, required=True, help='Replica ID (0-3)')
    args = parser.parse_args()

    replica = config.BUYER_FRONTEND_REPLICAS[args.replica_id]
    port = replica['port']

    print(f"Buyer Frontend replica {args.replica_id} starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
