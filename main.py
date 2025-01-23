from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, Column, Integer, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import httpx
import asyncio
import re
import pytz

# FastAPI app
app = FastAPI()

# Database setup
DATABASE_URL = "sqlite:///./page_content.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# SQLAlchemy model
class PageContent(Base):
    __tablename__ = "page_content"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


# Create the database table
Base.metadata.create_all(bind=engine)

# URL to monitor
PAGE_URL = "http://192.168.18.40/"
last_content = ""  # Keeps track of the last fetched content


async def monitor_page():
    """Task to periodically fetch the page content and save new updates to the database."""
    global last_content
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(PAGE_URL, timeout=10)
                if response.status_code == 200:
                    content = response.text.strip()
                    if content != last_content:
                        last_content = content
                        save_content_to_db(content)
                        print(f"New content saved at {datetime.now(pytz.timezone('America/Sao_Paulo'))}")
                else:
                    print(f"Failed to fetch page: {response.status_code}")
        except Exception as e:
            print(f"Error monitoring page: {e}")
        await asyncio.sleep(30)  # Check every 30 seconds


def save_content_to_db(content: str):
    """Save content to the database, checking for duplicate tag_ids."""
    db = SessionLocal()
    try:
        parsed_entries = parse_content(content)
        if not parsed_entries:
            print("No valid entries found in the content, skipping save.")
            return
        
        for entry in parsed_entries:
            existing_entry = db.query(PageContent).filter(PageContent.content.like(f"%TAG ID: {entry['tag_id']}%")).first()
            if existing_entry:
                print(f"Content with TAG ID {entry['tag_id']} already exists, skipping save.")
                continue
            
            page_content = PageContent(content=str(entry), timestamp=entry["timestamp"])
            db.add(page_content)
            db.commit()
            print(f"Content with TAG ID {entry['tag_id']} saved.")
    finally:
        db.close()


def parse_content(content: str):
    """Parse the content into the desired structured format."""
    pattern = re.compile(r"TAG ID:\s*([^\s]+).+?----([\w\s]+)")
    matches = pattern.findall(content)
    if matches:
        return [
            {
                "id": idx + 1,
                "tag_id": match[0],
                "message": match[1].strip(),
                "timestamp": datetime.now(pytz.timezone("America/Sao_Paulo")),
            }
            for idx, match in enumerate(matches)
        ]
    return []


@app.on_event("startup")
async def startup_event():
    """Start the page monitoring task when the application starts."""
    asyncio.create_task(monitor_page())


@app.get("/content")
def get_saved_content():
    """Get all saved content from the database as JSON."""
    db = SessionLocal()
    try:
        contents = db.query(PageContent).all()
        if not contents:
            raise HTTPException(status_code=404, detail="No content found")
        
        # Parse the content and return the structured data
        return [
            {
                "id": content.id,
                "content": content.content,
                "timestamp": content.timestamp.isoformat()
            }
            for content in contents
        ]
    finally:
        db.close()


@app.get("/")
def root():
    """Welcome route."""
    return {"message": "Welcome to the Page Monitor API!"}
