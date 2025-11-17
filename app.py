from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import easyocr
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List 
from PIL import Image, ImageEnhance, ImageFilter
import google.generativeai as genai
import os
import json
import re
from werkzeug.utils import secure_filename
try:
    import pdf2image
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("Warning: pdf2image not installed. PDF support disabled.")

app = Flask(__name__)
CORS(app)

# Configuration - Using SQLite (no installation needed!)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///insurance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# IMPORTANT: Replace with your free Gemini API key from: https://makersuite.google.com/app/apikey
GEMINI_API_KEY = 'AIzaSyCmcdQ-adcLbOiDjA-e4dcB3LdjFa1OWPw'
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# Initialize EasyOCR Reader (supports English and Hindi/Devanagari)
# NOTE: 'te' (Telugu) is removed as it conflicts with 'hi' (Hindi). 
print("Initializing EasyOCR... This may take a moment on first run.")
reader = easyocr.Reader(['en', 'hi'], gpu=False)
print("EasyOCR ready!")

db = SQLAlchemy(app)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ==================== DATABASE MODELS ====================

class PolicyFolder(db.Model):
    __tablename__ = 'policy_folders'
    id = db.Column(db.Integer, primary_key=True)
    folder_name = db.Column(db.String(200), nullable=False)
    policy_number = db.Column(db.String(100))
    company_name = db.Column(db.String(200))
    coverage_amount = db.Column(db.String(50))
    policy_type = db.Column(db.String(100))
    expiry_date = db.Column(db.String(50))
    exclusions = db.Column(db.Text)
    required_documents = db.Column(db.Text)
    
    status = db.Column(db.String(20), default='ongoing')
    completion_percentage = db.Column(db.Integer, default=0)
    
    policy_summary = db.Column(db.Text)
    policy_pdf_path = db.Column(db.String(500))
    policy_validated = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    documents = db.relationship('Document', backref='folder', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'folder_name': self.folder_name,
            'policy_number': self.policy_number,
            'company_name': self.company_name,
            'coverage_amount': self.coverage_amount,
            'policy_type': self.policy_type,
            'expiry_date': self.expiry_date,
            'exclusions': json.loads(self.exclusions) if self.exclusions else [],
            'required_documents': json.loads(self.required_documents) if self.required_documents else [],
            'status': self.status,
            'completion_percentage': self.completion_percentage,
            'policy_summary': self.policy_summary,
            'policy_validated': self.policy_validated,
            'document_count': len(self.documents),
            'created_at': self.created_at.isoformat()
        }

class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    folder_id = db.Column(db.Integer, db.ForeignKey('policy_folders.id'), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    document_type = db.Column(db.String(100))
    
    extracted_text = db.Column(db.Text)
    extracted_data = db.Column(db.Text)
    completeness = db.Column(db.Integer, default=0)
    is_duplicate = db.Column(db.Boolean, default=False)
    
    amount = db.Column(db.Float, default=0)
    summary = db.Column(db.Text)
    
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        data = json.loads(self.extracted_data) if self.extracted_data else {}
        return {
            'id': self.id,
            'folder_id': self.folder_id,
            'filename': self.filename,
            'document_type': self.document_type,
            'completeness': self.completeness,
            'is_duplicate': self.is_duplicate,
            'amount': self.amount,
            'summary': self.summary,
            'extracted_data': data,
            'uploaded_at': self.uploaded_at.isoformat()
        }

class AnalysisReport(db.Model):
    __tablename__ = 'analysis_reports'
    id = db.Column(db.Integer, primary_key=True)
    folder_id = db.Column(db.Integer, db.ForeignKey('policy_folders.id'), nullable=False)
    
    total_bill_amount = db.Column(db.Float, default=0)
    covered_amount = db.Column(db.Float, default=0)
    user_pays = db.Column(db.Float, default=0)
    
    missing_documents = db.Column(db.Text)
    fraud_warnings = db.Column(db.Text)
    exclusions_found = db.Column(db.Text)
    claim_guide = db.Column(db.Text)
    checklist = db.Column(db.Text)
    summary = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'total_bill_amount': self.total_bill_amount,
            'covered_amount': self.covered_amount,
            'user_pays': self.user_pays,
            'missing_documents': json.loads(self.missing_documents) if self.missing_documents else [],
            'fraud_warnings': json.loads(self.fraud_warnings) if self.fraud_warnings else [],
            'exclusions_found': json.loads(self.exclusions_found) if self.exclusions_found else [],
            'claim_guide': json.loads(self.claim_guide) if self.claim_guide else [],
            'checklist': json.loads(self.checklist) if self.checklist else [],
            'summary': self.summary,
            'created_at': self.created_at.isoformat()
        }

