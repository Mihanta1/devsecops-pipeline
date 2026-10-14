from fastapi import APIRouter

router=APIRouter()
@router.get("/health", tags=["health"])
async def read_health():
    return {"status": "ok"}
