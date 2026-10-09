from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import DATABASE_URL

# Handle thread checking for sqlite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_db(target_engine=None):
    eng = target_engine or engine
    Base.metadata.create_all(bind=eng)
    try:
        from sqlalchemy import inspect, text
        with eng.connect() as conn:
            inspector = inspect(conn)
            if "sessions" in inspector.get_table_names():
                cols = [c["name"] for c in inspector.get_columns("sessions")]
                if "needs_rescore" not in cols:
                    conn.execute(text("ALTER TABLE sessions ADD COLUMN needs_rescore BOOLEAN DEFAULT 0"))
                    conn.commit()
    except Exception:
        pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
