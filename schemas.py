"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Any, Dict

# ---------------------------------------------
# Task approval domain schemas (used by database viewer and API)
# ---------------------------------------------

FieldType = Literal["text", "number", "date", "select", "checkbox"]

class FormField(BaseModel):
    key: str = Field(..., description="Unique key for this field")
    label: str = Field(..., description="Label shown to the user")
    type: FieldType = Field("text", description="Input type")
    required: bool = Field(False, description="Whether this field is required")
    options: Optional[List[str]] = Field(None, description="Options for select type")

class TemplateStep(BaseModel):
    name: str = Field(..., description="Step name")
    description: Optional[str] = Field(None, description="What happens in this step")
    fields: List[FormField] = Field(default_factory=list, description="Form fields for this step")

class TaskTemplate(BaseModel):
    title: str = Field(..., description="Template title")
    description: Optional[str] = Field(None, description="Template description")
    steps: List[TemplateStep] = Field(..., description="Ordered steps")

class StepInstance(BaseModel):
    name: str
    description: Optional[str] = None
    fields: List[FormField] = Field(default_factory=list)
    status: Literal["pending", "in_review", "approved", "rejected"] = "pending"
    form_data: Dict[str, Any] = Field(default_factory=dict)
    comment: Optional[str] = None
    approved_by: Optional[str] = None

class TaskInstance(BaseModel):
    template_id: str
    title: str
    assignee: Optional[str] = None
    steps: List[StepInstance]
    current_step_index: int = 0
    status: Literal["draft", "submitted", "in_progress", "approved", "rejected"] = "submitted"

# ---------------------------------------------
# Example generic schemas retained for reference
# ---------------------------------------------

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Add your own schemas here:
# --------------------------------------------------

# Note: The Flames database viewer will automatically:
# 1. Read these schemas from GET /schema endpoint
# 2. Use them for document validation when creating/editing
# 3. Handle all database operations (CRUD) directly
# 4. You don't need to create any database endpoints!
