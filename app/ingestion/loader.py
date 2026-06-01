from pathlib import Path
from typing import Dict, Optional
import logging

# Document parsing libraries
import PyPDF2
from docx import Document as DocxDocument
import markdown
from bs4 import BeautifulSoup

from app.config.settings import settings

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format=settings.LOG_FORMAT
)

logger = logging.getLogger(__name__)


class DocumentLoader:
    """
    Unified document loader for multiple file formats.
    
    Supports:
    - PDF (.pdf)
    - Text files (.txt)
    - Word documents (.docx)
    - Markdown files (.md)
    """

    def __init__(self):
        self.supported_types = settings.SUPPORTED_FILE_TYPES
        logger.info(f"DocumentLoader initialized. Supported types: {self.supported_types}")

    def load(self, file_path: str) -> Dict[str, any]:
        """
        Load a document and extract its text content.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Dictionary containing:
                - 'text': Extracted text content
                - 'metadata': File metadata (name, type, size, etc.)
                
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file type is not supported
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_ext = path.suffix.lower()
        
        if file_ext not in self.supported_types:
            raise ValueError(
                f"Unsupported file type: {file_ext}. "
                f"Supported types: {self.supported_types}"
            )
        
        logger.info(f"Loading document: {path.name}")
        
        # Route to appropriate loader
        if file_ext == ".pdf":
            text = self._load_pdf(path)
        elif file_ext == ".txt":
            text = self._load_txt(path)
        elif file_ext == ".docx":
            text = self._load_docx(path)
        elif file_ext == ".md":
            text = self._load_markdown(path)
        else:
            raise ValueError(f"No loader implemented for {file_ext}")
        
        # Build metadata
        metadata = {
            "filename": path.name,
            "file_type": file_ext,
            "file_size_bytes": path.stat().st_size,
            "char_count": len(text),
        }
        
        logger.info(f"✓ Loaded {path.name}: {len(text)} characters")
        
        return {
            "text": text,
            "metadata": metadata,
        }

    # ------------------------------------------------------------------
    # Format-specific loaders
    # ------------------------------------------------------------------

    def _load_pdf(self, path: Path) -> str:
        """Extract text from PDF using PyPDF2."""
        text = []
        
        try:
            with open(path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                num_pages = len(pdf_reader.pages)
                
                for page_num in range(num_pages):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    
                    if page_text:
                        text.append(page_text)
                
                logger.info(f"  Extracted {num_pages} pages from PDF")
                
        except Exception as e:
            logger.error(f"Failed to parse PDF {path.name}: {e}")
            raise RuntimeError(f"PDF parsing failed: {e}")
        
        return "\n\n".join(text)

    def _load_txt(self, path: Path) -> str:
        """Load plain text file."""
        try:
            with open(path, 'r', encoding='utf-8') as file:
                text = file.read()
            return text
        except UnicodeDecodeError:
            # Fallback to Latin-1 encoding
            logger.warning(f"UTF-8 decode failed for {path.name}, trying latin-1")
            with open(path, 'r', encoding='latin-1') as file:
                text = file.read()
            return text

    def _load_docx(self, path: Path) -> str:
        """Extract text from Word document."""
        try:
            doc = DocxDocument(path)
            paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
            
            logger.info(f"  Extracted {len(paragraphs)} paragraphs from DOCX")
            
            return "\n\n".join(paragraphs)
            
        except Exception as e:
            logger.error(f"Failed to parse DOCX {path.name}: {e}")
            raise RuntimeError(f"DOCX parsing failed: {e}")

    def _load_markdown(self, path: Path) -> str:
        """
        Load Markdown file and convert to plain text.
        Strips HTML tags from rendered markdown.
        """
        try:
            with open(path, 'r', encoding='utf-8') as file:
                md_text = file.read()
            
            # Convert markdown to HTML
            html = markdown.markdown(md_text)
            
            # Strip HTML tags to get plain text
            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text(separator='\n\n')
            
            return text
            
        except Exception as e:
            logger.error(f"Failed to parse Markdown {path.name}: {e}")
            raise RuntimeError(f"Markdown parsing failed: {e}")

    # ------------------------------------------------------------------
    # Batch loading
    # ------------------------------------------------------------------

    def load_directory(self, directory_path: str) -> Dict[str, Dict]:
        """
        Load all supported documents from a directory.
        
        Args:
            directory_path: Path to directory containing documents
            
        Returns:
            Dictionary mapping filename -> loaded document data
        """
        dir_path = Path(directory_path)
        
        if not dir_path.exists() or not dir_path.is_dir():
            raise ValueError(f"Invalid directory: {directory_path}")
        
        documents = {}
        
        for file_path in dir_path.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in self.supported_types:
                try:
                    doc_data = self.load(str(file_path))
                    documents[file_path.name] = doc_data
                except Exception as e:
                    logger.error(f"Failed to load {file_path.name}: {e}")
        
        logger.info(f"✓ Loaded {len(documents)} documents from {dir_path.name}")
        
        return documents


# ============================================================
# Global Loader Instance
# ============================================================
_loader_instance = None


def get_loader() -> DocumentLoader:
    """Returns a singleton instance of DocumentLoader."""
    global _loader_instance
    
    if _loader_instance is None:
        _loader_instance = DocumentLoader()
    
    return _loader_instance