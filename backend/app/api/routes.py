from fastapi import APIRouter

from .admin import router as admin_router
from .compat import router as compat_router
from .native import router as native_router


router = APIRouter()
router.include_router(native_router)
router.include_router(compat_router)
router.include_router(admin_router)
