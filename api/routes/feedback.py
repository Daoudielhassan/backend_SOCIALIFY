from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import MessageMetadata
from db.schemas import FeedbackRequest
from api.dependencies import get_db, get_current_user

router = APIRouter()

@router.post("/", status_code=204)
async def submit_feedback(
    req: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    msg = await db.get(MessageMetadata, req.message_id)
    if not msg or msg.user_id != user.id:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.feedback_priority = req.feedback_priority
    msg.feedback_context = req.feedback_context
    msg.used_in_retrain = False
    await db.commit()
    return 