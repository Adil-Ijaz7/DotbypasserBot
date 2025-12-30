from aiogram import Router

router = Router()

from commands.start import router as start_router
from commands.co import router as co_router

router.include_router(start_router)
router.include_router(co_router)
