from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from typing import List

# --- CONFIGURATION ---
SERVER_NAME = "localhost\\fyt"
DATABASE_NAME = "banking_db"

# --- DATABASE SETUP ---
connection_string = f"mssql+pyodbc://@{SERVER_NAME}/{DATABASE_NAME}?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes"
engine = create_engine(connection_string)

# --- API SETUP ---
app = FastAPI(
    title="Banking NBO API",
    description="A Microservice to serve Customer Data and Next Best Offers",
    version="1.0"
)

# --- DATA MODELS (Pydantic) ---
# This defines the "Shape" of the data we send back to the user
class Product(BaseModel):
    product_name: str

class Recommendation(BaseModel):
    product: str
    probability: float
    reason: str

class CustomerProfile(BaseModel):
    customer_id: int
    holdings: List[str]
    top_recommendation: Recommendation | None # It's possible to have no recommendation

# --- ENDPOINTS (The "Routes") ---

@app.get("/")
def home():
    """Health Check"""
    return {"status": "online", "message": "Banking API is running. Go to /docs for the UI."}

@app.get("/customers/{customer_id}", response_model=CustomerProfile)
def get_customer_profile(customer_id: int):
    """
    Fetches a customer's current products and calculates their Next Best Offer.
    """
    
    # 1. Get Current Holdings
    with engine.connect() as conn:
        query_holdings = text("SELECT product_name FROM customer_products WHERE customer_id = :cid")
        result = conn.execute(query_holdings, {"cid": customer_id}).fetchall()
        
    if not result:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    current_products = [row[0] for row in result]
    
    # 2. Find Best Recommendation (The Logic)
    # We look for rules where 'current_holding' matches what the customer owns
    # We exclude products they already own
    best_rec = None
    
    with engine.connect() as conn:
        # Fetch all rules relevant to this customer's products
        # We perform a SQL 'IN' clause manually for parameter safety
        placeholders = ', '.join(f"'{p}'" for p in current_products)
        if placeholders:
            query_rules = text(f"""
                SELECT TOP 1 recommendation, probability, lift 
                FROM nbo_rules 
                WHERE current_holding IN ({placeholders})
                ORDER BY probability DESC
            """)
            rec_result = conn.execute(query_rules).fetchone()
            
            if rec_result:
                rec_product = rec_result[0]
                # Only recommend if they don't already have it
                if rec_product not in current_products:
                    best_rec = Recommendation(
                        product=rec_product,
                        probability=rec_result[1],
                        reason=f"High correlation with your existing products (Lift: {rec_result[2]:.1f})"
                    )

    return {
        "customer_id": customer_id,
        "holdings": current_products,
        "top_recommendation": best_rec
    }

@app.get("/products")
def get_all_products():
    """List all available products in the bank"""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT DISTINCT product_name FROM customer_products")).fetchall()
    return [row[0] for row in result]