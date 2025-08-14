from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
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
    # First, verify the message exists and belongs to the user
    query = await db.execute(
        select(MessageMetadata).where(
            MessageMetadata.id == req.message_id,
            MessageMetadata.user_id == user.id
        )
    )
    msg = query.scalar_one_or_none()
    
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Update the message with feedback using SQLAlchemy update
    await db.execute(
        update(MessageMetadata)
        .where(MessageMetadata.id == req.message_id)
        .values(
            feedback_priority=req.feedback_priority,
            feedback_context=req.feedback_context,
            used_in_retrain=False
        )
    )
    await db.commit()
    return 