class QnA(db.Model):
    __tablename__ = 'qna'
    id = db.Column(db.Integer, primary_key=True)
    folder_id = db.Column(db.Integer, db.ForeignKey('policy_folders.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'question': self.question,
            'answer': self.answer,
            'created_at': self.created_at.isoformat()
        }

# ==================== HELPER FUNCTIONS ====================

def enhance_image(image):
    """Enhance image quality for better OCR - makes blurry images clearer"""
    try:
        # Convert to RGB first if needed
        if image.mode not in ['RGB', 'L']:
            image = image.convert('RGB')
        
        # Convert to grayscale for better OCR
        img = image.convert('L')
        
        # Increase contrast significantly
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.5)
        
        # Increase sharpness
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)
        
        # Apply denoising filter
        img = img.filter(ImageFilter.MedianFilter(size=3))
        
        # Resize if too small for better OCR accuracy
        width, height = img.size
        if width < 1500:
            scale = 1500 / width
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.LANCZOS)
        
        return img
    except Exception as e:
        print(f"Image enhancement error: {e}")
        return image

def extract_text_from_image(image_path):
    """Extract text using EasyOCR with image enhancement"""
    try:
        print(f"Extracting text from: {image_path}")
        
        # Check if it's a PDF
        if image_path.lower().endswith('.pdf'):
            if not PDF_SUPPORT:
                return "PDF support not available. Please install pdf2image."
            
            print("Converting PDF to images...")
            # Convert PDF to images
            images = pdf2image.convert_from_path(image_path, dpi=300)
            text_parts = []
            
            for idx, img in enumerate(images):
                print(f"Processing page {idx + 1}/{len(images)}")
                # Enhance each page
                enhanced_img = enhance_image(img)
                
                # Save temporarily for EasyOCR
                temp_path = image_path.replace('.pdf', f'_page_{idx}.jpg')
                enhanced_img.save(temp_path)
                
                # Extract text using EasyOCR
                result = reader.readtext(temp_path, detail=0, paragraph=True)
                page_text = ' '.join(result)
                text_parts.append(page_text)
                
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
            full_text = ' '.join(text_parts)
            print(f"Extracted {len(full_text)} characters from PDF")
            return full_text
        else:
            # Open and enhance image
            img = Image.open(image_path)
            enhanced_img = enhance_image(img)
            
            # Save enhanced image temporarily
            temp_path = image_path.replace(os.path.splitext(image_path)[1], '_enhanced.jpg')
            enhanced_img.save(temp_path)
            
            # Extract text using EasyOCR
            print("Running OCR...")
            result = reader.readtext(temp_path, detail=0, paragraph=True)
            text = ' '.join(result)
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            print(f"Extracted {len(text)} characters")
            return text
    except Exception as e:
        print(f"OCR Error: {e}")
        # Fallback: try without enhancement
        try:
            print("Trying fallback OCR without enhancement...")
            result = reader.readtext(image_path, detail=0, paragraph=True)
            return ' '.join(result)
        except Exception as e2:
            print(f"Fallback OCR also failed: {e2}")
            return ""

def ask_gemini(prompt):
    """Call Google Gemini AI"""
    try:
        print("Calling Gemini API...")
        response = model.generate_content(prompt)
        print("Gemini response received")
        return response.text
    except Exception as e:
        print(f"Gemini Error: {e}")
        return None

