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
from .routers import mofa as mofa_router
from .routers import reporting as reporting_router
from .routers import dashboard as dashboard_router
from .routers import ussd as ussd_router
from .routers import listings as listings_router
from .uploads import UPLOADS_DIR

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
app.include_router(mofa_router.router)
app.include_router(reporting_router.router)
app.include_router(dashboard_router.router)
app.include_router(ussd_router.router)
app.include_router(listings_router.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    # FileResponse's default Last-Modified/ETag headers let browsers cache
    # these pages heuristically with no explicit Cache-Control -- during
    # active development a browser tab left open (or even a fresh load in
    # some browsers' heuristic-caching window) can keep serving an edited-
    # then-reverted-in-the-browser's-cache version of one of these files
    # after a real on-disk fix, with no visible error. Every -flow route
    # below goes through this helper so a hard refresh is never required
    # to see the current file.
    def _flow_page(filename: str) -> FileResponse:
        return FileResponse(
            str(FRONTEND_DIR / filename),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
        )

    @app.get("/buyer-flow")
    def buyer_flow_page():
        return _flow_page("buyer_commitment_fee_flow_live.html")

    @app.get("/farmer-flow")
    def farmer_flow_page():
        return _flow_page("farmer_opportunity_formula_flow_live.html")

    @app.get("/vendor-flow")
    def vendor_flow_page():
        return _flow_page("vendor_mechanisation_request_flow_live.html")

    @app.get("/matching-flow")
    def matching_flow_page():
        return _flow_page("agronomist_matching_queue_flow_live.html")

    @app.get("/formula-builder-flow")
    def formula_builder_flow_page():
        return _flow_page("production_formula_builder_flow_live.html")

    @app.get("/register-flow")
    def register_flow_page():
        return _flow_page("registration_otp_flow_live.html")

    @app.get("/dispatch-flow")
    def dispatch_flow_page():
        return _flow_page("logistics_dispatch_flow_live.html")

    @app.get("/harvest-pickup-flow")
    def harvest_pickup_flow_page():
        return _flow_page("farmer_harvest_pickup_flow_live.html")

    @app.get("/fulfilment-intake-flow")
    def fulfilment_intake_flow_page():
        return _flow_page("fulfilment_intake_flow_live.html")

    @app.get("/reconciliation-flow")
    def reconciliation_flow_page():
        return _flow_page("finance_reconciliation_flow_live.html")

    @app.get("/order-inputs-flow")
    def order_inputs_flow_page():
        return _flow_page("farmer_order_inputs_flow_live.html")

    @app.get("/vendor-catalogue-flow")
    def vendor_catalogue_flow_page():
        return _flow_page("vendor_product_catalogue_flow_live.html")

    @app.get("/mofa-report-flow")
    def mofa_report_flow_page():
        return _flow_page("mofa_compliance_report_flow_live.html")

    @app.get("/user-admin-flow")
    def user_admin_flow_page():
        return _flow_page("useradmin_flow_live.html")

    @app.get("/visit-logs-flow")
    def visit_logs_flow_page():
        return _flow_page("agronomist_visit_logs_flow_live.html")

    @app.get("/proof-trunking-flow")
    def proof_trunking_flow_page():
        return _flow_page("logistics_proof_trunking_flow_live.html")

    @app.get("/reporting-flow")
    def reporting_flow_page():
        return _flow_page("finance_reporting_flow_live.html")

    @app.get("/approvals-flow")
    def approvals_flow_page():
        return _flow_page("approvals_flow_live.html")

    @app.get("/control-centre-flow")
    def control_centre_flow_page():
        return _flow_page("control_centre_dashboard_flow_live.html")

    @app.get("/buyer-dashboard-flow")
    def buyer_dashboard_flow_page():
        return _flow_page("buyer_dashboard_flow_live.html")

    @app.get("/farmer-dashboard-flow")
    def farmer_dashboard_flow_page():
        return _flow_page("farmer_dashboard_flow_live.html")

    @app.get("/vendor-dashboard-flow")
    def vendor_dashboard_flow_page():
        return _flow_page("vendor_dashboard_flow_live.html")

    @app.get("/ussd-sms-flow")
    def ussd_sms_flow_page():
        return _flow_page("ussd_sms_flow_live.html")

    @app.get("/vendor-listings-flow")
    def vendor_listings_flow_page():
        return _flow_page("vendor_listings_flow_live.html")

    @app.get("/listing-review-flow")
    def listing_review_flow_page():
        return _flow_page("listing_review_queue_flow_live.html")


UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    seed()


@app.get("/health")
def health():
    return {"status": "ok"}
