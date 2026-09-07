from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import Base, engine
from .seed import seed
from .routers import auth as auth_router
from .routers import buyer as buyer_router
from .routers import farmer as farmer_router
from .routers import vendor as vendor_router
from .routers import admin as admin_router
from .routers import agronomist as agronomist_router
from .routers import logistics as logistics_router
from .routers import fulfilment as fulfilment_router
from .routers import reconciliation as reconciliation_router

app = FastAPI(
    title="Farm Master API",
    description="Stage 6 backend foundation: RBAC (7 roles), audit logging, "
                "and the Buyer commitment-fee flow. See Farm_Master_SDD_Stage6.docx "
                "and Farm_Master_API_Documentation_Stage6.docx.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(buyer_router.router)
app.include_router(farmer_router.router)
app.include_router(vendor_router.router)
app.include_router(admin_router.router)
app.include_router(agronomist_router.router)
app.include_router(logistics_router.router)
app.include_router(fulfilment_router.router)
app.include_router(reconciliation_router.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/buyer-flow")
    def buyer_flow_page():
        return FileResponse(str(FRONTEND_DIR / "buyer_commitment_fee_flow_live.html"))

    @app.get("/farmer-flow")
    def farmer_flow_page():
        return FileResponse(str(FRONTEND_DIR / "farmer_opportunity_formula_flow_live.html"))

    @app.get("/vendor-flow")
    def vendor_flow_page():
        return FileResponse(str(FRONTEND_DIR / "vendor_mechanisation_request_flow_live.html"))

    @app.get("/matching-flow")
    def matching_flow_page():
        return FileResponse(str(FRONTEND_DIR / "agronomist_matching_queue_flow_live.html"))

    @app.get("/formula-builder-flow")
    def formula_builder_flow_page():
        return FileResponse(str(FRONTEND_DIR / "production_formula_builder_flow_live.html"))

    @app.get("/register-flow")
    def register_flow_page():
        return FileResponse(str(FRONTEND_DIR / "registration_otp_flow_live.html"))

    @app.get("/dispatch-flow")
    def dispatch_flow_page():
        return FileResponse(str(FRONTEND_DIR / "logistics_dispatch_flow_live.html"))

    @app.get("/harvest-pickup-flow")
    def harvest_pickup_flow_page():
        return FileResponse(str(FRONTEND_DIR / "farmer_harvest_pickup_flow_live.html"))

    @app.get("/fulfilment-intake-flow")
    def fulfilment_intake_flow_page():
        return FileResponse(str(FRONTEND_DIR / "fulfilment_intake_flow_live.html"))

    @app.get("/reconciliation-flow")
    def reconciliation_flow_page():
        return FileResponse(str(FRONTEND_DIR / "finance_reconciliation_flow_live.html"))

    @app.get("/order-inputs-flow")
    def order_inputs_flow_page():
        return FileResponse(str(FRONTEND_DIR / "farmer_order_inputs_flow_live.html"))

    @app.get("/vendor-catalogue-flow")
    def vendor_catalogue_flow_page():
        return FileResponse(str(FRONTEND_DIR / "vendor_product_catalogue_flow_live.html"))


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    seed()


@app.get("/health")
def health():
    return {"status": "ok"}
