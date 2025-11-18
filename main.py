import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from database import db, create_document

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# -------- Properties API --------

class GeoJSONPolygon(BaseModel):
    type: str = Field(..., pattern="^Polygon$")
    coordinates: List[List[List[float]]]

class PropertyIn(BaseModel):
    title: str
    price: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    color: Optional[str] = None
    location: Dict[str, Any]  # GeoJSON Point {type:'Point', coordinates:[lon,lat]}

class PropertyOut(BaseModel):
    id: str
    title: str
    price: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    color: Optional[str] = None
    location: Dict[str, Any]


def _ensure_geo_index():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    try:
        db["property"].create_index([("location", "2dsphere")])
    except Exception:
        pass


@app.get("/api/properties")
def list_properties(limit: int = 1000):
    _ensure_geo_index()
    docs = db["property"].find({}, {"created_at": 0, "updated_at": 0}).limit(limit)
    results = []
    for d in docs:
        d["id"] = str(d.pop("_id"))
        results.append(d)
    return {"items": results}


class SearchBody(BaseModel):
    polygon: GeoJSONPolygon
    filters: Optional[Dict[str, Any]] = None


@app.post("/api/properties/search")
def search_properties(body: SearchBody, limit: int = 5000):
    _ensure_geo_index()
    geo_filter = {
        "location": {
            "$geoWithin": {
                "$geometry": {
                    "type": "Polygon",
                    "coordinates": body.polygon.coordinates,
                }
            }
        }
    }
    filter_dict = body.filters or {}
    query = {**filter_dict, **geo_filter}
    docs = db["property"].find(query, {"created_at": 0, "updated_at": 0}).limit(limit)
    results = []
    for d in docs:
        d["id"] = str(d.pop("_id"))
        results.append(d)
    return {"items": results}


@app.post("/api/properties")
def create_property(prop: PropertyIn):
    _ensure_geo_index()
    inserted_id = create_document("property", prop.model_dump())
    return {"id": inserted_id}


@app.post("/api/properties/seed")
def seed_properties():
    """Seed some demo properties across various cities for testing the map."""
    _ensure_geo_index()
    sample = [
        {"title": "SoMa Loft", "price": 1250000, "city": "San Francisco", "country": "USA", "type": "apartment", "status": "for sale", "location": {"type": "Point", "coordinates": [-122.4009, 37.7817]}},
        {"title": "Brooklyn Brownstone", "price": 2100000, "city": "New York", "country": "USA", "type": "house", "status": "for sale", "location": {"type": "Point", "coordinates": [-73.9442, 40.6782]}},
        {"title": "Downtown Condo", "price": 680000, "city": "Toronto", "country": "Canada", "type": "condo", "status": "for sale", "location": {"type": "Point", "coordinates": [-79.3832, 43.6532]}},
        {"title": "Shibuya Studio", "price": 450000, "city": "Tokyo", "country": "Japan", "type": "apartment", "status": "for rent", "location": {"type": "Point", "coordinates": [139.7006, 35.6595]}},
        {"title": "Canary Wharf Flat", "price": 920000, "city": "London", "country": "UK", "type": "apartment", "status": "for sale", "location": {"type": "Point", "coordinates": [-0.0195, 51.5054]}},
        {"title": "Bondi Beach House", "price": 1850000, "city": "Sydney", "country": "Australia", "type": "house", "status": "for sale", "location": {"type": "Point", "coordinates": [151.2743, -33.8908]}}
    ]
    for doc in sample:
        create_document("property", doc)
    return {"inserted": len(sample)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
