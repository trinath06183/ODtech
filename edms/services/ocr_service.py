import re
import logging
from django.core.files.uploadedfile import UploadedFile

logger = logging.getLogger(__name__)

class OCRService:
    @staticmethod
    def extract_invoice_data(uploaded_file: UploadedFile) -> dict:
        """
        Extracts invoice details (Invoice Number, Total Amount) from an uploaded PDF.
        """
        if not uploaded_file.name.lower().endswith('.pdf'):
            return {"error": "Currently, only PDF files are supported for auto-extraction."}
        
        try:
            import PyPDF2
        except ImportError:
            return {"error": "PyPDF2 is not installed. Please run `pip install PyPDF2` to enable PDF auto-extraction."}
        
        try:
            # Read PDF content
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
            # Reset file pointer so Django can still save it normally later
            uploaded_file.seek(0)
            
            # Simple Regex parsing for demonstration
            # In a real-world scenario, you might use OpenAI's API or AWS Textract here.
            
            invoice_number = None
            total_amount = None
            
            # Try to find Invoice Number (e.g. "Invoice No: INV-1234")
            inv_match = re.search(r'(?i)(?:invoice\s*no|inv\.|invoice\s*#)[\s:]*([A-Z0-9\-_]+)', text)
            if inv_match:
                invoice_number = inv_match.group(1).strip()
                
            # Try to find Total Amount (e.g. "Total: 1,234.50" or "Grand Total : Rs. 500")
            amt_match = re.search(r'(?i)(?:grand\s*total|total|amount)[\s:]*(?:rs\.?|inr|₹)?\s*([\d,\.]+)', text)
            if amt_match:
                # Clean up commas
                amt_str = amt_match.group(1).replace(',', '')
                try:
                    total_amount = float(amt_str)
                except ValueError:
                    pass
            
            return {
                "success": True,
                "invoice_number": invoice_number,
                "total_amount": total_amount,
                "raw_text_preview": text[:500] # for debugging
            }
            
        except Exception as e:
            logger.exception("[OCR_SERVICE] Error extracting text from PDF.")
            uploaded_file.seek(0)
            return {"error": f"Failed to read PDF file: {str(e)}"}
