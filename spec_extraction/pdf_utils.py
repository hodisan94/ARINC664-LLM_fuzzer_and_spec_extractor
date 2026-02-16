"""
PDF utilities for extracting text from ARINC 664 Part 7 specification.
"""

from typing import List, Tuple
import PyPDF2


# Chapter mapping: section name -> (start_page, end_page)
# Pages are 1-based - based on actual ARINC 664 Part 7 structure (145 pages)
CHAPTERS = {
    "1. Introduction and Overview": (1, 12),
    "3.1 End System - Virtual Links and Scheduling": (13, 25),
    "3.2 End System - Redundancy Management": (26, 35),
    "3.3 End System - IP Layer": (36, 50),
    "3.4 End System - Communication Ports": (51, 60),
    "4. Switch Specification": (61, 75),
    "5. Network Management": (76, 90),
    "Attachment 1 - Data Format": (91, 110),
    "Attachment 2 - Protocol Profiles": (111, 130),
    "Appendices": (131, 145),
}


# Relevant chapters for protocol rule extraction
# Scanning ALL chapters to ensure we don't miss any rules
RELEVANT_CHAPTERS = list(CHAPTERS.keys())


def extract_text_from_page(pdf_path: str, page_num: int) -> str:
    """
    Extract text from a single page (1-based indexing).
    
    Args:
        pdf_path: Path to PDF file
        page_num: Page number (1-based)
    
    Returns:
        Extracted text from the page
    """
    with open(pdf_path, 'rb') as pdf_file:
        reader = PyPDF2.PdfReader(pdf_file)
        # Convert to 0-based indexing
        if page_num - 1 < len(reader.pages):
            page = reader.pages[page_num - 1]
            return page.extract_text() or ""
        return ""


def extract_text_from_range(pdf_path: str, start_page: int, end_page: int) -> str:
    """
    Extract text from a range of pages (1-based indexing, inclusive).
    
    Args:
        pdf_path: Path to PDF file
        start_page: Starting page number (1-based)
        end_page: Ending page number (1-based, inclusive)
    
    Returns:
        Combined text from all pages in range
    """
    with open(pdf_path, 'rb') as pdf_file:
        reader = PyPDF2.PdfReader(pdf_file)
        text_parts = []
        max_page = len(reader.pages)
        
        for page_num in range(start_page, min(end_page + 1, max_page + 1)):
            # Convert to 0-based indexing
            if page_num - 1 < max_page:
                page = reader.pages[page_num - 1]
                page_text = page.extract_text() or ""
                text_parts.append(f"--- PAGE {page_num} ---\n{page_text}\n")
        
        return "\n".join(text_parts)


def extract_chapter(pdf_path: str, chapter_name: str) -> str:
    """
    Extract text from a specific chapter.
    
    Args:
        pdf_path: Path to PDF file
        chapter_name: Name of the chapter (must be in CHAPTERS)
    
    Returns:
        Extracted text from the chapter
    
    Raises:
        ValueError: If chapter_name is not found
    """
    if chapter_name not in CHAPTERS:
        raise ValueError(f"Chapter '{chapter_name}' not found in CHAPTERS mapping")
    
    start_page, end_page = CHAPTERS[chapter_name]
    return extract_text_from_range(pdf_path, start_page, end_page)


def chunk_text(text: str, max_chars: int = 6000) -> List[str]:
    """
    Split text into chunks of approximately max_chars.
    Tries to break at paragraph boundaries when possible.
    
    Args:
        text: Text to split
        max_chars: Maximum characters per chunk
    
    Returns:
        List of text chunks
    """
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # Split by paragraphs first
    paragraphs = text.split("\n\n")
    
    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_chars:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            # If paragraph itself is too long, split it
            if len(para) > max_chars:
                for i in range(0, len(para), max_chars):
                    chunks.append(para[i:i + max_chars])
                current_chunk = ""
            else:
                current_chunk = para + "\n\n"
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks if chunks else [text]


def get_all_relevant_text(pdf_path: str) -> dict:
    """
    Extract text from all relevant chapters for rule extraction.
    
    Args:
        pdf_path: Path to ARINC 664 Part 7 PDF
    
    Returns:
        Dictionary mapping chapter names to their extracted text
    """
    result = {}
    for chapter_name in RELEVANT_CHAPTERS:
        try:
            print(f"  Extracting: {chapter_name}...")
            text = extract_chapter(pdf_path, chapter_name)
            if text.strip():
                result[chapter_name] = text
        except Exception as e:
            print(f"  Warning: Could not extract {chapter_name}: {e}")
    return result
