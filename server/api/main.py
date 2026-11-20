import os, re, sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path: sys.path.insert(0, str(BASE_DIR))

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from analytics.processing import process_dataframe
from database import (Assessment, ClassRoom, Faculty, FacultyClassAssignment, Mark, Student, Subject, User,
    dataframe_from_database, get_db, initialize_database)
from security import create_access_token, current_user, hash_password, require_roles, verify_password
from services.class_service import build_class_service
from services.student_service import build_student_service
from services.manual_service import build_manual_service

MODEL_PATH = str(BASE_DIR / "ml" / "risk_model.pkl")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173").split(",")]
app = FastAPI(title="Student Performance Intelligence API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # Allows the Render static-site hostname while retaining explicit local origins.
    allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX", r"https://[a-z0-9-]+\.onrender\.com"),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=128)
class FacultyRequest(LoginRequest):
    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=3, max_length=160)
class ClassRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
class ClassUpdateRequest(ClassRequest):
    pass
class StudentRequest(BaseModel):
    student_code: str = Field(min_length=1, max_length=40)
    full_name: str = Field(min_length=2, max_length=160)
    class_code: str
class StudentUpdateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    class_code: str
class AssignmentRequest(BaseModel):
    faculty_id: int
    class_code: str
class MarkRequest(BaseModel):
    class_code: str; student_code: str
    subject: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=160)
    assessment_name: str = Field(min_length=1, max_length=160)
    assessment_date: date
    marks_obtained: float = Field(ge=0); total_marks: float = Field(gt=0)
    time_taken: float = Field(ge=0); questions_attempted: int = Field(ge=0); questions_correct: int = Field(ge=0)
    @model_validator(mode="after")
    def valid(self):
        if self.marks_obtained > self.total_marks: raise ValueError("marks_obtained cannot exceed total_marks")
        if self.questions_correct > self.questions_attempted: raise ValueError("questions_correct cannot exceed questions_attempted")
        return self

class ManualPredictionRequest(BaseModel):
    student_id: str; student_name: str; class_id: str; subject: str; topic: str; assessment_name: str
    marks_obtained: float; total_marks: float; attempt_date: str; time_taken: float; questions_attempted: int; questions_correct: int

@app.on_event("startup")
def startup(): initialize_database()
def room(db, code):
    value = db.scalar(select(ClassRoom).where(ClassRoom.code == code))
    if not value: raise HTTPException(404, "Class not found")
    return value
def class_key(value: str) -> str:
    """Treat equivalent user-facing labels such as `Class 10A` and `10A` alike."""
    key = re.sub(r"[^a-z0-9]", "", value.casefold())
    return key[5:] if key.startswith("class") else key
def duplicate_class(db, code: str, name: str, excluding_id: int | None = None) -> bool:
    target = {class_key(code), class_key(name)}
    query = select(ClassRoom)
    if excluding_id is not None:
        query = query.where(ClassRoom.id != excluding_id)
    return any(target & {class_key(value.code), class_key(value.name)} for value in db.scalars(query))
def class_summary(value: ClassRoom):
    return {
        "id": value.id, "code": value.code, "name": value.name,
        "student_count": len(value.students),
        "faculty": [{"id": assignment.faculty.id, "assignment_id": assignment.id, "full_name": assignment.faculty.full_name}
                    for assignment in value.assignments],
    }
def profile(user): return {"id": user.id, "username": user.username, "role": user.role, "full_name": user.faculty.full_name if user.faculty else "Administrator"}
def authorize_room(db, user, classroom):
    if user.role == "admin": return
    if not user.faculty or not db.scalar(select(FacultyClassAssignment.id).where(FacultyClassAssignment.faculty_id == user.faculty.id, FacultyClassAssignment.class_id == classroom.id)):
        raise HTTPException(403, "You are not assigned to this class")
def frame(db):
    value = dataframe_from_database(db)
    if value.empty: raise HTTPException(404, "No assessment data is available")
    return process_dataframe(value)

@app.get("/")
def root(): return {"message": "Student Performance Intelligence API is running"}
@app.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": profile(user)}
@app.get("/auth/me")
def me(user: User = Depends(current_user)): return profile(user)

