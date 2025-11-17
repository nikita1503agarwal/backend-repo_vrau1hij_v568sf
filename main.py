import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import TaskTemplate, TaskInstance, StepInstance, TemplateStep, FormField

app = FastAPI(title="Task Approval API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utils
class ObjectIdStr(str):
    @classmethod
    def validate(cls, v):
        try:
            return str(ObjectId(v))
        except Exception:
            raise ValueError("Invalid ObjectId")


def to_str_id(doc: Dict[str, Any]):
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


@app.get("/")
def read_root():
    return {"message": "Task Approval Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


# Seed a default template if none exists
@app.post("/api/templates/seed")
def seed_template():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    existing = db["tasktemplate"].find_one({"title": "General Request Approval"})
    if existing:
        return to_str_id(existing)

    template = TaskTemplate(
        title="General Request Approval",
        description="Three-step approval with basic fields",
        steps=[
            TemplateStep(
                name="Details",
                description="Provide request details",
                fields=[
                    FormField(key="subject", label="Subject", type="text", required=True),
                    FormField(key="amount", label="Amount", type="number", required=True),
                    FormField(key="due_date", label="Due Date", type="date"),
                ],
            ),
            TemplateStep(
                name="Manager Review",
                description="Manager approves or rejects",
                fields=[
                    FormField(key="manager_comment", label="Manager Comment", type="text"),
                ],
            ),
            TemplateStep(
                name="Finance Review",
                description="Finance verifies and approves",
                fields=[
                    FormField(key="cost_center", label="Cost Center", type="select", options=["1001","2002","3003"], required=True),
                ],
            ),
        ],
    )

    template_dict = template.model_dump()
    inserted_id = create_document("tasktemplate", template_dict)
    doc = db["tasktemplate"].find_one({"_id": ObjectId(inserted_id)})
    return to_str_id(doc)


# Create a task instance from a template
class CreateTaskRequest(BaseModel):
    template_id: str
    title: Optional[str] = None
    assignee: Optional[str] = None


@app.post("/api/tasks")
def create_task(req: CreateTaskRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    tmpl = db["tasktemplate"].find_one({"_id": ObjectId(req.template_id)})
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    steps: List[StepInstance] = []
    for s in tmpl["steps"]:
        step = StepInstance(
            name=s["name"],
            description=s.get("description"),
            fields=[FormField(**f) for f in s.get("fields", [])],
            status="pending",
            form_data={},
        )
        steps.append(step)

    task = TaskInstance(
        template_id=str(tmpl["_id"]),
        title=req.title or tmpl.get("title", "Task"),
        assignee=req.assignee,
        steps=steps,
        current_step_index=0,
        status="submitted",
    )
    inserted_id = create_document("taskinstance", task.model_dump())
    doc = db["taskinstance"].find_one({"_id": ObjectId(inserted_id)})
    return to_str_id(doc)


@app.get("/api/tasks")
def list_tasks(status: Optional[str] = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    filter_q: Dict[str, Any] = {}
    if status:
        filter_q["status"] = status
    tasks = list(db["taskinstance"].find(filter_q).sort("created_at", -1))
    for t in tasks:
        to_str_id(t)
    return tasks


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    doc = db["taskinstance"].find_one({"_id": ObjectId(task_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    return to_str_id(doc)


class SubmitStepForm(BaseModel):
    data: Dict[str, Any]


@app.post("/api/tasks/{task_id}/steps/{index}/submit")
def submit_step_form(task_id: str, index: int, payload: SubmitStepForm):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    task = db["taskinstance"].find_one({"_id": ObjectId(task_id)})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if index < 0 or index >= len(task["steps"]):
        raise HTTPException(status_code=400, detail="Invalid step index")

    # save form data and set in_review
    task["steps"][index]["form_data"] = payload.data
    task["steps"][index]["status"] = "in_review"
    db["taskinstance"].update_one({"_id": ObjectId(task_id)}, {"$set": {"steps": task["steps"]}})
    return {"ok": True}


class ApproveReject(BaseModel):
    action: str  # "approve" | "reject"
    comment: Optional[str] = None
    actor: Optional[str] = None


@app.post("/api/tasks/{task_id}/steps/{index}/decision")
def decide_step(task_id: str, index: int, payload: ApproveReject):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    task = db["taskinstance"].find_one({"_id": ObjectId(task_id)})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if index < 0 or index >= len(task["steps"]):
        raise HTTPException(status_code=400, detail="Invalid step index")

    action = payload.action.lower()
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action")

    step = task["steps"][index]
    step["comment"] = payload.comment
    step["approved_by"] = payload.actor
    step["status"] = "approved" if action == "approve" else "rejected"

    # Progress task status
    next_index = index + 1
    if step["status"] == "rejected":
        task_status = "rejected"
    elif next_index >= len(task["steps"]):
        task_status = "approved"
    else:
        task_status = "in_progress"

    update = {
        "steps": task["steps"],
        "current_step_index": min(next_index, len(task["steps"]) - 1),
        "status": task_status,
    }

    db["taskinstance"].update_one({"_id": ObjectId(task_id)}, {"$set": update})
    doc = db["taskinstance"].find_one({"_id": ObjectId(task_id)})
    return to_str_id(doc)


# Expose schemas for internal tools
@app.get("/schema")
def get_schema():
    # This endpoint helps the built-in DB viewer if used
    return {
        "collections": [
            "tasktemplate",
            "taskinstance",
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