def validate_policy_document(text):
    """Check if document is a valid insurance policy using Gemini"""
    print("Validating policy document...")
    prompt = f"""
    Analyze this text and determine if it's a valid insurance policy document.
    Look for: policy number, coverage details, insurance company name, terms and conditions.
    
    Text: {text[:2000]}
    
    Respond with ONLY 'YES' or 'NO'.
    If YES, it's a valid insurance policy.
    If NO, it's not an insurance policy document.
    """
    
    response = ask_gemini(prompt)
    is_valid = response and 'YES' in response.upper()
    print(f"Policy validation result: {'Valid' if is_valid else 'Invalid'}")
    return is_valid

def extract_policy_data(text):
    """Extract policy information using Gemini AI"""
    print("Extracting policy data...")
    prompt = f"""
    Extract key information from this insurance policy document:
    
    Text: {text}
    
    Provide a JSON response with these exact keys (extract actual values from the text):
    {{
        "policy_number": "extracted policy number or POL+timestamp if not found",
        "company_name": "insurance company name",
        "coverage_amount": "coverage amount with ₹ symbol",
        "policy_type": "type of policy (health/life/vehicle etc)",
        "expiry_date": "expiry/validity date in DD-MMM-YYYY format",
        "exclusions": ["list", "of", "exclusions", "and", "limitations"],
        "required_documents": ["list", "of", "required", "documents", "for", "claims"],
        "summary": "comprehensive 2-3 sentence summary of policy coverage and key benefits"
    }}
    
    Extract actual values from the document. Be thorough with exclusions and required documents.
    Return ONLY valid JSON, no additional text or markdown.
    """
    
    response = ask_gemini(prompt)
    try:
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            print("Policy data extracted successfully")
            return data
    except Exception as e:
        print(f"Error parsing policy data: {e}")
    
    # Fallback data
    print("Using fallback policy data")
    return {
        "policy_number": f"POL{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "company_name": "Insurance Company",
        "coverage_amount": "₹5,00,000",
        "policy_type": "Health Insurance",
        "expiry_date": "31-Dec-2025",
        "exclusions": ["Cosmetic procedures", "Dental care", "Pre-existing diseases for first year"],
        "required_documents": ["Hospital bills", "Discharge summary", "Prescriptions", "Doctor signature", "Medical reports"],
        "summary": "Comprehensive health insurance policy covering hospitalization expenses up to policy limit."
    }

