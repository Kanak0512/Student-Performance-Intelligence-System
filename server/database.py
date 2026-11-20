"""SQLite persistence for Student Performance Intelligence."""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Generator

import pandas as pd
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'student_performance.db'}")
# Supabase provides PostgreSQL URLs. SQLAlchemy needs the installed psycopg
# driver specified explicitly, while local development continues to use SQLite.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)  # admin | faculty
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    faculty: Mapped["Faculty | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class Faculty(Base):
    __tablename__ = "faculty"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    full_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(160), unique=True)
    user: Mapped[User] = relationship(back_populates="faculty")
    assignments: Mapped[list["FacultyClassAssignment"]] = relationship(back_populates="faculty", cascade="all, delete-orphan")


class ClassRoom(Base):
    __tablename__ = "classes"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    students: Mapped[list["Student"]] = relationship(back_populates="classroom")
    assignments: Mapped[list["FacultyClassAssignment"]] = relationship(back_populates="classroom", cascade="all, delete-orphan")


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    classroom: Mapped[ClassRoom] = relationship(back_populates="students")


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class FacultyClassAssignment(Base):
    __tablename__ = "faculty_class_assignments"
    __table_args__ = (UniqueConstraint("faculty_id", "class_id", name="uq_faculty_class"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id"))
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    faculty: Mapped[Faculty] = relationship(back_populates="assignments")
    classroom: Mapped[ClassRoom] = relationship(back_populates="assignments")


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    topic: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(160))
    assessment_date: Mapped[date] = mapped_column(Date)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    marks: Mapped[list["Mark"]] = relationship(back_populates="assessment", cascade="all, delete-orphan")


class Mark(Base):
    __tablename__ = "marks"
    __table_args__ = (UniqueConstraint("assessment_id", "student_id", name="uq_mark_per_student_assessment"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    marks_obtained: Mapped[float] = mapped_column(Float)
    total_marks: Mapped[float] = mapped_column(Float)
    time_taken: Mapped[float] = mapped_column(Float)
    questions_attempted: Mapped[int] = mapped_column(Integer)
    questions_correct: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    assessment: Mapped[Assessment] = relationship(back_populates="marks")
    student: Mapped[Student] = relationship()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def import_csv_demo_data(db: Session) -> None:
    """One-time, idempotent import retaining the bundled synthetic demo data."""
    if db.scalar(select(Mark.id).limit(1)) is not None:
        return
    path = BASE_DIR / "data" / "raw_data.csv"
    if not path.exists():
        return
    frame = pd.read_csv(path)
    # Preserve valid demo rows while refusing malformed dates from the source CSV.
    frame["attempt_date"] = pd.to_datetime(frame["attempt_date"], errors="coerce")
    frame = frame.dropna(subset=["attempt_date"])
    classes: dict[str, ClassRoom] = {}
    subjects: dict[str, Subject] = {}
    students: dict[str, Student] = {}
    for code in frame["class_id"].dropna().unique():
        room = ClassRoom(code=str(code), name=f"Class {code}")
        db.add(room); classes[str(code)] = room
    db.flush()
    for name in frame["subject"].dropna().unique():
        subject = Subject(name=str(name)); db.add(subject); subjects[str(name)] = subject
    db.flush()
    for row in frame[["student_id", "student_name", "class_id"]].drop_duplicates().itertuples(index=False):
        student = Student(student_code=str(row.student_id), full_name=str(row.student_name), classroom=classes[str(row.class_id)])
        db.add(student); students[str(row.student_id)] = student
    db.flush()
    def number(value, default=0.0):
        return default if pd.isna(value) else float(value)

    def whole(value, default=0):
        return default if pd.isna(value) else int(value)

    for row in frame.itertuples(index=False):
        assessment = Assessment(class_id=classes[str(row.class_id)].id, subject_id=subjects[str(row.subject)].id,
            topic=str(row.topic), name=str(row.assessment_name), assessment_date=row.attempt_date.date())
        db.add(assessment); db.flush()
        db.add(Mark(assessment_id=assessment.id, student_id=students[str(row.student_id)].id,
            marks_obtained=number(row.marks_obtained), total_marks=number(row.total_marks, 1.0), time_taken=number(row.time_taken),
            questions_attempted=whole(row.questions_attempted), questions_correct=whole(row.questions_correct)))
    db.commit()


def initialize_database() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        import_csv_demo_data(db)


def dataframe_from_database(db: Session) -> pd.DataFrame:
    rows = db.execute(select(Mark, Assessment, Student, ClassRoom, Subject)
        .join(Assessment, Mark.assessment_id == Assessment.id)
        .join(Student, Mark.student_id == Student.id)
        .join(ClassRoom, Student.class_id == ClassRoom.id)
        .join(Subject, Assessment.subject_id == Subject.id)).all()
    return pd.DataFrame([{
        "student_id": student.student_code, "student_name": student.full_name, "class_id": room.code,
        "subject": subject.name, "topic": assessment.topic, "assessment_name": assessment.name,
        "marks_obtained": mark.marks_obtained, "total_marks": mark.total_marks,
        "attempt_date": assessment.assessment_date.isoformat(), "time_taken": mark.time_taken,
        "questions_attempted": mark.questions_attempted, "questions_correct": mark.questions_correct,
    } for mark, assessment, student, room, subject in rows])
