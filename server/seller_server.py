"""
Seller Frontend Server - FastAPI + gRPC version
"""

import grpc
import json
import sys
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'proto'))

import config
import customer_pb2
import customer_pb2_grpc
import product_pb2
import product_pb2_grpc

app = FastAPI(title="Seller Frontend Server")

# ========== gRPC Clients ==========

def get_customer_stub():
    channel = grpc.insecure_channel(f'{config.CUSTOMER_DB_HOST}:{config.CUSTOMER_DB_PORT}')
    return customer_pb2_grpc.CustomerDBStub(channel)

def get_product_stub():
    channel = grpc.insecure_channel(f'{config.PRODUCT_DB_HOST}:{config.PRODUCT_DB_PORT}')
    return product_pb2_grpc.ProductDBStub(channel)

def parse(response):
    """Convert gRPC DBResponse to dict"""
    return {
        'status': 'success' if response.status == 1 else 'error',
        'message': response.message,
        'data': json.loads(response.json_data) if response.json_data else {}
    }

def validate_session(session_id: str):
    """Validate seller session, return seller_id or raise"""
    stub = get_customer_stub()
    response = stub.ValidateSessionSeller(customer_pb2.SessionRequest(session_id=session_id))
    if response.status != 1:
        raise HTTPException(status_code=401, detail=response.message)
    return json.loads(response.json_data)['seller_id']

# ========== Request Models ==========

class CreateAccountRequest(BaseModel):
    username: str
    password: str
    seller_name: str

class LoginRequest(BaseModel):
    username: str
    password: str

class SessionRequest(BaseModel):
    session_id: str

class RegisterItemRequest(BaseModel):
    session_id: str
    name: str
    category: int
    keywords: List[str] = []
    condition: str
    price: float
    quantity: int

class ChangePriceRequest(BaseModel):
    session_id: str
    item_id: str
    new_price: float

class UpdateUnitsRequest(BaseModel):
    session_id: str
    item_id: str
    quantity: int

# ========== Routes ==========

@app.post("/seller/create_account")
async def create_account(body: CreateAccountRequest):
    if not body.username or not body.password or not body.seller_name:
        raise HTTPException(status_code=400, detail="Username, password, and seller name are required")
    stub = get_customer_stub()
    response = stub.CreateSeller(customer_pb2.CreateSellerRequest(
        username=body.username,
        password=body.password,
        seller_name=body.seller_name
    ))
    return parse(response)

@app.post("/seller/login")
async def login(body: LoginRequest):
    if not body.username or not body.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    stub = get_customer_stub()
    response = stub.LoginSeller(customer_pb2.LoginRequest(
        username=body.username,
        password=body.password
    ))
    return parse(response)

@app.post("/seller/logout")
async def logout(body: SessionRequest):
    stub = get_customer_stub()
    response = stub.LogoutSeller(customer_pb2.SessionRequest(session_id=body.session_id))
    return parse(response)

@app.post("/seller/restore_session")
async def restore_session(body: SessionRequest):
    stub = get_customer_stub()
    response = stub.RestoreSessionSeller(customer_pb2.SessionRequest(session_id=body.session_id))
    return parse(response)

@app.get("/seller/get_rating")
async def get_rating(session_id: str):
    seller_id = validate_session(session_id)
    stub = get_customer_stub()
    response = stub.GetSellerRating(customer_pb2.SellerRequest(seller_id=str(seller_id)))
    return parse(response)

@app.post("/seller/register_item")
async def register_item(body: RegisterItemRequest):
    seller_id = validate_session(body.session_id)

    # Validate
    if not body.name or body.category is None or not body.condition or body.price is None or body.quantity is None:
        raise HTTPException(status_code=400, detail="Missing required fields")
    if body.price < 0 or body.quantity < 0 or body.category < 1 or body.category > 8:
        raise HTTPException(status_code=400, detail="Invalid price, quantity, or category")

    stub = get_product_stub()
    response = stub.RegisterItem(product_pb2.RegisterItemRequest(
        seller_id=str(seller_id),
        name=body.name,
        category=body.category,
        keywords=body.keywords,
        condition=body.condition,
        price=body.price,
        quantity=body.quantity
    ))
    return parse(response)

@app.post("/seller/change_price")
async def change_price(body: ChangePriceRequest):
    seller_id = validate_session(body.session_id)
    if body.new_price < 0:
        raise HTTPException(status_code=400, detail="Invalid price")
    stub = get_product_stub()
    response = stub.UpdateItemPrice(product_pb2.UpdatePriceRequest(
        item_id=body.item_id,
        seller_id=str(seller_id),
        new_price=body.new_price
    ))
    return parse(response)

@app.post("/seller/update_units")
async def update_units(body: UpdateUnitsRequest):
    seller_id = validate_session(body.session_id)
    if body.quantity < 0:
        raise HTTPException(status_code=400, detail="Invalid quantity")
    stub = get_product_stub()
    response = stub.UpdateItemQuantity(product_pb2.UpdateQuantityRequest(
        item_id=body.item_id,
        seller_id=str(seller_id),
        quantity_to_remove=body.quantity
    ))
    return parse(response)

@app.get("/seller/display_items")
async def display_items(session_id: str):
    seller_id = validate_session(session_id)
    stub = get_product_stub()
    response = stub.GetSellerItems(product_pb2.SellerRequest(seller_id=str(seller_id)))
    return parse(response)


if __name__ == '__main__':
    print(f"Seller Frontend starting on port {config.SELLER_FRONTEND_PORT}")
    print(f"Customer DB: {config.CUSTOMER_DB_HOST}:{config.CUSTOMER_DB_PORT}")
    print(f"Product DB:  {config.PRODUCT_DB_HOST}:{config.PRODUCT_DB_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=config.SELLER_FRONTEND_PORT)