def analyze_document(text, folder_id):
    """Enhanced document analysis with cross-referencing to policy"""
    print(f"Analyzing document for folder {folder_id}...")
    folder = PolicyFolder.query.get_or_404(folder_id)
    
    # Get all existing documents for cross-verification
    existing_docs = Document.query.filter_by(folder_id=folder_id).all()
    existing_summaries = "\n".join([f"- {doc.filename}: {doc.summary}" for doc in existing_docs])
    
    coverage = folder.coverage_amount
    exclusions = folder.exclusions
    required_docs = folder.required_documents
    policy_text_snippet = folder.policy_summary[:500] if folder.policy_summary else ""
    
    prompt = f"""
    You are an expert insurance fraud detection AI. Analyze this medical/insurance document for claim processing.
    
    POLICY CONTEXT (THE RULEBOOK):
    - Coverage: {coverage}
    - Exclusions: {exclusions}
    - Required Documents: {required_docs}
    - Policy Summary: {policy_text_snippet}
    
    EXISTING DOCUMENTS IN THIS CLAIM:
    {existing_summaries}
    
    CURRENT DOCUMENT TEXT TO ANALYZE:
    {text}
    
    CRITICAL FRAUD DETECTION CHECKS:
    1. **Date Consistency**: Check if document dates are within policy validity period
    2. **Treatment Exclusions**: Verify treatments/procedures against policy exclusions
    3. **Amount Anomalies**: Flag unusually high amounts or duplicate charges
    4. **Cross-Document Consistency**: Check if dates, patient names, and diagnoses match across documents
    5. **Required Signatures/Seals**: Verify presence of doctor signatures and hospital seals
    6. **Waiting Period Violations**: Check if claim is made during waiting periods
    7. **Pre-existing Conditions**: Flag treatments for pre-existing conditions if not covered
    
    Provide detailed analysis in JSON format:
    {{
        "document_type": "bill/prescription/discharge_summary/medical_report/diagnostic_report/other",
        "hospital_name": "hospital/clinic name or null",
        "doctor_name": "doctor name or null",
        "patient_name": "patient name or null",
        "date": "document date in DD-MMM-YYYY or null",
        "disease_type": "disease/condition mentioned or null",
        "treatment_details": "brief description of treatment",
        "amount": numeric amount in rupees or 0,
        "has_doctor_signature": true/false,
        "has_hospital_seal": true/false,
        "has_date": true/false,
        "has_patient_details": true/false,
        "completeness": percentage 0-100 based on document completeness,
        "summary": "brief 2-3 sentence summary",
        "missing_info": ["critical", "missing", "information"],
        "fraud_indicators": [
            "Specific fraud concerns with severity level (HIGH/MEDIUM/LOW)",
            "Example: HIGH - Treatment date is before policy start date",
            "Example: MEDIUM - Missing hospital seal verification"
        ],
        "policy_compliance": {{
            "is_covered": true/false,
            "exclusion_violated": "specific exclusion name or null",
            "waiting_period_issue": true/false,
            "reason": "explanation of coverage decision"
        }}
    }}
    
    Be thorough and strict. Flag ALL suspicious patterns.
    Return ONLY valid JSON.
    """
    
    response = ask_gemini(prompt)
    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            print(f"Document analyzed: {data.get('document_type')} - Completeness: {data.get('completeness')}%")
            print(f"Fraud indicators: {len(data.get('fraud_indicators', []))}")
            return data
    except Exception as e:
        print(f"Error analyzing document: {e}")
    
    return {
        "document_type": "unknown",
        "completeness": 50,
        "amount": 0,
        "summary": "Analysis incomplete",
        "missing_info": ["Analysis failed"],
        "fraud_indicators": ["Could not complete fraud analysis"],
        "policy_compliance": {"is_covered": False, "reason": "Analysis failed"}
    }

def check_duplicate(folder_id, new_text):
    """Check if document is duplicate using text similarity"""
    print("Checking for duplicates...")
    documents = Document.query.filter_by(folder_id=folder_id).all()
    for doc in documents:
        if doc.extracted_text:
            similarity = calculate_similarity(new_text, doc.extracted_text)
            if similarity > 0.85:
                print(f"Duplicate detected! Similarity: {similarity:.2%}")
                return True
    print("No duplicates found")
    return False

def calculate_similarity(text1, text2):
    """Simple text similarity using word overlap"""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union)

# ==================== HELPER FUNCTIONS (Cont.) ====================
# ... (all functions before this remain the same)

