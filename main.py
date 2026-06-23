from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request, Form, status, Cookie, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import uvicorn
import os
import sys

# Windows consoles often use cp1252; reconfigure so emoji/log output does not crash startup.
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
import shutil
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta
import json
from typing import List, Optional, Dict, Any
import asyncio
import re
import logging
import hashlib
import secrets
import uuid
from pydantic import BaseModel, EmailStr

# Document processing imports
import fitz  # PyMuPDF
import pdfplumber
from docx import Document

# AI/ML imports - simplified approach
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("Warning: sentence-transformers not available. Install with: pip install sentence-transformers")

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("Warning: faiss not available. Install with: pip install faiss-cpu")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("Warning: numpy not available. Install with: pip install numpy")





# Import AI engines
try:
    from ollama_ai_engine import OllamaAIEngine
    print("✅ OllamaAIEngine imported successfully")
    OLLAMA_AVAILABLE = True
except ImportError as e:
    print(f"❌ Failed to import OllamaAIEngine: {e}")
    print("❌ Ollama is required for this application to work. Please install Ollama from: https://ollama.ai")
    sys.exit(1)

# Security
import bcrypt
from datetime import datetime, timedelta
import threading
from contextlib import contextmanager

# Pydantic models for authentication and conversation management
class UserRegistration(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ConversationCreate(BaseModel):
    title: Optional[str] = None

class ConversationUpdate(BaseModel):
    title: str

class ChatMessage(BaseModel):
    message: str
    conversation_id: str

class User(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    created_at: datetime
    is_active: bool = True

class Conversation(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

class ChatEntry(BaseModel):
    id: str
    conversation_id: str
    question: str
    answer: str
    sources: Optional[str] = None
    created_at: datetime

# Configuration
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
Path("static").mkdir(exist_ok=True)
Path("templates").mkdir(exist_ok=True)

DATABASE_PATH = "chatbot.db"
SECRET_KEY = "your-secret-key-change-this-in-production"
SESSION_EXPIRE_HOURS = 24

# Password hashing (bcrypt directly; passlib is incompatible with bcrypt 4.1+)
def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        raise ValueError("Password must be 72 bytes or fewer")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False

# Session management
active_sessions = {}  # In production, use Redis or database
security = HTTPBearer(auto_error=False)

# Global variables for AI components
sentence_model = None
faiss_index = None
# Replace global document_chunks with conversation-specific storage
document_chunks_by_conversation = {}

class DocumentProcessor:
    def __init__(self):
        # Supported formats - only text-based documents
        self.supported_formats = ['.pdf', '.docx', '.doc', '.txt']
    
    def extract_text_from_pdf(self, file_path: str) -> dict:
        """Extract text from PDF with page-specific information using PyMuPDF"""
        try:
            doc = fitz.open(file_path)
            pages_content = []
            full_text = ""
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text()
                
                if page_text.strip():  # Only include pages with content
                    pages_content.append({
                        'page_number': page_num + 1,
                        'content': page_text.strip()
                    })
                    full_text += f"\n[Page {page_num + 1}]\n{page_text}"
            
            doc.close()
            
            return {
                'full_text': full_text,
                'pages': pages_content,
                'total_pages': len(doc)
            }
        except Exception as e:
            # Fallback to pdfplumber
            try:
                with pdfplumber.open(file_path) as pdf:
                    pages_content = []
                    full_text = ""
                    
                    for page_num, page in enumerate(pdf.pages):
                        page_text = page.extract_text() or ""
                        
                        if page_text.strip():
                            pages_content.append({
                                'page_number': page_num + 1,
                                'content': page_text.strip()
                            })
                            full_text += f"\n[Page {page_num + 1}]\n{page_text}"
                    
                    return {
                        'full_text': full_text,
                        'pages': pages_content,
                        'total_pages': len(pdf.pages)
                    }
            except Exception as e2:
                raise HTTPException(status_code=400, detail=f"Error processing PDF: {str(e2)}")
    
    def extract_text_from_docx(self, file_path: str) -> str:
        """Extract text from Word document with encoding detection"""
        try:
            doc = Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing Word document: {str(e)}")
    
    def extract_text_from_txt(self, file_path: str) -> str:
        """Extract text from plain text file with encoding detection"""
        try:
            # Try utf-8 encoding first
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    return file.read()
            except UnicodeDecodeError:
                # Fallback to utf-8 with error handling
                with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
                    return file.read()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing text file: {str(e)}")
    
    def process_document(self, file_path: str, filename: str) -> dict:
        """Process document and extract text from supported text-based formats"""
        file_ext = Path(filename).suffix.lower()
        
        # Initialize result variables
        text = ""
        pages_info = []
        total_pages = 1
        extraction_method = "Unknown"
        
        # Extract text based on file type
        if file_ext == '.pdf':
            try:
                pdf_result = self.extract_text_from_pdf(file_path)
                text = pdf_result['full_text']
                pages_info = pdf_result['pages']
                total_pages = pdf_result['total_pages']
                extraction_method = "Direct PDF"
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Error processing PDF: {str(e)}")
                    
        elif file_ext in ['.docx', '.doc']:
            text = self.extract_text_from_docx(file_path)
            # For Word docs, estimate pages based on content length
            estimated_pages = max(1, len(text) // 2000)  # Rough estimate
            pages_info = [{'page_number': i+1, 'content': text[i*2000:(i+1)*2000]} 
                         for i in range(estimated_pages)]
            total_pages = estimated_pages
            extraction_method = "Direct Word"
            
        elif file_ext == '.txt':
            text = self.extract_text_from_txt(file_path)
            # For text files, treat as single page
            pages_info = [{'page_number': 1, 'content': text}]
            total_pages = 1
            extraction_method = "Direct Text"
                
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file format: {file_ext}. Supported formats: PDF, DOCX, DOC, TXT")
        
        # Basic processing
        chunks = self.create_enhanced_chunks_with_pages(pages_info)
        
        # Prepare result
        result = {
            'filename': filename,
            'text': text,
            'chunks': chunks,
            'pages_info': pages_info,
            'total_pages': total_pages,
            'extraction_method': extraction_method,
            'processed_at': datetime.now().isoformat()
        }
            
        return result
    
    def create_enhanced_chunks_with_pages(self, pages_info: list) -> list:
        """Create enhanced chunks with accurate page number tracking"""
        chunks = []
        chunk_id = 0
        
        for page_info in pages_info:
            page_number = page_info['page_number']
            page_content = page_info['content'].strip()
            
            if not page_content:
                continue
            
            # Split page content into semantic chunks
            page_chunks = self._create_semantic_chunks_for_page(page_content)
            
            for chunk_text in page_chunks:
                if chunk_text.strip():
                    chunks.append({
                        'id': chunk_id,
                        'text': chunk_text.strip(),
                        'page_number': page_number,
                        'chunk_length': len(chunk_text),
                        'word_count': len(chunk_text.split())
                    })
                    chunk_id += 1
        
        return chunks
    
    def _create_semantic_chunks_for_page(self, text: str, max_chunk_size: int = 1000) -> list:
        """Create semantic chunks from page text, respecting sentence boundaries"""
        if not text.strip():
            return []
        
        # Split into sentences using standard English punctuation
        sentence_endings = ['. ', '! ', '? ', '.\n', '!\n', '?\n']
        
        # Split text into sentences
        sentences = []
        current_sentence = ""
        
        for char in text:
            current_sentence += char
            for ending in sentence_endings:
                if current_sentence.endswith(ending):
                    sentences.append(current_sentence.strip())
                    current_sentence = ""
                    break
        
        # Add remaining text as a sentence
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        # Group sentences into chunks
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # Check if adding this sentence would exceed max_chunk_size
            if len(current_chunk) + len(sentence) + 1 <= max_chunk_size:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
            else:
                # Save current chunk and start new one
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        
        # Add the last chunk
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def split_text_into_chunks(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Split text into overlapping chunks (basic method)"""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - overlap
        return chunks

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.init_database()
    
    @contextmanager
    def get_db_connection(self):
        """Context manager for database connections with proper locking"""
        conn = None
        try:
            with self._lock:
                conn = sqlite3.connect(
                    self.db_path, 
                    timeout=30,
                    check_same_thread=False
                )
                # Optimize connection
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=NORMAL')
                conn.execute('PRAGMA busy_timeout=30000')
                yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()
    
    def init_database(self):
        """Initialize SQLite database with user authentication and conversation management"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    last_login TIMESTAMP
                )
            ''')
            
            # Conversations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_count INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            ''')
            
            # Documents table with conversation association
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    text_content TEXT,
                    processed_text TEXT,
                    word_count INTEGER,
                    sentence_count INTEGER,
                    character_count INTEGER,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            ''')
            
            # Chat history table with conversation association
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    sources TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            ''')
            
            # User sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            ''')
            
            # User metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            ''')
            
            # Document chunks table for conversation isolation
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    source_filename TEXT NOT NULL,
                    chunk_text TEXT NOT NULL,
                    page_number INTEGER DEFAULT 1,
                    chunk_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
                )
            ''')
            
            # Add missing columns to existing tables for backward compatibility
            self._add_missing_columns(cursor)
            
            conn.commit()
    
    def _add_missing_columns(self, cursor):
        """Add missing columns to existing tables for backward compatibility"""
        try:
            # Check existing tables and add new columns if needed
            tables_to_check = [
                ('documents', [
                    ('conversation_id', 'TEXT'),
                    ('user_id', 'TEXT'),
                    ('processed_text', 'TEXT'),
                    ('word_count', 'INTEGER'),
                    ('sentence_count', 'INTEGER'),
                    ('character_count', 'INTEGER')
                ]),
                ('chat_history', [
                    ('id', 'TEXT'),
                    ('conversation_id', 'TEXT'),
                    ('user_id', 'TEXT')
                ])
            ]
            
            for table_name, columns_to_add in tables_to_check:
                cursor.execute(f"PRAGMA table_info({table_name})")
                existing_columns = [column[1] for column in cursor.fetchall()]
                
                for column_name, column_type in columns_to_add:
                    if column_name not in existing_columns:
                        try:
                            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                            print(f"Added column {column_name} to {table_name} table")
                        except sqlite3.OperationalError as e:
                            print(f"Could not add column {column_name} to {table_name}: {e}")
                            
        except Exception as e:
            print(f"Warning: Could not add missing columns: {e}")
    
    # User management methods
    def create_user(self, email: str, password: str, full_name: str = None) -> str:
        """Create a new user and return user ID"""
        user_id = str(uuid.uuid4())
        password_hash = hash_password(password)
        
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    INSERT INTO users (id, email, password_hash, full_name)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, email, password_hash, full_name))
                conn.commit()
                return user_id
            except sqlite3.IntegrityError:
                raise HTTPException(status_code=400, detail="Email already registered")
    
    def authenticate_user(self, email: str, password: str) -> Optional[dict]:
        """Authenticate user and return user data"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT id, email, password_hash, full_name, is_active FROM users WHERE email = ?', (email,))
            user_data = cursor.fetchone()
            
            if user_data and verify_password(password, user_data[2]) and user_data[4]:
                # Update last login
                cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user_data[0],))
                conn.commit()
                
                return {
                    'id': user_data[0],
                    'email': user_data[1],
                    'full_name': user_data[3],
                    'is_active': user_data[4]
                }
        
        return None
    
    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        """Get user by ID"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT id, email, full_name, created_at, is_active FROM users WHERE id = ?', (user_id,))
            user_data = cursor.fetchone()
            
            if user_data:
                return {
                    'id': user_data[0],
                    'email': user_data[1],
                    'full_name': user_data[2],
                    'created_at': user_data[3],
                    'is_active': user_data[4]
                }
        return None
    
    # Session management methods
    def create_session(self, user_id: str) -> str:
        """Create a new session for user"""
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=SESSION_EXPIRE_HOURS)
        
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO user_sessions (session_id, user_id, expires_at)
                VALUES (?, ?, ?)
            ''', (session_id, user_id, expires_at))
            conn.commit()
        
        # Store in memory for quick access
        active_sessions[session_id] = {
            'user_id': user_id,
            'expires_at': expires_at
        }
        
        return session_id
    
    def validate_session(self, session_id: str) -> Optional[str]:
        """Validate session and return user ID"""
        if not session_id:
            return None
            
        # Check memory first
        if session_id in active_sessions:
            session_data = active_sessions[session_id]
            if datetime.now() < session_data['expires_at']:
                return session_data['user_id']
            else:
                # Session expired, remove from memory
                del active_sessions[session_id]
        
        # Check database
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_id, expires_at FROM user_sessions 
                WHERE session_id = ? AND is_active = 1
            ''', (session_id,))
            session_data = cursor.fetchone()
            
            if session_data:
                expires_at = datetime.fromisoformat(session_data[1])
                if datetime.now() < expires_at:
                    # Update memory cache
                    active_sessions[session_id] = {
                        'user_id': session_data[0],
                        'expires_at': expires_at
                    }
                    return session_data[0]
                else:
                    # Deactivate expired session
                    cursor.execute('UPDATE user_sessions SET is_active = 0 WHERE session_id = ?', (session_id,))
                    conn.commit()
        
        return None
    
    def invalidate_session(self, session_id: str):
        """Invalidate a session"""
        if session_id in active_sessions:
            del active_sessions[session_id]
        
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE user_sessions SET is_active = 0 WHERE session_id = ?', (session_id,))
            conn.commit()
    
    # Conversation management methods
    def create_conversation(self, user_id: str, title: str = None) -> str:
        """Create a new conversation for user"""
        conversation_id = str(uuid.uuid4())
        if not title:
            title = f"Conversation {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO conversations (id, user_id, title)
                VALUES (?, ?, ?)
            ''', (conversation_id, user_id, title))
            conn.commit()
        
        return conversation_id
    
    def get_user_conversations(self, user_id: str) -> List[dict]:
        """Get all conversations for a user"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, created_at, updated_at, message_count
                FROM conversations 
                WHERE user_id = ? 
                ORDER BY updated_at DESC
            ''', (user_id,))
            
            conversations = []
            for row in cursor.fetchall():
                conversations.append({
                    'id': row[0],
                    'title': row[1],
                    'created_at': row[2],
                    'updated_at': row[3],
                    'message_count': row[4]
                })
        
        return conversations
    
    def get_conversation(self, conversation_id: str, user_id: str) -> Optional[dict]:
        """Get a specific conversation for a user"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, created_at, updated_at, message_count
                FROM conversations 
                WHERE id = ? AND user_id = ?
            ''', (conversation_id, user_id))
            
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'title': row[1],
                    'created_at': row[2],
                    'updated_at': row[3],
                    'message_count': row[4]
                }
        return None
    
    def update_conversation(self, conversation_id: str, user_id: str, title: str):
        """Update conversation title"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE conversations 
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            ''', (title, conversation_id, user_id))
            conn.commit()
    
    def delete_conversation(self, conversation_id: str, user_id: str):
        """Delete a conversation and all associated data"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            # Delete associated documents, chat history, etc. (CASCADE will handle this)
            cursor.execute('DELETE FROM conversations WHERE id = ? AND user_id = ?', (conversation_id, user_id))
            conn.commit()
    
    # Document management methods (updated for conversations)
    def add_document(self, conversation_id: str, user_id: str, filename: str, file_path: str, document_data: dict):
        """Add document to database with conversation association"""
        import uuid
        import os
        from datetime import datetime
        
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Generate unique document ID
            doc_id = str(uuid.uuid4())
            
            # Extract document information
            text_content = document_data.get('text', '')
            processed_text = document_data.get('processed_text', text_content)
            
            # Calculate file stats
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            file_type = os.path.splitext(filename)[1].lower()
            word_count = len(text_content.split()) if text_content else 0
            character_count = len(text_content) if text_content else 0
            sentence_count = text_content.count('.') + text_content.count('!') + text_content.count('?') if text_content else 0
            
            # Use filename as original_filename, but make it unique if needed
            original_filename = filename
            
            # Check if filename already exists for this user
            cursor.execute('''
                SELECT COUNT(*) FROM documents 
                WHERE user_id = ? AND original_filename = ?
            ''', (user_id, original_filename))
            
            count = cursor.fetchone()[0]
            if count > 0:
                # Make filename unique by adding timestamp
                name, ext = os.path.splitext(original_filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                original_filename = f"{name}_{timestamp}{ext}"
            
            try:
                cursor.execute('''
                    INSERT INTO documents (
                        id, conversation_id, user_id, filename, original_filename, file_path, 
                        file_size, file_type, text_content, processed_text, word_count, 
                        sentence_count, character_count, processing_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    doc_id, conversation_id, user_id, filename, original_filename, file_path,
                    file_size, file_type, text_content, processed_text, word_count,
                    sentence_count, character_count, 'completed', datetime.now().isoformat()
                ))
                
                conn.commit()
                return doc_id
                
            except Exception as e:
                # If still fails, try with a UUID suffix
                if "UNIQUE constraint failed" in str(e):
                    name, ext = os.path.splitext(filename)
                    unique_suffix = str(uuid.uuid4())[:8]
                    original_filename = f"{name}_{unique_suffix}{ext}"
                    
                    cursor.execute('''
                        INSERT INTO documents (
                            id, conversation_id, user_id, filename, original_filename, file_path, 
                            file_size, file_type, text_content, processed_text, word_count, 
                            sentence_count, character_count, processing_status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        doc_id, conversation_id, user_id, filename, original_filename, file_path,
                        file_size, file_type, text_content, processed_text, word_count,
                        sentence_count, character_count, 'completed', datetime.now().isoformat()
                    ))
                    
                    conn.commit()
                else:
                    raise e
            
            return doc_id
    
    def get_conversation_documents(self, conversation_id: str, user_id: str):
        """Get all documents for a specific conversation"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM documents 
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY processed_at DESC
            ''', (conversation_id, user_id))
            documents = cursor.fetchall()
        return documents
    
    def get_user_documents(self, user_id: str):
        """Get all documents for a user across all conversations"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT d.*, c.title as conversation_title 
                FROM documents d
                JOIN conversations c ON d.conversation_id = c.id
                WHERE d.user_id = ?
                ORDER BY d.processed_at DESC
            ''', (user_id,))
            documents = cursor.fetchall()
        return documents
    
    # Chat history methods (updated for conversations)
    def add_chat_entry(self, conversation_id: str, user_id: str, question: str, answer: str, 
                      sources: str = ""):
        """Add chat entry to conversation history"""
        chat_id = str(uuid.uuid4())
        
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            print(f"DEBUG: add_chat_entry - chat_id: {chat_id}, conversation_id: {conversation_id}, user_id: {user_id}, question: {question[:50]}..., answer: {answer[:50]}..., sources: {sources}")
            cursor.execute('''
                INSERT INTO chat_history (
                    id, conversation_id, user_id, question, answer, sources
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (chat_id, conversation_id, user_id, question, answer, sources))
            
            # Update conversation message count and timestamp
            cursor.execute('''
                UPDATE conversations 
                SET message_count = message_count + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            ''', (conversation_id, user_id))
            
            conn.commit()
        
        return chat_id
    
    def get_conversation_history(self, conversation_id: str, user_id: str, limit: int = 50):
        """Get chat history for a specific conversation"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, question, answer, sources, created_at
                FROM chat_history 
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY created_at ASC
                LIMIT ?
            ''', (conversation_id, user_id, limit))
            
            history = []
            for row in cursor.fetchall():
                history.append({
                    'id': row[0],
                    'question': row[1],
                    'answer': row[2],
                    'sources': row[3],
                    'created_at': row[4]
                })
        
        return history
    
    def search_user_conversations(self, user_id: str, query: str, limit: int = 20):
        """Search within user's conversations and chat history"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT DISTINCT c.id, c.title, c.updated_at, ch.question, ch.answer
                FROM conversations c
                LEFT JOIN chat_history ch ON c.id = ch.conversation_id
                WHERE c.user_id = ? AND (
                    c.title LIKE ? OR 
                    ch.question LIKE ? OR 
                    ch.answer LIKE ?
                )
                ORDER BY c.updated_at DESC
                LIMIT ?
            ''', (user_id, f'%{query}%', f'%{query}%', f'%{query}%', limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'conversation_id': row[0],
                    'title': row[1],
                    'updated_at': row[2],
                    'question': row[3],
                    'answer': row[4]
                })
        
        return results
    
    # User metrics methods
    def record_user_metric(self, user_id: str, metric_type: str, metric_value: float):
        """Record a user metric"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_metrics (user_id, metric_type, metric_value)
                VALUES (?, ?, ?)
            ''', (user_id, metric_type, metric_value))
            conn.commit()
    
    # Document chunks management methods
    def store_document_chunks(self, conversation_id: str, user_id: str, document_id: str, 
                            source_filename: str, enhanced_chunks: list):
        """Store document chunks in the database for conversation isolation"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Clear existing chunks for this document in this conversation
            cursor.execute('''
                DELETE FROM document_chunks 
                WHERE conversation_id = ? AND document_id = ?
            ''', (conversation_id, document_id))
            
            # Insert new chunks
            for chunk in enhanced_chunks:
                chunk_text = chunk.get('text', '')
                page_number = chunk.get('page_number', 1)
                chunk_id = chunk.get('chunk_id', 0)
                
                if chunk_text.strip():  # Only store non-empty chunks
                    cursor.execute('''
                        INSERT INTO document_chunks 
                        (conversation_id, user_id, document_id, source_filename, 
                         chunk_text, page_number, chunk_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (conversation_id, user_id, document_id, source_filename, 
                          chunk_text, page_number, chunk_id))
            
            conn.commit()
    
    def get_conversation_chunks(self, conversation_id: str, user_id: str) -> list:
        """Get all document chunks for a specific conversation"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT source_filename, chunk_text, page_number, chunk_id
                FROM document_chunks 
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY source_filename, chunk_id
            ''', (conversation_id, user_id))
            
            chunks = cursor.fetchall()
            
            # Group chunks by filename
            documents_data = {}
            for filename, chunk_text, page_number, chunk_id in chunks:
                if filename not in documents_data:
                    documents_data[filename] = {
                        'filename': filename,
                        'chunks': [],
                        'enhanced_chunks': []
                    }
                
                documents_data[filename]['chunks'].append(chunk_text)
                documents_data[filename]['enhanced_chunks'].append({
                    'text': chunk_text,
                    'page_number': page_number,
                    'chunk_id': chunk_id
                })
            
            return list(documents_data.values())
    
    def clear_conversation_chunks(self, conversation_id: str, user_id: str):
        """Clear all document chunks for a specific conversation"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM document_chunks 
                WHERE conversation_id = ? AND user_id = ?
            ''', (conversation_id, user_id))
            conn.commit()
    
    def clear_user_chunks(self, user_id: str):
        """Clear all document chunks for a specific user"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM document_chunks 
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
    
    def get_user_metrics(self, user_id: str, metric_type: str = None, days: int = 30):
        """Get user metrics for the specified period"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            if metric_type:
                cursor.execute('''
                    SELECT metric_type, metric_value, recorded_at
                    FROM user_metrics 
                    WHERE user_id = ? AND metric_type = ? 
                    AND recorded_at >= datetime('now', '-{} days')
                    ORDER BY recorded_at DESC
                '''.format(days), (user_id, metric_type))
            else:
                cursor.execute('''
                    SELECT metric_type, metric_value, recorded_at
                    FROM user_metrics 
                    WHERE user_id = ? 
                    AND recorded_at >= datetime('now', '-{} days')
                    ORDER BY recorded_at DESC
                '''.format(days), (user_id,))
            
            metrics = []
            for row in cursor.fetchall():
                metrics.append({
                    'metric_type': row[0],
                    'metric_value': row[1],
                    'recorded_at': row[2]
                })
        
        return metrics
    
    # Legacy methods for backward compatibility
    def get_all_documents(self):
        """Get all documents (legacy method for backward compatibility)"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents")
            documents = cursor.fetchall()
        return documents
    
    def clear_all_documents(self):
        """Clear all documents and chat history from the database (admin only)"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM documents")
            cursor.execute("DELETE FROM chat_history")
            cursor.execute("DELETE FROM conversations")
            conn.commit()
        print("All documents and chat history cleared from database")
    
    def clear_user_documents(self, user_id: str):
        """Clear all documents for a specific user"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM documents WHERE user_id = ?", (user_id,))
            conn.commit()
        print(f"All documents cleared for user {user_id}")

    def clear_user_chat_history(self, user_id: str):
        """Clear chat history for a specific user"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
            conn.commit()
        print(f"Chat history cleared for user {user_id}")
    
    def get_conversation_chat_history(self, conversation_id: str, user_id: str):
        """Get chat history for a specific conversation"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, conversation_id, question, answer, sources, created_at 
                FROM chat_history 
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY created_at ASC
            """, (conversation_id, user_id))
            history = cursor.fetchall()
        return history
    
    def get_user_chat_history(self, user_id: str, limit: int = 50):
        """Get all chat history for a user"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, conversation_id, question, answer, sources, created_at 
                FROM chat_history 
                WHERE user_id = ?
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            history = cursor.fetchall()
        return history

# Initialize database manager
db_manager = DatabaseManager(DATABASE_PATH)

# Authentication helper functions
async def get_current_user(request: Request) -> Optional[dict]:
    """Get current user from session"""
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    
    user_id = db_manager.validate_session(session_id)
    if not user_id:
        return None
    
    return db_manager.get_user_by_id(user_id)

async def require_auth(request: Request) -> dict:
    """Require authentication and return user"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

def create_response_with_session(content: dict, session_id: str = None):
    """Create response with session cookie"""
    response = JSONResponse(content=content)
    if session_id:
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=SESSION_EXPIRE_HOURS * 3600
        )
    return response

# Initialize components
doc_processor = DocumentProcessor()
db_manager = DatabaseManager(DATABASE_PATH)

# Use Ollama AI engine for reliable local model execution
print("🚀 Initializing AI Engine...")

# Check if Ollama is available first
try:
    import requests
    response = requests.get("http://localhost:11434/api/tags", timeout=2)
    if response.status_code != 200:
        print("❌ Ollama is not running. Please start Ollama and restart the application.")
        print("💡 Install Ollama from: https://ollama.ai")
        sys.exit(1)
except Exception as e:
    print(f"❌ Cannot connect to Ollama: {e}")
    print("❌ Ollama is required for this application to work. Please install and start Ollama.")
    print("💡 Install Ollama from: https://ollama.ai")
    sys.exit(1)

# Initialize Ollama AI Engine
try:
    from ollama_ai_engine import OllamaAIEngine
    print("📋 Ollama detected - using Ollama AI Engine for local model execution")
    ai_engine = OllamaAIEngine()
    print("✅ Ollama AI Engine loaded successfully!")
except Exception as e:
    print(f"❌ Error loading Ollama AI Engine: {e}")
    print("❌ Failed to initialize AI engine. Please check your Ollama installation.")
    sys.exit(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    Path("static").mkdir(exist_ok=True)
    
    # Load existing documents and rebuild index
    documents = db_manager.get_all_documents()
    if documents:
        documents_data = []
        for doc in documents:
            chunks = doc_processor.split_text_into_chunks(doc[3])  # text_content is at index 3
            documents_data.append({
                'filename': doc[1],
                'chunks': chunks
            })
        ai_engine.build_vector_index(documents_data)
    
    yield
    # Shutdown (if needed)

# Create FastAPI app with lifespan
app = FastAPI(title="Lote Chemical AI Document Assistant", lifespan=lifespan)

# Add exception handling middleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with detailed messages"""
    error_details = []
    for error in exc.errors():
        field = " -> ".join(str(x) for x in error["loc"])
        message = error["msg"]
        error_details.append(f"{field}: {message}")
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": error_details,
            "message": "Please check your input data"
        }
    )

@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors"""
    error_details = []
    for error in exc.errors():
        field = " -> ".join(str(x) for x in error["loc"])
        message = error["msg"]
        error_details.append(f"{field}: {message}")
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Data validation error",
            "errors": error_details,
            "message": "Please check your input data"
        }
    )

# Templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Authentication endpoints
@app.post("/api/register")
async def register_user(request: Request):
    """Register a new user"""
    try:
        # Get raw JSON data
        try:
            data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid JSON data: {str(e)}")
        
        # Extract and validate fields
        email = data.get('email', '').strip() if data.get('email') else ''
        password = data.get('password', '')
        full_name = data.get('full_name', '').strip() if data.get('full_name') else ''
        
        # Validate input data
        if not email:
            raise HTTPException(status_code=422, detail="Email is required")
        
        if not password or len(password) < 6:
            raise HTTPException(status_code=422, detail="Password must be at least 6 characters long")
        
        if not full_name:
            raise HTTPException(status_code=422, detail="Full name is required")
        
        # Validate email format
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise HTTPException(status_code=422, detail="Invalid email format")
        
        user_id = db_manager.create_user(
            email=email.lower(),
            password=password,
            full_name=full_name
        )
        
        # Create session for new user
        session_id = db_manager.create_session(user_id)
        
        # Record registration metric
        db_manager.record_user_metric(user_id, "registration", 1.0)
        
        return create_response_with_session({
            "message": "User registered successfully",
            "user_id": user_id
        }, session_id)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Registration error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/api/login")
async def login_user(request: Request):
    """Login user"""
    try:
        # Get raw JSON data
        try:
            data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid JSON data: {str(e)}")
        
        # Extract and validate fields
        email = data.get('email', '').strip() if data.get('email') else ''
        password = data.get('password', '')
        
        # Validate input data
        if not email:
            raise HTTPException(status_code=422, detail="Email is required")
        
        if not password:
            raise HTTPException(status_code=422, detail="Password is required")
        
        user = db_manager.authenticate_user(email.lower(), password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Create new session
        session_id = db_manager.create_session(user['id'])
        
        # Record login metric
        db_manager.record_user_metric(user['id'], "login", 1.0)
        
        return create_response_with_session({
            "message": "Login successful",
            "user": {
                "id": user['id'],
                "email": user['email'],
                "full_name": user['full_name']
            }
        }, session_id)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.post("/api/logout")
async def logout_user(request: Request):
    """Logout user"""
    session_id = request.cookies.get("session_id")
    if session_id:
        db_manager.invalidate_session(session_id)
    
    response = JSONResponse({"message": "Logout successful"})
    response.delete_cookie("session_id")
    return response

@app.get("/api/user/profile")
async def get_user_profile(request: Request):
    """Get current user profile"""
    user = await require_auth(request)
    return {"user": user}

@app.get("/api/user/conversations")
async def get_user_conversations(request: Request):
    """Get user's conversations"""
    user = await require_auth(request)
    conversations = db_manager.get_user_conversations(user['id'])
    return {"conversations": conversations}

@app.post("/api/conversations")
async def create_conversation(request: Request, conversation_data: ConversationCreate):
    """Create a new conversation"""
    user = await require_auth(request)
    conversation_id = db_manager.create_conversation(user['id'], conversation_data.title)
    
    # Record conversation creation metric
    db_manager.record_user_metric(user['id'], "conversation_created", 1.0)
    
    return {"conversation_id": conversation_id, "message": "Conversation created successfully"}

@app.get("/api/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str):
    """Get conversation details and history"""
    user = await require_auth(request)
    
    conversation = db_manager.get_conversation(conversation_id, user['id'])
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    history = db_manager.get_conversation_history(conversation_id, user['id'])
    documents = db_manager.get_conversation_documents(conversation_id, user['id'])
    
    return {
        "conversation": conversation,
        "history": history,
        "documents": [{"id": doc[0], "filename": doc[3], "processed_at": doc[-1]} for doc in documents]
    }

@app.put("/api/conversations/{conversation_id}")
async def update_conversation(request: Request, conversation_id: str, conversation_data: ConversationUpdate):
    """Update conversation title"""
    user = await require_auth(request)
    
    conversation = db_manager.get_conversation(conversation_id, user['id'])
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    db_manager.update_conversation(conversation_id, user['id'], conversation_data.title)
    return {"message": "Conversation updated successfully"}

@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(request: Request, conversation_id: str):
    """Delete a conversation"""
    user = await require_auth(request)
    
    conversation = db_manager.get_conversation(conversation_id, user['id'])
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    db_manager.delete_conversation(conversation_id, user['id'])
    
    # Record conversation deletion metric
    db_manager.record_user_metric(user['id'], "conversation_deleted", 1.0)
    
    return {"message": "Conversation deleted successfully"}

@app.get("/api/user/search")
async def search_user_data(request: Request, q: str = Query(..., description="Search query")):
    """Search within user's conversations and documents"""
    user = await require_auth(request)
    
    # Search conversations
    conversation_results = db_manager.search_user_conversations(user['id'], q)
    
    # Record search metric
    db_manager.record_user_metric(user['id'], "search_query", 1.0)
    
    return {
        "query": q,
        "results": {
            "conversations": conversation_results
        }
    }

@app.get("/api/user/metrics")
async def get_user_metrics(request: Request, days: int = Query(30, description="Number of days")):
    """Get user metrics and statistics"""
    user = await require_auth(request)
    
    metrics = db_manager.get_user_metrics(user['id'], days=days)
    conversations = db_manager.get_user_conversations(user['id'])
    documents = db_manager.get_user_documents(user['id'])
    
    # Calculate summary statistics
    total_conversations = len(conversations)
    total_documents = len(documents)
    total_messages = sum(conv['message_count'] for conv in conversations)
    
    # Group metrics by type
    metrics_by_type = {}
    for metric in metrics:
        metric_type = metric['metric_type']
        if metric_type not in metrics_by_type:
            metrics_by_type[metric_type] = []
        metrics_by_type[metric_type].append(metric)
    
    return {
        "summary": {
            "total_conversations": total_conversations,
            "total_documents": total_documents,
            "total_messages": total_messages,
            "recent_activity_days": days
        },
        "metrics": metrics_by_type
    }

# Main application endpoints (updated for authentication)
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with authentication check"""
    user = await get_current_user(request)
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            "user": user,
            "authenticated": user is not None,
        },
    )

@app.post("/upload")
async def upload_document(request: Request, files: List[UploadFile] = File(...), conversation_id: str = Form(None)):
    """Upload and process multiple documents with user authentication"""
    user = await require_auth(request)
    
    # If no conversation_id provided, create a new conversation
    if not conversation_id:
        conversation_id = db_manager.create_conversation(user['id'], f"Documents uploaded {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    else:
        # Verify user owns the conversation
        conversation = db_manager.get_conversation(conversation_id, user['id'])
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    
    import time
    start_time = time.time()
    uploaded_files = []
    
    try:
        for file in files:
            if not file.filename:
                continue
                
            # Check file extension
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in doc_processor.supported_formats:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Unsupported file format: {file_ext}. Supported formats: {', '.join(doc_processor.supported_formats)}"
                )
            
            # Save uploaded file with user-specific path
            user_upload_dir = UPLOAD_DIR / user['id']
            user_upload_dir.mkdir(exist_ok=True)
            
            file_path = user_upload_dir / file.filename
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            try:
                # Process document with enhanced chunking
                doc_data = doc_processor.process_document(str(file_path), file.filename)
                
                # Enhanced document processing for better RAG
                enhanced_chunks = []
                for chunk_data in doc_data['chunks']:
                    if isinstance(chunk_data, dict):
                        enhanced_chunks.append({
                            'text': chunk_data['text'],
                            'page_number': chunk_data.get('page_number', 1),
                            'chunk_id': chunk_data.get('id', 0)
                        })
                    else:
                        # Handle string chunks
                        enhanced_chunks.append({
                            'text': str(chunk_data),
                            'page_number': 1,
                            'chunk_id': 0
                        })
                
                doc_data['enhanced_chunks'] = enhanced_chunks
                
                # Save to database with conversation and user association
                document_id = db_manager.add_document(conversation_id, user['id'], file.filename, str(file_path), doc_data)
                
                # Prepare upload response
                file_info = {
                    "filename": file.filename,
                    "chunks_count": len(doc_data['chunks']),
                    "conversation_id": conversation_id
                }
                
                uploaded_files.append(file_info)
                
                # Store chunks in database for conversation isolation
                if doc_data.get('enhanced_chunks'):
                    db_manager.store_document_chunks(
                        conversation_id=conversation_id,
                        user_id=user['id'],
                        document_id=document_id,
                        source_filename=file.filename,
                        enhanced_chunks=doc_data['enhanced_chunks']
                    )
                
            except Exception as e:
                # Clean up file if processing failed
                if file_path.exists():
                    file_path.unlink()
                raise HTTPException(status_code=500, detail=f"Error processing {file.filename}: {str(e)}")
        
        # Store chunks for this conversation
        conversation_documents = db_manager.get_conversation_documents(conversation_id, user['id'])
        documents_data = []
        for doc in conversation_documents:
            # doc structure: (id, conversation_id, user_id, filename, file_path, text_content, ...)
            # Get text content from the correct column (8 = text_content, 9 = processed_text)
            processed_text = doc[9] if len(doc) > 9 and doc[9] else None
            text_content = doc[8] if len(doc) > 8 and doc[8] else None
            content_to_use = processed_text or text_content
            
            if content_to_use:
                # Try to parse enhanced chunks from processed_text if it's JSON
                enhanced_chunks = []
                if processed_text:
                    try:
                        import json
                        doc_data = json.loads(processed_text)
                        if 'enhanced_chunks' in doc_data:
                            enhanced_chunks = doc_data['enhanced_chunks']
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                # If no enhanced chunks, create basic chunks
                if not enhanced_chunks:
                    basic_chunks = doc_processor.split_text_into_chunks(content_to_use)
                    enhanced_chunks = [{
                        'text': chunk,
                        'page_number': 1,
                        'chunk_id': i
                    } for i, chunk in enumerate(basic_chunks)]
                
                # Convert enhanced chunks to simple chunks for AI engine
                simple_chunks = [chunk['text'] for chunk in enhanced_chunks if chunk.get('text', '').strip()]
                
                documents_data.append({
                    'filename': doc[3],  # filename
                    'chunks': simple_chunks,
                    'enhanced_chunks': enhanced_chunks
                })
        
        # Store conversation-specific chunks
        document_chunks_by_conversation[conversation_id] = documents_data
        
        # Build vector index with conversation-specific documents
        ai_engine.build_vector_index(documents_data)
        
        # Calculate processing time and record metrics
        processing_time = time.time() - start_time
        
        # Record upload metrics
        db_manager.record_user_metric(user['id'], "document_upload", len(uploaded_files))
        db_manager.record_user_metric(user['id'], "processing_time", processing_time)
        
        return JSONResponse({
            "message": f"Successfully uploaded {len(uploaded_files)} document(s)",
            "files": uploaded_files,
            "conversation_id": conversation_id,
            "processing_time": round(processing_time, 3)
        })
        
    except Exception as e:
        processing_time = time.time() - start_time
        
        # Record error metric
        db_manager.record_user_metric(user['id'], "upload_error", 1.0)
        
        raise e

@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint for monitoring"""
    try:
        from utils.monitoring import health_checker
        health_status = await health_checker.check_system_health()
        return JSONResponse(health_status)
    except ImportError:
        # Fallback to basic health check if monitoring utils not available
        try:
            documents = db_manager.get_all_documents()
            db_status = True
        except Exception:
            db_status = False
        
        # Check disk space
        import shutil
        total, used, free = shutil.disk_usage(UPLOAD_DIR)
        disk_usage = {
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "usage_percent": round((used / total) * 100, 2)
        }
        
        return JSONResponse({
            "status": "healthy" if db_status else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "components": {
                "database": "healthy" if db_status else "unhealthy"
            },
            "metrics": {
                "documents_count": len(documents) if db_status else 0,
                "disk_usage": disk_usage
            }
        })

@app.get("/metrics")
async def get_metrics():
    """Get application performance metrics"""
    try:
        from utils.monitoring import performance_monitor
        metrics = performance_monitor.get_metrics()
        return JSONResponse({
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics
        })
    except ImportError:
        return JSONResponse({
            "error": "Monitoring utilities not available",
            "timestamp": datetime.utcnow().isoformat()
        })

@app.post("/chat")
async def chat(
    request: Request,
    question: str = Form(...),
    conversation_id: Optional[str] = Form(None)
):
    """Enhanced chat endpoint with user authentication and conversation management"""
    import time
    start_time = time.time()
    
    try:
        # Get authenticated user
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Input validation
        if len(question.strip()) == 0:
            return JSONResponse({
                "answer": "Please ask me a question! I'm here to help with your documents. 😊",
                "confidence": 0.0,
                "sources": [],
                "model": "Enhanced AI Assistant"
            })
        
        if len(question) > 1000:
            return JSONResponse({
                "answer": "Your question is too long. Please keep it under 1000 characters for better processing.",
                "confidence": 0.0,
                "sources": [],
                "model": "Enhanced AI Assistant"
            })
        
        # Get or create conversation
        if conversation_id:
            conversation = db_manager.get_conversation(conversation_id, user['id'])
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
        else:
            # Create new conversation
            conversation_id = db_manager.create_conversation(
                user['id'], 
                f"Chat - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            conversation = db_manager.get_conversation(conversation_id, user['id'])
        
        # Get conversation-specific chunks from database first, then memory, then rebuild
        documents_data = db_manager.get_conversation_chunks(conversation_id, user['id'])
        
        # If no chunks in database, try memory
        if not documents_data:
            documents_data = document_chunks_by_conversation.get(conversation_id, [])
        
        # If no chunks in memory either, rebuild from documents table
        if not documents_data:
            conversation_documents = db_manager.get_conversation_documents(conversation_id, user['id'])
            print(f"Debug: Found {len(conversation_documents)} documents for conversation {conversation_id}")
            
            documents_data = []
            for i, doc in enumerate(conversation_documents):
                print(f"Debug: Document {i}: length={len(doc)}")
                
                # Try to get processed_text first (column 9), then text_content (column 8)
                processed_text = doc[9] if len(doc) > 9 and doc[9] else None
                text_content = doc[8] if len(doc) > 8 and doc[8] else None
                
                # Use processed_text if available, otherwise use text_content
                content_to_use = processed_text or text_content
                
                if content_to_use:
                    print(f"Debug: Content found, length: {len(content_to_use)}")
                    
                    # Try to parse enhanced chunks from processed_text if it's JSON
                    enhanced_chunks = []
                    if processed_text:
                        try:
                            import json
                            doc_data = json.loads(processed_text)
                            if 'enhanced_chunks' in doc_data:
                                enhanced_chunks = doc_data['enhanced_chunks']
                                print(f"Debug: Found {len(enhanced_chunks)} enhanced chunks")
                        except (json.JSONDecodeError, TypeError):
                            print("Debug: Could not parse enhanced chunks, using basic chunking")
                    
                    # If no enhanced chunks, create basic chunks
                    if not enhanced_chunks:
                        basic_chunks = doc_processor.split_text_into_chunks(content_to_use)
                        enhanced_chunks = [{
                            'text': chunk,
                            'page_number': 1,
                            'chunk_id': i
                        } for i, chunk in enumerate(basic_chunks)]
                        print(f"Debug: Created {len(enhanced_chunks)} basic chunks")
                    
                    # Convert enhanced chunks to simple chunks for AI engine
                    simple_chunks = [chunk['text'] for chunk in enhanced_chunks if chunk.get('text', '').strip()]
                    
                    documents_data.append({
                        'filename': doc[3],  # filename
                        'chunks': simple_chunks,
                        'enhanced_chunks': enhanced_chunks
                    })
                else:
                    print(f"Debug: No content found for document {i}")
            
            # Store in conversation-specific memory
            document_chunks_by_conversation[conversation_id] = documents_data
            print(f"Debug: Total documents_data: {len(documents_data)}")
        
        # Update AI engine with conversation-specific documents
        if documents_data:
            ai_engine.build_vector_index(documents_data)
        
        # Convert documents_data to the format expected by AI engine
        conversation_documents_for_ai = []
        for doc_data in documents_data:
            for chunk in doc_data['chunks']:
                conversation_documents_for_ai.append({
                    'content': chunk,
                    'filename': doc_data['filename']
                })
        
        # Get answer from AI engine with conversation-specific documents
        result = ai_engine.answer_question(question, conversation_documents_for_ai)
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Log to database with user and conversation context
        sources = result.get("sources", [])
        if sources and isinstance(sources[0], dict):
            # Handle dictionary sources
            sources_str = ",".join([s.get('filename', 'Unknown') for s in sources])
        else:
            # Handle string sources (fallback)
            sources_str = ",".join(sources) if sources else ""
        db_manager.add_chat_entry(
            conversation_id, user['id'], question, result["answer"], sources_str
        )
        
        # Record user metrics
        db_manager.record_user_metric(user['id'], "chat_query", 1.0)
        db_manager.record_user_metric(user['id'], "response_time", processing_time)
        
        # Prepare response with enhanced information
        response_data = {
            "answer": result["answer"],
            "confidence": result["confidence"],
            "sources": result.get("sources", []),
            "model": "Enhanced AI Assistant",
            "processing_time": round(processing_time, 3),
            "conversation_id": conversation_id,
            "conversation_documents_count": len(conversation_documents_for_ai)
        }
        
        # Add enhanced search and analysis information
        if "cross_document_analysis" in result:
            response_data["cross_document_analysis"] = result["cross_document_analysis"]
        
        if "total_documents_searched" in result:
            response_data["total_documents_searched"] = result["total_documents_searched"]
        
        if "relevant_documents_found" in result:
            response_data["relevant_documents_found"] = result["relevant_documents_found"]
        
        # Add document references with page numbers
        if "document_references" in result:
            response_data["document_references"] = result["document_references"]
        
        return JSONResponse(response_data)
        
    except Exception as e:
        processing_time = time.time() - start_time
        
        # Record error metric if user is authenticated
        try:
            user = await get_current_user(request)
            if user:
                db_manager.record_user_metric(user['id'], "chat_error", 1.0)
        except:
            pass
        
        print(f"Chat error: {e}")
        return JSONResponse({
            "answer": "I apologize, but I encountered an error while processing your question. Please try again! 😊",
            "confidence": 0.0,
            "sources": [],
            "error": str(e),
            "processing_time": round(processing_time, 3)
        })

@app.post("/clear-files")
async def clear_files(request: Request):
    """Clear all uploaded files and database entries for the authenticated user"""
    try:
        # Get authenticated user
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Get user's documents before clearing them
        user_documents = db_manager.get_user_documents(user['id'])
        
        # Clear user's uploaded files from filesystem
        for doc in user_documents:
            file_path = doc[4] if len(doc) > 4 else None  # file_path column
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Warning: Could not remove file {file_path}: {e}")
        
        # Clear user's documents from database
        db_manager.clear_user_documents(user['id'])
        
        # Clear user's document chunks from database
        db_manager.clear_user_chunks(user['id'])
        
        # Clear conversation-specific chunks from memory for this user
        conversations_to_clear = []
        for conv_id in list(document_chunks_by_conversation.keys()):
            # Get conversation to check if it belongs to this user
            try:
                conversation = db_manager.get_conversation(conv_id, user['id'])
                if conversation:
                    conversations_to_clear.append(conv_id)
            except:
                pass
        
        for conv_id in conversations_to_clear:
            if conv_id in document_chunks_by_conversation:
                del document_chunks_by_conversation[conv_id]
        
        # Reset AI engine (rebuild with empty documents since all are cleared)
        ai_engine.build_vector_index([])
        
        return JSONResponse({"message": "All your files cleared successfully"})
    except Exception as e:
        print(f"Error in clear_files: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/documents")
async def get_documents(request: Request):
    """Get list of uploaded documents for the authenticated user"""
    try:
        # Get authenticated user
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        documents = db_manager.get_user_documents(user['id'])
        return JSONResponse([{
            "id": doc[0],
            "conversation_id": doc[1],
            "filename": doc[3],
            "processed_at": doc[6] if len(doc) > 6 else None
        } for doc in documents])
    except Exception as e:
        return JSONResponse({"error": str(e)})

@app.get("/chat-history")
async def get_chat_history(request: Request, conversation_id: Optional[str] = None):
    """Get chat history for the authenticated user, optionally filtered by conversation"""
    try:
        # Get authenticated user
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if conversation_id:
            # Get chat history for specific conversation
            history = db_manager.get_conversation_chat_history(conversation_id, user['id'])
        else:
            # Get all chat history for user
            history = db_manager.get_user_chat_history(user['id'])
        
        return JSONResponse([{
            "id": entry[0],
            "conversation_id": entry[1] if len(entry) > 1 else None,
            "question": entry[2] if len(entry) > 2 else entry[1],
            "answer": entry[3] if len(entry) > 3 else entry[2],
            "sources": json.loads(entry[4]) if len(entry) > 4 and entry[4] else [],
            "created_at": entry[5] if len(entry) > 5 else entry[4]
        } for entry in history])
    except Exception as e:
        return JSONResponse({"error": str(e)})

def create_default_admin_user():
    """Create a default admin user if no users exist"""
    try:
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        
        # Check if any users exist
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        if user_count == 0:
            # Create default admin user
            admin_email = "admin@lotechemical.com"
            admin_password = "admin123"
            admin_name = "Administrator"
            
            user_id = db_manager.create_user(admin_email, admin_password, admin_name)
            print(f"✅ Default admin user created:")
            print(f"   Email: {admin_email}")
            print(f"   Password: {admin_password}")
            print(f"   Please change the password after first login!")
        else:
            print(f"✅ Database has {user_count} existing users")
        
        conn.close()
    except Exception as e:
        print(f"❌ Error creating default admin user: {e}")

if __name__ == "__main__":
    print("Starting Lote Chemical AI Document Assistant...")
    
    # Create default admin user if needed
    create_default_admin_user()
    
    print("Access the application at: http://localhost:8000")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)