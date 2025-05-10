from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
from dotenv import load_dotenv
import google.generativeai as genai
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.document_loaders import PyMuPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import ConversationalRetrievalChain
import tempfile
import logging
import time
import asyncio


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class LoggedGoogleGenerativeAIEmbeddings(GoogleGenerativeAIEmbeddings):
    def embed_documents(self, texts):
        logger.info(f"[Gemini Embeddings] Embedding {len(texts)} documents")
        return super().embed_documents(texts)

    def embed_query(self, text):
        logger.info("[Gemini Embeddings] Embedding single query")
        return super().embed_query(text)
    
class LoggedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    def _call(self, prompt, stop=None):
        truncated = prompt[:200].replace("\n", " ")
        logger.info(f"[Gemini Chat] Sending prompt (truncated): {truncated}...")
        return super()._call(prompt, stop=stop)

# Initialize Gemini API
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment variables")

# Configure Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# Initialize FastAPI app
app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React app's default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize embeddings with the correct model name
embeddings = LoggedGoogleGenerativeAIEmbeddings(
    model="models/embedding-001",
    google_api_key=GOOGLE_API_KEY,
)

# Pydantic models for request/response
class ChatMessage(BaseModel):
    message: str
    chat_history: Optional[List[List[str]]] = []

# Store vector DB in memory (you might want to persist this in production)
vector_store = None
conversation_chain = None

async def process_with_retry(operation, *args, max_retries=3, initial_delay=4, **kwargs):
    last_error = None
    for attempt in range(max_retries):
        try:
            result = operation(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as e:
            last_error = e
            if "quota" in str(e).lower() or "429" in str(e):
                delay = initial_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Rate limit hit, attempt {attempt + 1}/{max_retries}. Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
                continue
            raise HTTPException(status_code=500, detail=str(e))
    
    if last_error:
        if "quota" in str(last_error).lower() or "429" in str(last_error):
            raise HTTPException(
                status_code=429,
                detail="API rate limit exceeded. Please try again in a few minutes."
            )
        raise HTTPException(status_code=500, detail=str(last_error))

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    global vector_store, conversation_chain
    
    logger.info(f"Received file upload request: {file.filename}")
    
    if not file.filename.endswith('.pdf'):
        logger.error(f"Invalid file type: {file.filename}")
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # Save the uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
        try:
            content = await file.read()
            temp_file.write(content)
            temp_file.flush()
            logger.info(f"File saved temporarily at: {temp_file.name}")
            
            # Load and process the PDF
            logger.info("Loading PDF with PyMuPDFLoader")
            loader = PyMuPDFLoader(temp_file.name)
            documents = loader.load()
            logger.info(f"PDF loaded successfully. Number of pages: {len(documents)}")
            
            # Split documents into chunks
            logger.info("Splitting documents into chunks")
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200
            )
            splits = text_splitter.split_documents(documents)
            logger.info(f"Documents split into {len(splits)} chunks")
            
            # Create vector store with retry logic
            logger.info("Creating vector store")
            vector_store = await process_with_retry(
                Chroma.from_documents,
                documents=splits,
                embedding=embeddings
            )
            logger.info("Vector store created successfully")
            
            # Initialize conversation chain with the correct model name
            logger.info("Initializing conversation chain")
            llm = LoggedChatGoogleGenerativeAI(
                model="models/gemini-1.5-pro",
                temperature=0.7,
                google_api_key=GOOGLE_API_KEY,
                convert_system_message_to_human=True
            )
            conversation_chain = ConversationalRetrievalChain.from_llm(
                llm=llm,
                retriever=vector_store.as_retriever(),
                return_source_documents=True
            )
            logger.info("Conversation chain initialized successfully")
            
        except Exception as e:
            logger.error(f"Error processing PDF: {str(e)}")
            if "quota" in str(e).lower() or "429" in str(e):
                raise HTTPException(
                    status_code=429,
                    detail="API rate limit exceeded. Please try again in a few minutes."
                )
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            # Clean up the temporary file
            try:
                os.unlink(temp_file.name)
                logger.info("Temporary file cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up temporary file: {str(e)}")
    
    logger.info("PDF processing completed successfully")
    return {"message": "PDF processed successfully"}

@app.post("/chat")
async def chat(chat_input: ChatMessage):
    if not vector_store or not conversation_chain:
        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF file first"
        )
    
    try:
        logger.info(f"Processing chat message: {chat_input.message}")
        # Process the chat message with retry logic
        response = await process_with_retry(
            conversation_chain.invoke,
            {
                "question": chat_input.message,
                "chat_history": chat_input.chat_history
            }
        )
        
        return {
            "response": response["answer"],
            "source_documents": [
                {
                    "page": doc.metadata.get("page", 0),
                    "content": doc.page_content[:200] + "..."  # First 200 chars
                }
                for doc in response.get("source_documents", [])
            ]
        }
        
    except Exception as e:
        logger.error(f"Error processing chat message: {str(e)}")
        if "quota" in str(e).lower() or "429" in str(e):
            raise HTTPException(
                status_code=429,
                detail="API rate limit exceeded. Please try again in a few minutes."
            )
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 