def generate_comprehensive_analysis(folder_id):
    """Agentic AI analysis with deep fraud detection"""
    print(f"Generating agentic analysis for folder {folder_id}...")
    folder = PolicyFolder.query.get(folder_id)
    documents = Document.query.filter_by(folder_id=folder_id).all()
    
    # Compile all document data
    doc_details = []
    for doc in documents:
        extracted_data = json.loads(doc.extracted_data) if doc.extracted_data else {}
        doc_details.append({
            'filename': doc.filename,
            'type': doc.document_type,
            'summary': doc.summary,
            'amount': doc.amount,
            'date': extracted_data.get('date'),
            'hospital': extracted_data.get('hospital_name'),
            'doctor': extracted_data.get('doctor_name'),
            'patient': extracted_data.get('patient_name'),
            'treatment': extracted_data.get('treatment_details'),
            'fraud_indicators': extracted_data.get('fraud_indicators', []),
            'compliance': extracted_data.get('policy_compliance', {})
        })
    
    doc_summaries = "\n".join([
        f"- {d['filename']} ({d['type']}): {d['summary']} | Amount: ₹{d['amount']} | Date: {d['date']} | Hospital: {d['hospital']}"
        for d in doc_details
    ])
    
    all_fraud_indicators = []
    for d in doc_details:
        if d['fraud_indicators']:
            all_fraud_indicators.extend([f"[{d['filename']}]: {ind}" for ind in d['fraud_indicators']])
    
    total_amount = sum([d['amount'] for d in doc_details])
    
    prompt = f"""
    You are an expert insurance claim analyst. Perform comprehensive agentic analysis.
    
    POLICY DETAILS:
    - Company: {folder.company_name}
    - Policy Number: {folder.policy_number}
    - Coverage: {folder.coverage_amount}
    - Policy Type: {folder.policy_type}
    - Expiry: {folder.expiry_date}
    - Exclusions: {folder.exclusions}
    - Required Documents: {folder.required_documents}
    - Policy Summary: {folder.policy_summary}
    
    UPLOADED DOCUMENTS ({len(documents)} total):
    {doc_summaries}
    
    Total Claimed Amount: ₹{total_amount}
    
    DETECTED FRAUD INDICATORS:
    {chr(10).join(all_fraud_indicators) if all_fraud_indicators else "None detected at document level"}
    
    AGENTIC ANALYSIS TASKS:
    
    1. **Cross-Document Verification**:
       - Verify patient names match across all documents
       - Check date consistency and chronological order
       - Validate hospital/doctor information consistency
       - Detect duplicate charges or billing
    
    2. **Policy Compliance Deep Check**:
       - Match each expense against policy coverage limits
       - Identify expenses falling under exclusions
       - Check waiting period violations
       - Verify required documents are present
    
    3. **Fraud Pattern Detection**:
       - Unusual billing patterns
       - Inflated costs compared to standard rates
       - Missing critical information (signatures, seals, dates)
       - Inconsistent diagnoses or treatments
       - Timeline anomalies
    
    4. **Financial Calculation**:
       - Calculate total eligible amount based on policy
       - Account for co-payments, deductibles
       - Subtract non-covered expenses
       - Apply policy limits
    
    Provide comprehensive analysis in JSON:
    {{
        "total_bill_amount": {total_amount},
        "covered_amount": calculated eligible amount after all checks,
        "user_pays": amount user must pay (deductibles + non-covered),
        "missing_documents": ["specific required documents not yet uploaded"],
        "fraud_warnings": [
            "Detailed fraud warnings with severity and evidence",
            "Format: SEVERITY - Description - Evidence from documents"
        ],
        "exclusions_found": [
            "Specific expenses/treatments that fall under exclusions",
            "Include amounts if applicable"
        ],
        "claim_guide": [
            "Step 1: Specific actionable step",
            "Step 2: Next step with details",
            "Continue with complete process"
        ],
        "checklist": [
            {{"item": "Hospital bills with seal and signature", "completed": true/false}},
            {{"item": "Discharge summary", "completed": true/false}},
            {{"item": "All prescriptions", "completed": true/false}},
            {{"item": "Diagnostic reports", "completed": true/false}},
            {{"item": "Doctor registration verification", "completed": true/false}}
        ],
        "summary": "4-5 sentence comprehensive analysis covering: overall claim viability, major concerns, coverage assessment, fraud risk level, and recommended next steps",
        "claim_approval_likelihood": "HIGH/MEDIUM/LOW with explanation",
        "recommendations": ["specific actions to improve claim success"]
    }}
    
    Be thorough, realistic, and prioritize fraud detection.
    Return ONLY valid JSON.
    """
    
    response = ask_gemini(prompt)
    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            print("Agentic analysis completed successfully")
            return data
    except Exception as e:
        print(f"Error in agentic analysis: {e}")
    
    # Enhanced fallback
    return {
        "total_bill_amount": total_amount,
        "covered_amount": total_amount * 0.7,
        "user_pays": total_amount * 0.3,
        "missing_documents": [],
        "fraud_warnings": all_fraud_indicators if all_fraud_indicators else [],
        "exclusions_found": [],
        "claim_guide": [
            "Review all fraud warnings carefully",
            "Obtain missing documents with proper verification",
            "Submit claim with complete documentation",
            "Follow up within 7-15 days"
        ],
        "checklist": [],
        "summary": "Analysis completed with potential issues detected. Review warnings carefully.",
        "claim_approval_likelihood": "MEDIUM",
        "recommendations": ["Address all fraud indicators before submission"]
    }

