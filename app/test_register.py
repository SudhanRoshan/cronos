from app.database import engine, Base
from app.main import register_tenant

# Step 1: create all tables (tenants, jobs, logs - though only Tenant model exists so far)
Base.metadata.create_all(engine)

# Step 2: register a tenant
raw_key = register_tenant("ShopEasy")

# Step 3: see the result
print("Raw API key (show this once):", raw_key)