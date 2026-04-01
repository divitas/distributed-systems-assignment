"""
Buyer Frontend Server - FastAPI + gRPC version
Includes MakePurchase with SOAP financial service
Supports running multiple frontend replicas via --port
"""

import argparse
import grpc
import json
import sys
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import uvicorn
import requests as http_requests
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "proto"))

import config
import customer_pb2
import customer_pb2_grpc
import product_pb2
import product_pb2_grpc

app = FastAPI(title="Buyer Frontend Server")


def get_customer_stub():
    channel = grpc.insecure_channel(f"{config.CUSTOMER_DB_HOST}:{config.CUSTOMER_DB_PORT}")
    return customer_pb2_grpc.CustomerDBStub(channel)


def get_product_stub():
    channel = grpc.insecure_channel(f"{config.PRODUCT_DB_HOST}:{config.PRODUCT_DB_PORT}")
    return product_pb2_grpc.ProductDBStub(channel)


def parse(response):
    return {
        "status": "success" if response.status == 1 else "error",
        "message": response.message,
        "data": json.loads(response.json_data) if response.json_data else {}
    }


def validate_session(session_id: str):
    stub = get_customer_stub()
    response = stub.ValidateSessionBuyer(customer_pb2.SessionRequest(session_id=session_id))
    if response.status != 1:
        raise HTTPException(status_code=401, detail=response.message)
    return json.loads(response.json_data)["buyer_id"]


def call_financial_service(card_name, card_number, expiration_date, security_code):
    soap_body = f"""<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ProcessPayment>
      <name>{card_name}</name>
      <card_number>{card_number}</card_number>
      <expiration_date>{expiration_date}</expiration_date>
      <security_code>{security_code}</security_code>
    </ProcessPayment>
  </soap:Body>
</soap:Envelope>"""

    response = http_requests.post(
        f"http://{config.FINANCIAL_SERVICE_HOST}:{config.FINANCIAL_SERVICE_PORT}/",
        data=soap_body,
        headers={"Content-Type": "text/xml"},
        timeout=10
    )
    return "<result>true</result>" in response.text


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


@app.post("/buyer/create_account")
async def create_account(body: CreateAccountRequest):
    stub = get_customer_stub()
    response = stub.CreateBuyer(customer_pb2.CreateBuyerRequest(
        username=body.username,
        password=body.password,
        buyer_name=body.buyer_name
    ))
    return parse(response)


@app.post("/buyer/login")
async def login(body: LoginRequest):
    stub = get_customer_stub()
    response = stub.LoginBuyer(customer_pb2.LoginRequest(
        username=body.username,
        password=body.password
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
        category=body.category,
        keywords=body.keywords
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
        session_id=body.session_id,
        buyer_id=str(buyer_id),
        item_id=body.item_id,
        quantity=body.quantity
    ))
    return parse(response)


@app.post("/buyer/remove_from_cart")
async def remove_from_cart(body: CartRequest):
    buyer_id = validate_session(body.session_id)
    stub = get_customer_stub()
    response = stub.RemoveFromCart(customer_pb2.CartRequest(
        session_id=body.session_id,
        buyer_id=str(buyer_id),
        item_id=body.item_id,
        quantity=body.quantity
    ))
    return parse(response)


@app.post("/buyer/save_cart")
async def save_cart(body: SaveCartRequest):
    buyer_id = validate_session(body.session_id)
    stub = get_customer_stub()
    response = stub.SaveCart(customer_pb2.SaveCartRequest(
        session_id=body.session_id,
        buyer_id=str(buyer_id)
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
        item_id=body.item_id,
        thumbs=body.thumbs
    ))

    customer_stub = get_customer_stub()
    feedback_type = "thumbs_up" if body.thumbs == 1 else "thumbs_down"
    response = customer_stub.UpdateSellerFeedback(customer_pb2.FeedbackRequest(
        seller_id=body.seller_id,
        feedback_type=feedback_type
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

    # Credit Card Validations
    if not re.match(r"^\d{16}$", body.card_number):
        return {"status": "error", "message": "Invalid card number: must be exactly 16 digits", "data": {}}
        
    if not re.match(r"^\d{3}$", body.security_code):
        return {"status": "error", "message": "Invalid security code: must be exactly 3 digits", "data": {}}
        
    try:
        exp_date = datetime.strptime(body.expiration_date, "%m/%y")
        current_time = datetime.now()
        if exp_date.year < current_time.year or (exp_date.year == current_time.year and exp_date.month < current_time.month):
            return {"status": "error", "message": "Card has expired", "data": {}}
    except ValueError:
        return {"status": "error", "message": "Invalid expiration date format (expected MM/YY)", "data": {}}

    try:
        payment_approved = call_financial_service(
            body.card_name,
            body.card_number,
            body.expiration_date,
            body.security_code
        )
    except Exception as e:
        return {
            "status": "error",
            "message": f"Payment service unavailable: {str(e)}",
            "data": {}
        }

    if not payment_approved:
        return {
            "status": "error",
            "message": "Payment declined",
            "data": {}
        }

    product_stub = get_product_stub()
    purchase_response = product_stub.MakePurchase(product_pb2.PurchaseRequest(
        item_id=body.item_id,
        buyer_id=str(buyer_id),
        quantity=body.quantity
    ))

    if purchase_response.status != 1:
        return parse(purchase_response)

    purchase_data = json.loads(purchase_response.json_data) if purchase_response.json_data else {}
    seller_id = purchase_data.get("seller_id")
    total_price = purchase_data.get("total_price", 0.0)

    customer_stub = get_customer_stub()

    add_purchase_response = customer_stub.AddPurchase(customer_pb2.AddPurchaseRequest(
        buyer_id=str(buyer_id),
        item_id=body.item_id,
        quantity=body.quantity,
        price=float(total_price)
    ))

    if add_purchase_response.status != 1:
        return parse(add_purchase_response)

    if seller_id is not None:
        customer_stub.UpdateSellerItemsSold(customer_pb2.UpdateItemsSoldRequest(
            seller_id=str(seller_id), 
            quantity=body.quantity
        ))

    return {
        "status": "success",
        "message": "Purchase completed successfully",
        "data": {
            "item_id": body.item_id,
            "quantity": body.quantity,
            "seller_id": seller_id,
            "total_price": total_price
        }
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=config.BUYER_FRONTEND_PORT)
    args = parser.parse_args()

    print(f"Buyer Frontend starting on port {args.port}")
    print(f"Customer DB: {config.CUSTOMER_DB_HOST}:{config.CUSTOMER_DB_PORT}")
    print(f"Product DB: {config.PRODUCT_DB_HOST}:{config.PRODUCT_DB_PORT}")
    print(f"Financial Service: {config.FINANCIAL_SERVICE_HOST}:{config.FINANCIAL_SERVICE_PORT}")

    uvicorn.run(app, host="0.0.0.0", port=args.port)