def update_folder_status(folder_id):
    """Update folder completion percentage and status based on document analysis"""
    print(f"Updating folder status for {folder_id}...")
    folder = PolicyFolder.query.get_or_404(folder_id)
    documents = Document.query.filter_by(folder_id=folder_id).all()
    
    if not documents:
        folder.completion_percentage = 0
        folder.status = 'ongoing'
    else:
        # Calculate average completeness
        avg_completeness = sum([doc.completeness for doc in documents]) / len(documents)
        folder.completion_percentage = int(avg_completeness)
        
        # Check for fraud indicators
        has_fraud = any([
            doc.extracted_data and 'fraud' in doc.extracted_data.lower() 
            for doc in documents
        ])
        
        # Set status based on completion and fraud
        if has_fraud:
            folder.status = 'fraud'
        elif folder.completion_percentage >= 95:
            folder.status = 'completed'
        elif folder.completion_percentage >= 70:
            folder.status = 'valid'
        else:
            folder.status = 'ongoing'
    
    print(f"Folder status: {folder.status} ({folder.completion_percentage}%)")
    db.session.commit()

# ==================== API ROUTES ====================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    """Get dashboard statistics"""
    folders = PolicyFolder.query.all()
    stats = {
        'total': len(folders),
        'valid': len([f for f in folders if f.status == 'valid']),
        'fraud': len([f for f in folders if f.status == 'fraud']),
        'ongoing': len([f for f in folders if f.status == 'ongoing']),
        'completed': len([f for f in folders if f.status == 'completed'])
    }
    print(f"Dashboard stats: {stats}")
    return jsonify(stats)

@app.route('/api/folders', methods=['GET'])
def get_folders():
    """Get all policy folders"""
    folders = PolicyFolder.query.order_by(PolicyFolder.created_at.desc()).all()
    print(f"Retrieved {len(folders)} folders")
    return jsonify([f.to_dict() for f in folders])

@app.route('/api/folders/<int:folder_id>', methods=['GET', 'DELETE'])
def handle_folder(folder_id):
    """Get or delete folder"""
    folder = PolicyFolder.query.get_or_404(folder_id)
    
    if request.method == 'DELETE':
        print(f"Deleting folder {folder_id}")
        # Delete associated files
        for doc in folder.documents:
            if os.path.exists(doc.file_path):
                os.remove(doc.file_path)
        if folder.policy_pdf_path and os.path.exists(folder.policy_pdf_path):
            os.remove(folder.policy_pdf_path)
        
        db.session.delete(folder)
        db.session.commit()
        print(f"Folder {folder_id} deleted")
        return '', 204
    
    return jsonify(folder.to_dict())

@app.route('/api/upload-policy', methods=['POST'])
def upload_policy():
    """Step 1: Upload and validate policy PDF/image"""
    print("\n=== POLICY UPLOAD STARTED ===")
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    folder_name = request.form.get('folder_name', 'New Policy')
    
    print(f"Folder name: {folder_name}")
    print(f"File: {file.filename}")
    
    # Save file
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"policy_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}")
    file.save(filepath)
    print(f"File saved to: {filepath}")
    
    # Extract text
    extracted_text = extract_text_from_image(filepath)
    
    if not extracted_text or len(extracted_text) < 50:
        os.remove(filepath)
        return jsonify({'error': 'Could not extract text from document. Please upload a clearer image or PDF.'}), 400
    
    # Validate policy document
    is_valid = validate_policy_document(extracted_text)
    
    if not is_valid:
        os.remove(filepath)
        return jsonify({'error': 'This does not appear to be a valid insurance policy document. Please upload a policy document with coverage details.'}), 400
    
    # Extract policy data using Gemini
    policy_data = extract_policy_data(extracted_text)
    
    # Create folder
    folder = PolicyFolder(
        folder_name=folder_name,
        policy_number=policy_data['policy_number'],
        company_name=policy_data['company_name'],
        coverage_amount=policy_data['coverage_amount'],
        policy_type=policy_data['policy_type'],
        expiry_date=policy_data['expiry_date'],
        exclusions=json.dumps(policy_data['exclusions']),
        required_documents=json.dumps(policy_data['required_documents']),
        policy_summary=policy_data['summary'],
        policy_pdf_path=filepath,
        policy_validated=True
    )
    
    db.session.add(folder)
    db.session.commit()
    
    print(f"=== POLICY UPLOAD COMPLETED - Folder ID: {folder.id} ===\n")
    return jsonify(folder.to_dict()), 201