@app.get("/classes")
def classes(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(ClassRoom)
    if user.role == "faculty": query = query.join(FacultyClassAssignment).where(FacultyClassAssignment.faculty_id == user.faculty.id)
    return {"classes": [x.code for x in db.scalars(query.order_by(ClassRoom.code)).all()]}
@app.get("/students")
def students(class_code: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Student, ClassRoom).join(ClassRoom)
    if class_code:
        classroom = room(db, class_code); authorize_room(db, user, classroom); query = query.where(Student.class_id == classroom.id)
    elif user.role == "faculty": query = query.join(FacultyClassAssignment, FacultyClassAssignment.class_id == ClassRoom.id).where(FacultyClassAssignment.faculty_id == user.faculty.id)
    return {"students": [{"student_id": s.student_code, "student_name": s.full_name, "class_id": c.code} for s,c in db.execute(query.order_by(Student.full_name)).all()]}
@app.get("/student/{student_id}")
def student_report(student_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    student = db.scalar(select(Student).where(Student.student_code == student_id))
    if not student: raise HTTPException(404, "Student not found")
    authorize_room(db, user, student.classroom); result = build_student_service(frame(db), MODEL_PATH, student_id)
    if not result: raise HTTPException(422, "Student exists but has no assessment records yet. Add marks before running analytics.")
    return result
@app.get("/class/{class_id}")
def class_report(class_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    classroom = room(db, class_id); authorize_room(db, user, classroom)
    enrolled_student_count = db.scalar(select(func.count(Student.id)).where(Student.class_id == classroom.id))
    result = build_class_service(frame(db), class_id, enrolled_student_count)
    if not result: raise HTTPException(404, "Class has no assessments")
    return result
@app.post("/manual-prediction")
def manual_prediction(payload: ManualPredictionRequest, user: User = Depends(current_user)):
    # The predictor remains an unsaved sandbox. Persisted faculty entries use POST /marks.
    import pandas as pd
    return build_manual_service(pd.DataFrame([payload.model_dump()]), MODEL_PATH)

@app.get("/admin/overview")
def admin_overview(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    data = frame(db)
    return {"total_students": db.scalar(select(func.count(Student.id))), "total_faculty": db.scalar(select(func.count(Faculty.id))), "total_classes": db.scalar(select(func.count(ClassRoom.id))), "total_assessments": db.scalar(select(func.count(Mark.id))), "overall_average": round(float(data.score_percentage.mean()), 2), "overall_accuracy": round(float(data.accuracy.mean()), 2)}
@app.get("/admin/faculty")
def list_faculty(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    return [{"id": f.id, "username": f.user.username, "full_name": f.full_name, "email": f.email, "is_active": f.user.is_active, "classes": [db.get(ClassRoom,a.class_id).code for a in f.assignments]} for f in db.scalars(select(Faculty)).all()]
@app.get("/admin/classes")
def list_admin_classes(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    return [class_summary(value) for value in db.scalars(select(ClassRoom).order_by(ClassRoom.code)).all()]
@app.get("/admin/students")
def list_admin_students(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    return [{"id": student.id, "student_code": student.student_code, "full_name": student.full_name,
             "class_code": student.classroom.code, "class_name": student.classroom.name}
            for student in db.scalars(select(Student).order_by(Student.full_name)).all()]
@app.post("/admin/faculty", status_code=201)
def create_faculty(payload: FacultyRequest, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    if db.scalar(select(User).where(User.username == payload.username)) or db.scalar(select(Faculty).where(Faculty.email == payload.email)): raise HTTPException(409, "Username or email already exists")
    faculty = Faculty(user=User(username=payload.username, password_hash=hash_password(payload.password), role="faculty"), full_name=payload.full_name, email=payload.email); db.add(faculty); db.commit(); db.refresh(faculty); return {"id": faculty.id, "full_name": faculty.full_name}
@app.patch("/admin/faculty/{faculty_id}/active")
def set_active(faculty_id: int, active: bool, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    faculty = db.get(Faculty, faculty_id)
    if not faculty: raise HTTPException(404, "Faculty not found")
    faculty.user.is_active = active; db.commit(); return {"id": faculty_id, "is_active": active}
@app.delete("/admin/faculty/{faculty_id}", status_code=204)
def delete_faculty(faculty_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    faculty = db.get(Faculty, faculty_id)
    if not faculty: raise HTTPException(404, "Faculty not found")
    db.delete(faculty.user)
    db.commit()
@app.post("/admin/classes", status_code=201)
def create_class(payload: ClassRequest, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    if duplicate_class(db, payload.code, payload.name): raise HTTPException(409, "An equivalent class code or name already exists")
    value = ClassRoom(code=payload.code, name=payload.name); db.add(value); db.commit(); return {"code": value.code, "name": value.name}
@app.patch("/admin/classes/{class_id}")
def update_class(class_id: int, payload: ClassUpdateRequest, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    value = db.get(ClassRoom, class_id)
    if not value: raise HTTPException(404, "Class not found")
    if duplicate_class(db, payload.code, payload.name, class_id): raise HTTPException(409, "An equivalent class code or name already exists")
    value.code, value.name = payload.code, payload.name
    db.commit(); db.refresh(value)
    return class_summary(value)
@app.delete("/admin/classes/{class_id}", status_code=204)
def delete_class(class_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    value = db.get(ClassRoom, class_id)
    if not value: raise HTTPException(404, "Class not found")
    if value.students or db.scalar(select(Assessment.id).where(Assessment.class_id == class_id).limit(1)):
        raise HTTPException(409, "Cannot delete a class that contains students or assessment history")
    db.delete(value)
    db.commit()
@app.post("/admin/students", status_code=201)
def create_student(payload: StudentRequest, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    if db.scalar(select(Student).where(Student.student_code == payload.student_code)): raise HTTPException(409, "Student ID already exists")
    classroom = room(db,payload.class_code); value=Student(student_code=payload.student_code,full_name=payload.full_name,class_id=classroom.id);db.add(value);db.commit();return {"student_id":value.student_code,"student_name":value.full_name,"class_id":classroom.code}
@app.patch("/admin/students/{student_id}")
def update_student(student_id: int, payload: StudentUpdateRequest, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    value = db.get(Student, student_id)
    if not value: raise HTTPException(404, "Student not found")
    classroom = room(db, payload.class_code)
    value.full_name, value.class_id = payload.full_name, classroom.id
    db.commit()
    return {"id": value.id, "student_code": value.student_code, "full_name": value.full_name, "class_code": classroom.code}
@app.delete("/admin/students/{student_id}", status_code=204)
def delete_student(student_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    value = db.get(Student, student_id)
    if not value: raise HTTPException(404, "Student not found")
    if db.scalar(select(Mark.id).where(Mark.student_id == student_id).limit(1)):
        raise HTTPException(409, "Cannot delete a student with assessment history")
    db.delete(value)
    db.commit()
@app.post("/admin/assignments", status_code=201)
def assign(payload: AssignmentRequest, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    faculty=db.get(Faculty,payload.faculty_id); classroom=room(db,payload.class_code)
    if not faculty: raise HTTPException(404,"Faculty not found")
    if db.scalar(select(FacultyClassAssignment).where(FacultyClassAssignment.faculty_id==faculty.id,FacultyClassAssignment.class_id==classroom.id)): raise HTTPException(409,"Faculty is already assigned")
    db.add(FacultyClassAssignment(faculty_id=faculty.id,class_id=classroom.id));db.commit();return {"faculty_id":faculty.id,"class_code":classroom.code}
@app.delete("/admin/assignments/{assignment_id}", status_code=204)
def remove_assignment(assignment_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    assignment = db.get(FacultyClassAssignment, assignment_id)
    if not assignment: raise HTTPException(404, "Faculty assignment not found")
    db.delete(assignment)
    db.commit()

def persist_mark(payload, db, user, mark_id=None):
    classroom=room(db,payload.class_code);authorize_room(db,user,classroom)
    student=db.scalar(select(Student).where(Student.student_code==payload.student_code))
    if not student or student.class_id!=classroom.id: raise HTTPException(422,"Student does not belong to the selected class")
    subject=db.scalar(select(Subject).where(Subject.name==payload.subject))
    if not subject: subject=Subject(name=payload.subject);db.add(subject);db.flush()
    if mark_id:
        mark=db.get(Mark,mark_id)
        if not mark: raise HTTPException(404,"Mark entry not found")
        authorize_room(db,user,mark.assessment and db.get(ClassRoom,mark.assessment.class_id))
        mark.marks_obtained,mark.total_marks,mark.time_taken,mark.questions_attempted,mark.questions_correct=payload.marks_obtained,payload.total_marks,payload.time_taken,payload.questions_attempted,payload.questions_correct
        mark.assessment.subject_id,mark.assessment.topic,mark.assessment.name,mark.assessment.assessment_date=subject.id,payload.topic,payload.assessment_name,payload.assessment_date
    else:
        assessment=Assessment(class_id=classroom.id,subject_id=subject.id,topic=payload.topic,name=payload.assessment_name,assessment_date=payload.assessment_date,created_by=user.id);db.add(assessment);db.flush()
        mark=Mark(assessment_id=assessment.id,student_id=student.id,marks_obtained=payload.marks_obtained,total_marks=payload.total_marks,time_taken=payload.time_taken,questions_attempted=payload.questions_attempted,questions_correct=payload.questions_correct);db.add(mark)
    db.commit();db.refresh(mark);return {"id":mark.id,"message":"Marks saved. Analytics update immediately."}
@app.post("/marks",status_code=201)
def create_mark(payload:MarkRequest,db:Session=Depends(get_db),user:User=Depends(require_roles("admin","faculty"))): return persist_mark(payload,db,user)
@app.put("/marks/{mark_id}")
def update_mark(mark_id:int,payload:MarkRequest,db:Session=Depends(get_db),user:User=Depends(require_roles("admin","faculty"))): return persist_mark(payload,db,user,mark_id)
@app.get("/faculty/dashboard")
def faculty_dashboard(db:Session=Depends(get_db),user:User=Depends(require_roles("faculty"))):
    rooms=db.scalars(select(ClassRoom).join(FacultyClassAssignment).where(FacultyClassAssignment.faculty_id==user.faculty.id)).all();ids=[x.id for x in rooms]
    return {"assigned_classes":[x.code for x in rooms],"total_students":db.scalar(select(func.count(Student.id)).where(Student.class_id.in_(ids))) if ids else 0,"total_assessments":db.scalar(select(func.count(Mark.id)).join(Assessment).where(Assessment.class_id.in_(ids))) if ids else 0}
