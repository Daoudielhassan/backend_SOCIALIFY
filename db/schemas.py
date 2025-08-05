from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    whatsapp_number: Optional[str] = None
    is_active: Optional[bool] = True

class UserCreate(UserBase):
    password: str

class UserOut(UserBase):
    id: int
    created_at: datetime
    
    model_config = {"from_attributes": True}

class MessageBase(BaseModel):
    source: str
    external_id: Optional[str] = None
    sender: Optional[str] = None
    subject: Optional[str] = None
    body: str
    received_at: datetime

class MessageCreate(MessageBase):
    pass

class MessageOut(MessageBase):
    id: int
    predicted_priority: Optional[str]
    predicted_context: Optional[str]
    prediction_confidence: Optional[float]
    feedback_priority: Optional[str]
    feedback_context: Optional[str]
    used_in_retrain: Optional[bool]
    created_at: datetime
    
    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[EmailStr] = None

class PredictionRequest(BaseModel):
    message: str

class PredictionResponse(BaseModel):
    context: str
    priority: str
    confidence: float

class FeedbackRequest(BaseModel):
    message_id: int
    feedback_priority: str
    feedback_context: str

# Analytics schemas
class AnalyticsResponse(BaseModel):
    total_messages: int
    priority_distribution: dict
    source_distribution: dict
    context_distribution: dict
    daily_messages: List[dict]
    feedback_count: int
    accuracy_percentage: float
    date_range: dict

class DashboardStats(BaseModel):
    totals: dict
    priority_breakdown: dict
    source_breakdown: dict
    recent_activity: List[dict]
    user_info: dict

# User settings schemas
class UserSettingsResponse(BaseModel):
    user_info: dict
    preferences: dict
    integration_status: dict

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    whatsapp_number: Optional[str] = None

# Message fetch schemas
class MessageFetchRequest(BaseModel):
    source: str = "gmail"
    force_sync: bool = False

class MessageFetchResponse(BaseModel):
    success: bool
    fetched_count: int
    messages: List[MessageOut]
    errors: List[str]
    last_sync: str 