@app.route('/api/folders/<int:folder_id>/upload', methods=['POST'])
def upload_document(folder_id):
    """Step 2: Upload multiple bills/documents to folder with enhanced analysis"""
    print(f"\n=== MULTI-DOCUMENT UPLOAD TO FOLDER {folder_id} ===")
    
    folder = PolicyFolder.query.get_or_404(folder_id)
    
    if folder.completion_percentage >= 100:
        return jsonify({'error': 'Folder is 100% complete. No more uploads allowed.'}), 400
    
    files_list = request.files.getlist('files')
    
    if not files_list or all(f.filename == '' for f in files_list):
        return jsonify({'error': 'No files uploaded'}), 400
        
    uploaded_documents = []
    failed_uploads = []

    for file in files_list:
        if file.filename == '':
            continue
            
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], 
                               f"{folder_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}")
        
        try:
            file.save(filepath)
            print(f"Document saved: {filepath}")
            
            # Extract text
            extracted_text = extract_text_from_image(filepath)
            
            if not extracted_text or len(extracted_text) < 20:
                os.remove(filepath)
                failed_uploads.append({'filename': filename, 'reason': 'Could not extract text'})
                continue
            
            # Check duplicate
            is_duplicate = check_duplicate(folder_id, extracted_text)
            if is_duplicate:
                os.remove(filepath)
                failed_uploads.append({'filename': filename, 'reason': 'Duplicate document'})
                continue
            
            # Analyze document with enhanced fraud detection
            analysis = analyze_document(extracted_text, folder_id)
            
            # Create document record
            document = Document(
                folder_id=folder_id,
                filename=filename,
                file_path=filepath,
                document_type=analysis.get('document_type', 'unknown'),
                extracted_text=extracted_text,
                extracted_data=json.dumps(analysis),
                completeness=analysis.get('completeness', 0),
                amount=analysis.get('amount', 0),
                summary=analysis.get('summary', ''),
                is_duplicate=False
            )
            db.session.add(document)
            db.session.commit()
            uploaded_documents.append(document.to_dict())
            
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            failed_uploads.append({'filename': filename, 'reason': str(e)})
    
    # Update folder status
    update_folder_status(folder_id)
    
    result = {
        'uploaded': uploaded_documents,
        'failed': failed_uploads,
        'total_uploaded': len(uploaded_documents),
        'total_failed': len(failed_uploads)
    }
    
    print(f"=== UPLOAD COMPLETE: {len(uploaded_documents)} succeeded, {len(failed_uploads)} failed ===\n")
    return jsonify(result), 201
    
    # --- END OF REQUIRED CHANGES ---

@app.route('/api/folders/<int:folder_id>/documents', methods=['GET'])
def get_documents(folder_id):
    """Get all documents in folder"""
    documents = Document.query.filter_by(folder_id=folder_id).all()
    return jsonify([d.to_dict() for d in documents])

@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """Delete document and update folder status"""
    print(f"Deleting document {doc_id}")
    document = Document.query.get_or_404(doc_id)
    folder_id = document.folder_id
    
    # Delete file from disk
    if os.path.exists(document.file_path):
        os.remove(document.file_path)
        print(f"File deleted: {document.file_path}")
    
    db.session.delete(document)
    db.session.commit()
    
    # Update folder status after deletion
    update_folder_status(folder_id)
    
    print(f"Document {doc_id} deleted successfully")
    return '', 204

@app.route('/api/folders/<int:folder_id>/analyze', methods=['POST'])
def analyze_folder(folder_id):
    """Generate comprehensive analysis with fraud detection and claim guide"""
    print(f"\n=== GENERATING ANALYSIS FOR FOLDER {folder_id} ===")
    
    # Generate analysis using Gemini
    analysis_data = generate_comprehensive_analysis(folder_id)
    
    # Delete old analysis if exists
    AnalysisReport.query.filter_by(folder_id=folder_id).delete()
    
    # Create new analysis report
    # ⚠️ FIX APPLIED: Using .get() with default values (0.0 for floats, [] for lists) 
    # to prevent KeyErrors if analysis_data is incomplete or the fallback data is used.
    report = AnalysisReport(
        folder_id=folder_id,
        total_bill_amount=analysis_data.get('total_bill_amount', 0.0),
        covered_amount=analysis_data.get('covered_amount', 0.0),
        user_pays=analysis_data.get('user_pays', 0.0),
        missing_documents=json.dumps(analysis_data.get('missing_documents', [])),
        fraud_warnings=json.dumps(analysis_data.get('fraud_warnings', [])),
        exclusions_found=json.dumps(analysis_data.get('exclusions_found', [])),
        claim_guide=json.dumps(analysis_data.get('claim_guide', [])),
        checklist=json.dumps(analysis_data.get('checklist', [])),
        summary=analysis_data.get('summary', 'No summary available.')
    )
    
    db.session.add(report)
    db.session.commit()
    
    print("=== ANALYSIS COMPLETED ===\n")
    # Return the newly created AnalysisReport object
    return jsonify(report.to_dict()), 201

@app.route('/api/folders/<int:folder_id>/analysis', methods=['GET'])
def get_analysis(folder_id):
    """Get latest analysis for folder"""
    analysis = AnalysisReport.query.filter_by(folder_id=folder_id).order_by(AnalysisReport.created_at.desc()).first()
    
    if not analysis:
        return jsonify({'error': 'No analysis found. Please generate analysis first.'}), 404
    
    return jsonify(analysis.to_dict())

@app.route('/api/folders/<int:folder_id>/qna', methods=['POST', 'GET'])
def handle_qna(folder_id):
    """Q&A system - Ask questions about policy or retrieve history"""
    folder = PolicyFolder.query.get_or_404(folder_id)
    
    if request.method == 'POST':
        question = request.json.get('question')
        print(f"Q&A Question: {question}")
        
        if not question:
             return jsonify({'error': 'No question provided.'}), 400

        # Get all document summaries for context
        documents = Document.query.filter_by(folder_id=folder_id).all()
        doc_context = "\n".join([f"- {doc.filename}: {doc.summary}" for doc in documents])
        
        # NOTE: folder.exclusions holds a JSON string and must be loaded to be useful
        try:
            exclusions_list = json.loads(folder.exclusions)
            exclusions_str = ", ".join(exclusions_list)
        except (json.JSONDecodeError, TypeError):
            exclusions_str = folder.exclusions or "None specified."
            
        prompt = f"""
        Answer this question about the insurance policy and uploaded documents.
        
        POLICY DETAILS:
        - Company: {folder.company_name}
        - Coverage: {folder.coverage_amount}
        - Type: {folder.policy_type}
        - Expiry: {folder.expiry_date}
        - Exclusions: {exclusions_str}
        - Summary: {folder.policy_summary}
        
        UPLOADED DOCUMENTS:
        {doc_context}
        
        USER QUESTION: {question}
        
        Provide a clear, concise, and helpful answer based on the policy details and documents.
        If the question cannot be answered from available information, say so clearly.
        """
        
        answer = ask_gemini(prompt) or "Unable to generate answer. Please try rephrasing your question."
        
        qna = QnA(
            folder_id=folder_id,
            question=question,
            answer=answer
        )
        db.session.add(qna)
        db.session.commit()
        
        # Return the newly created QnA object
        return jsonify(qna.to_dict()), 201

    elif request.method == 'GET':
        # Retrieve all QnA history for the folder
        history = QnA.query.filter_by(folder_id=folder_id).order_by(QnA.created_at.desc()).all()
        return jsonify([q.to_dict() for q in history])


# ==================== MAIN EXECUTION BLOCK ====================

if __name__ == '__main__':
    with app.app_context():
        # Ensure database tables exist before running
        db.create_all()
        print("Database initialized and tables created.")
    app.run(debug=True)