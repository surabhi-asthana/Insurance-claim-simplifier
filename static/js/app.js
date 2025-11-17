const API_BASE = 'http://localhost:5000/api';

let currentFolderId = null;
let policyFile = null;

// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', () => {
    console.log('Insurance Claim Simplifier loaded');
    initDashboard();
    setupEventListeners();
});

function setupEventListeners() {
    // Dashboard
    document.getElementById('newPolicyBtn').addEventListener('click', () => showView('uploadPolicy'));
    
    // Upload Policy
    const policyUploadArea = document.getElementById('policyUploadArea');
    const policyFileInput = document.getElementById('policyFileInput');
    
    policyUploadArea.addEventListener('click', () => policyFileInput.click());
    policyUploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        policyUploadArea.classList.add('active');
    });
    policyUploadArea.addEventListener('dragleave', () => {
        policyUploadArea.classList.remove('active');
    });
    policyUploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        policyUploadArea.classList.remove('active');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            policyFileInput.files = files;
            handlePolicyFileSelect({ target: { files: files } });
        }
    });
    
    policyFileInput.addEventListener('change', handlePolicyFileSelect);
    document.getElementById('uploadPolicyBtn').addEventListener('click', uploadPolicy);
    
    // Folder View
    document.getElementById('docFileInput').addEventListener('change', uploadDocument);
    document.getElementById('analyzeBtn').addEventListener('click', generateAnalysis);
    document.getElementById('askBtn').addEventListener('click', askQuestion);
    document.getElementById('questionInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') askQuestion();
    });
    
    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(tab.dataset.tab + 'Tab').classList.add('active');
        });
    });
}

// ==================== VIEW MANAGEMENT ====================

function showView(viewName) {
    console.log('Switching to view:', viewName);
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    
    if (viewName === 'dashboard') {
        document.getElementById('dashboardView').classList.add('active');
        initDashboard();
    } else if (viewName === 'uploadPolicy') {
        document.getElementById('uploadPolicyView').classList.add('active');
        resetUploadForm();
    } else if (viewName === 'folder') {
        document.getElementById('folderView').classList.add('active');
        loadFolderDetails();
    }
}

function resetUploadForm() {
    document.getElementById('folderName').value = '';
    document.getElementById('policyFileInput').value = '';
    document.getElementById('uploadPolicyBtn').disabled = true;
    document.getElementById('policyValidationResult').style.display = 'none';
    document.getElementById('policyUploadArea').classList.remove('active');
    document.querySelector('#policyUploadArea p').textContent = 'Click to upload or drag and drop';
    document.querySelector('#policyUploadArea span').textContent = 'PDF, JPG, PNG (Max 16MB)';
    policyFile = null;
}

// ==================== DASHBOARD ====================

async function initDashboard() {
    console.log('Loading dashboard...');
    await loadDashboardStats();
    await loadFolders();
}

async function loadDashboardStats() {
    try {
        const response = await fetch(`${API_BASE}/dashboard`);
        const stats = await response.json();
        
        console.log('Dashboard stats:', stats);
        
        document.getElementById('totalCount').textContent = stats.total;
        document.getElementById('validCount').textContent = stats.valid;
        document.getElementById('ongoingCount').textContent = stats.ongoing;
        document.getElementById('completedCount').textContent = stats.completed;
        document.getElementById('fraudCount').textContent = stats.fraud;
    } catch (error) {
        console.error('Error loading stats:', error);
        showNotification('Failed to load dashboard statistics', 'error');
    }
}

async function loadFolders() {
    try {
        const response = await fetch(`${API_BASE}/folders`);
        const folders = await response.json();
        
        console.log(`Loaded ${folders.length} folders`);
        
        const container = document.getElementById('foldersList');
        
        if (folders.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg class="icon-xl" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                    </svg>
                    <p>No policies yet. Click "Create New Policy" to get started.</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = folders.map(folder => `
            <div class="folder-card" onclick="openFolder(${folder.id})">
                <div class="folder-card-header">
                    <div>
                        <div class="folder-title">${escapeHtml(folder.folder_name)}</div>
                        <div class="folder-meta">
                            <span>${escapeHtml(folder.company_name || 'Unknown Company')}</span>
                            <span>•</span>
                            <span>${folder.document_count} document${folder.document_count !== 1 ? 's' : ''}</span>
                        </div>
                    </div>
                    <span class="status-badge status-${folder.status}">${folder.status.toUpperCase()}</span>
                </div>
                <div class="folder-card-body">
                    <div class="folder-info">
                        <small>Policy: ${escapeHtml(folder.policy_number || 'N/A')}</small>
                        <small>Coverage: ${escapeHtml(folder.coverage_amount || 'N/A')}</small>
                    </div>
                </div>
                <div class="folder-actions">
                    <div class="completion-badge">${folder.completion_percentage}% Complete</div>
                    <button class="btn-danger btn-icon" onclick="event.stopPropagation(); deleteFolder(${folder.id})" title="Delete folder">
                        <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
                        </svg>
                    </button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading folders:', error);
        showNotification('Failed to load folders', 'error');
    }
}

function openFolder(folderId) {
    console.log('Opening folder:', folderId);
    currentFolderId = folderId;
    showView('folder');
}

async function deleteFolder(folderId) {
    if (!confirm('Delete this folder and all its documents? This action cannot be undone.')) return;
    
    try {
        console.log('Deleting folder:', folderId);
        const response = await fetch(`${API_BASE}/folders/${folderId}`, { method: 'DELETE' });
        
        if (response.ok) {
            showNotification('Folder deleted successfully', 'success');
            loadFolders();
            loadDashboardStats();
        } else {
            showNotification('Failed to delete folder', 'error');
        }
    } catch (error) {
        console.error('Error deleting folder:', error);
        showNotification('Failed to delete folder', 'error');
    }
}

// ==================== UPLOAD POLICY ====================

function handlePolicyFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;
    
    console.log('Policy file selected:', file.name, file.size);
    
    // Check file size
    if (file.size > 16 * 1024 * 1024) {
        showNotification('File too large. Maximum size is 16MB', 'error');
        return;
    }
    
    // Check file type
    const allowedTypes = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png'];
    if (!allowedTypes.includes(file.type)) {
        showNotification('Invalid file type. Please upload PDF, JPG, or PNG', 'error');
        return;
    }
    
    policyFile = file;
    document.getElementById('policyUploadArea').classList.add('active');
    document.getElementById('uploadPolicyBtn').disabled = false;
    
    const uploadArea = document.getElementById('policyUploadArea');
    uploadArea.querySelector('p').textContent = file.name;
    uploadArea.querySelector('span').textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
}

async function uploadPolicy() {
    const folderName = document.getElementById('folderName').value.trim();
    
    if (!folderName) {
        showNotification('Please enter a folder name', 'error');
        document.getElementById('folderName').focus();
        return;
    }
    
    if (!policyFile) {
        showNotification('Please select a policy document', 'error');
        return;
    }
    
    const btn = document.getElementById('uploadPolicyBtn');
    const btnText = document.getElementById('uploadBtnText');
    const spinner = document.getElementById('uploadSpinner');
    
    btn.disabled = true;
    spinner.style.display = 'block';
    btnText.textContent = 'Validating & Extracting...';
    
    const formData = new FormData();
    formData.append('file', policyFile);
    formData.append('folder_name', folderName);
    
    try {
        console.log('Uploading policy...');
        const response = await fetch(`${API_BASE}/upload-policy`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            console.log('Policy uploaded successfully:', result);
            showResult('success', '✓ Policy validated successfully! Redirecting to folder...');
            showNotification('Policy uploaded and validated!', 'success');
            
            setTimeout(() => {
                currentFolderId = result.id;
                showView('folder');
            }, 1500);
        } else {
            console.error('Policy upload failed:', result.error);
            showResult('error', '✗ ' + (result.error || 'Invalid policy document'));
            btn.disabled = false;
        }
    } catch (error) {
        console.error('Upload error:', error);
        showResult('error', '✗ Upload failed. Please check your connection and try again.');
        btn.disabled = false;
    } finally {
        spinner.style.display = 'none';
        btnText.textContent = 'Upload & Validate Policy';
    }
}

function showResult(type, message) {
    const resultBox = document.getElementById('policyValidationResult');
    resultBox.className = `result-box ${type}`;
    resultBox.textContent = message;
    resultBox.style.display = 'block';
}

// ==================== FOLDER VIEW ====================

async function loadFolderDetails() {
    if (!currentFolderId) {
        console.error('No folder ID set');
        return;
    }
    
    try {
        console.log('Loading folder details:', currentFolderId);
        
        // Load folder info
        const folderResponse = await fetch(`${API_BASE}/folders/${currentFolderId}`);
        const folder = await folderResponse.json();
        
        console.log('Folder details:', folder);
        
        // Update header
        document.getElementById('folderTitle').textContent = folder.folder_name;
        document.getElementById('folderCompany').textContent = folder.company_name;
        document.getElementById('folderPolicy').textContent = `Policy: ${folder.policy_number}`;
        document.getElementById('folderCompletion').textContent = `${folder.completion_percentage}%`;
        
        const statusBadge = document.getElementById('folderStatus');
        statusBadge.textContent = folder.status.toUpperCase();
        statusBadge.className = `status-badge status-${folder.status}`;
        
        // Update policy summary
        document.getElementById('policySummary').textContent = folder.policy_summary;
        document.getElementById('policyCoverage').textContent = folder.coverage_amount;
        document.getElementById('policyExpiry').textContent = folder.expiry_date;
        
        const exclusionsList = document.getElementById('policyExclusions');
        exclusionsList.innerHTML = folder.exclusions.map(ex => `<li>${escapeHtml(ex)}</li>`).join('');
        
        // Disable uploads if 100% complete
        const uploadLabel = document.getElementById('uploadDocLabel');
        if (folder.completion_percentage >= 100) {
            uploadLabel.style.display = 'none';
            showNotification('Folder is 100% complete! Upload disabled.', 'info');
        } else {
            uploadLabel.style.display = 'flex';
        }
        
        // Load documents
        await loadDocuments();
        
        // Load analysis if exists
        await loadAnalysis();
        
        // Load Q&A history
        await loadQnA();
        
    } catch (error) {
        console.error('Error loading folder:', error);
        showNotification('Failed to load folder details', 'error');
    }
}

async function loadDocuments() {
    try {
        const response = await fetch(`${API_BASE}/folders/${currentFolderId}/documents`);
        const documents = await response.json();
        
        console.log(`Loaded ${documents.length} documents`);
        
        const container = document.getElementById('documentsList');
        
        if (documents.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg class="icon-xl" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                    </svg>
                    <p>No documents uploaded yet. Upload bills, prescriptions, and medical reports.</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = documents.map(doc => {
            const completenessClass = doc.completeness >= 70 ? 'high' : doc.completeness >= 40 ? 'medium' : 'low';
            const completenessColor = doc.completeness >= 70 ? 'var(--success)' : doc.completeness >= 40 ? 'var(--warning)' : 'var(--danger)';
            
            return `
                <div class="document-item">
                    <div class="document-header">
                        <div class="document-info">
                            <h4>${escapeHtml(doc.filename)}</h4>
                            <div class="document-meta">
                                <span class="doc-type">${doc.document_type}</span>
                                ${doc.amount > 0 ? `<span>₹${doc.amount.toLocaleString('en-IN')}</span>` : ''}
                                <span>${new Date(doc.uploaded_at).toLocaleDateString()}</span>
                                ${doc.is_duplicate ? '<span style="color: var(--danger)">⚠️ DUPLICATE</span>' : ''}
                            </div>
                            ${doc.summary ? `<div class="document-summary">${escapeHtml(doc.summary)}</div>` : ''}
                        </div>
                        <button class="btn-danger btn-icon" onclick="deleteDocument(${doc.id})" title="Delete document">
                            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
                            </svg>
                        </button>
                    </div>
                    <div class="completeness-bar">
                        <div class="progress-bar">
                            <div class="progress-fill ${completenessClass}" style="width: ${doc.completeness}%"></div>
                        </div>
                        <small style="color: ${completenessColor}">${doc.completeness}% Complete</small>
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading documents:', error);
        showNotification('Failed to load documents', 'error');
    }
}

async function uploadDocument(e) {
    const files = e.target.files;
    if (files.length === 0) return;
    
    let totalSize = 0;
    const formData = new FormData();
    const validFiles = [];
    const rejectedFiles = [];
    
    // Validate all files first
    for (const file of files) {
        if (file.size > 16 * 1024 * 1024) {
            rejectedFiles.push({name: file.name, reason: 'Too large (Max 16MB)'});
            continue;
        }
        
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
        if (!allowedTypes.includes(file.type)) {
            rejectedFiles.push({name: file.name, reason: 'Invalid type'});
            continue;
        }
        
        formData.append('files', file);
        validFiles.push(file.name);
        totalSize += file.size;
    }
    
    if (validFiles.length === 0) {
        showNotification('No valid files to upload', 'error');
        e.target.value = '';
        return;
    }
    
    if (rejectedFiles.length > 0) {
        const rejectedMsg = rejectedFiles.map(f => `${f.name}: ${f.reason}`).join('\n');
        showNotification(`Some files rejected:\n${rejectedMsg}`, 'warning');
    }
    
    console.log(`Uploading ${validFiles.length} documents... Total: ${(totalSize / 1024 / 1024).toFixed(2)} MB`);
    
    const btn = document.getElementById('uploadDocLabel');
    const originalContent = btn.innerHTML;
    btn.innerHTML = `<div class="spinner"></div> Uploading ${validFiles.length} file(s)...`;
    btn.style.pointerEvents = 'none';
    
    try {
        const response = await fetch(`${API_BASE}/folders/${currentFolderId}/upload`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            const successCount = result.total_uploaded || result.uploaded?.length || 0;
            const failCount = result.total_failed || result.failed?.length || 0;
            
            let message = `${successCount} document(s) uploaded successfully!`;
            if (failCount > 0) {
                message += ` (${failCount} failed)`;
                console.log('Failed uploads:', result.failed);
            }
            
            showNotification(message, successCount > 0 ? 'success' : 'warning');
            
            await loadFolderDetails();
            await loadDashboardStats();
        } else {
            showNotification(result.error || 'Upload failed', 'error');
        }
    } catch (error) {
        console.error('Upload error:', error);
        showNotification('Upload failed. Please try again.', 'error');
    } finally {
        btn.innerHTML = originalContent;
        btn.style.pointerEvents = 'auto';
        e.target.value = '';
    }
}

async function deleteDocument(docId) {
    if (!confirm('Delete this document?')) return;
    
    try {
        console.log('Deleting document:', docId);
        const response = await fetch(`${API_BASE}/documents/${docId}`, { method: 'DELETE' });
        
        if (response.ok) {
            showNotification('Document deleted', 'success');
            await loadFolderDetails();
            await loadDocuments();
        } else {
            showNotification('Failed to delete document', 'error');
        }
    } catch (error) {
        console.error('Error deleting document:', error);
        showNotification('Failed to delete document', 'error');
    }
}

// ==================== ANALYSIS ====================

async function generateAnalysis() {
    const btn = document.getElementById('analyzeBtn');
    const originalContent = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Analyzing...';
    
    document.getElementById('analysisContent').innerHTML = `
        <div class="empty-state">
            <div class="spinner" style="width: 48px; height: 48px; border-width: 4px; border-color: var(--primary); border-top-color: transparent; margin: 0 auto 1rem;"></div>
            <p>AI is analyzing your documents and policy...<br>This may take up to a minute.</p>
        </div>
    `;
    
    // Switch to analysis tab
    document.querySelector('[data-tab="analysis"]').click();
    
    try {
        console.log('Generating analysis...');
        const response = await fetch(`${API_BASE}/folders/${currentFolderId}/analyze`, {
            method: 'POST'
        });
        
        const analysis = await response.json();
        console.log('Analysis generated:', analysis);
        
        displayAnalysis(analysis);
        showNotification('Analysis completed!', 'success');
        
    } catch (error) {
        console.error('Error generating analysis:', error);
        document.getElementById('analysisContent').innerHTML = `
            <div class="empty-state">
                <p style="color: var(--danger)">Analysis failed. Please try again.</p>
            </div>
        `;
        showNotification('Analysis failed', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalContent;
    }
}

async function loadAnalysis() {
    try {
        const response = await fetch(`${API_BASE}/folders/${currentFolderId}/analysis`);
        if (response.ok) {
            const analysis = await response.json();
            console.log('Loaded existing analysis');
            displayAnalysis(analysis);
        }
    } catch (error) {
        console.log('No existing analysis found');
    }
}

function displayAnalysis(analysis) {
    let html = '<h3>📊 Comprehensive Claim Analysis</h3>';
    
    // Financial Stats
    html += `
        <div class="analysis-grid">
            <div class="analysis-stat stat-blue">
                <h4>Total Bill Amount</h4>
                <p>₹${analysis.total_bill_amount.toLocaleString('en-IN')}</p>
            </div>
            <div class="analysis-stat stat-green">
                <h4>Covered Amount</h4>
                <p>₹${analysis.covered_amount.toLocaleString('en-IN')}</p>
            </div>
            <div class="analysis-stat stat-red">
                <h4>You Pay</h4>
                <p>₹${analysis.user_pays.toLocaleString('en-IN')}</p>
            </div>
        </div>
    `;
    
    // Fraud Warnings
    if (analysis.fraud_warnings.length > 0) {
        html += `
            <div class="alert alert-danger">
                <h4 style="margin-bottom: 0.5rem;">⚠️ Fraud Warnings</h4>
                <ul style="margin: 0.5rem 0 0 1.5rem;">
                    ${analysis.fraud_warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
                </ul>
            </div>
        `;
    }
    
    // Missing Documents
    if (analysis.missing_documents.length > 0) {
        html += `
            <div class="alert alert-warning">
                <h4 style="margin-bottom: 0.5rem;">📋 Missing Documents</h4>
                <ul style="margin: 0.5rem 0 0 1.5rem;">
                    ${analysis.missing_documents.map(d => `<li>${escapeHtml(d)}</li>`).join('')}
                </ul>
            </div>
        `;
    }
    
    // Exclusions Found
    if (analysis.exclusions_found.length > 0) {
        html += `
            <div class="alert alert-warning">
                <h4 style="margin-bottom: 0.5rem;">🚫 Exclusions Detected</h4>
                <ul style="margin: 0.5rem 0 0 1.5rem;">
                    ${analysis.exclusions_found.map(e => `<li>${escapeHtml(e)}</li>`).join('')}
                </ul>
            </div>
        `;
    }
    
    // Summary
    html += `
        <div style="padding: 1.5rem; background: var(--bg); border-radius: 8px; margin-bottom: 1.5rem;">
            <h4>📝 Summary</h4>
            <p style="margin-top: 0.5rem; line-height: 1.6;">${escapeHtml(analysis.summary)}</p>
        </div>
    `;
    
    // Checklist
    if (analysis.checklist.length > 0) {
        html += `
            <div style="margin-bottom: 1.5rem;">
                <h4>✅ Document Checklist</h4>
                <div style="margin-top: 0.5rem;">
                    ${analysis.checklist.map(item => `
                        <div class="checklist-item">
                            <div class="checkbox ${item.completed ? 'checked' : ''}">
                                ${item.completed ? '✓' : ''}
                            </div>
                            <span>${escapeHtml(item.item)}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    // Claim Guide
    if (analysis.claim_guide.length > 0) {
        html += `
            <div class="claim-guide">
                <h4>📝 Step-by-Step Claim Guide</h4>
                <ol>
                    ${analysis.claim_guide.map(step => `<li>${escapeHtml(step)}</li>`).join('')}
                </ol>
            </div>
        `;
    }
    
    document.getElementById('analysisContent').innerHTML = html;
}

// ==================== Q&A ====================

async function loadQnA() {
    try {
        const response = await fetch(`${API_BASE}/folders/${currentFolderId}/qna`);
        const qnas = await response.json();
        
        const container = document.getElementById('qnaHistory');
        
        if (qnas.length === 0) {
            container.innerHTML = '<p style="color: var(--text-light); text-align: center; padding: 2rem;">No questions asked yet. Ask a question about your policy!</p>';
            return;
        }
        
        container.innerHTML = qnas.map(qna => `
            <div class="qna-item">
                <div class="qna-question"><strong>Q:</strong> ${escapeHtml(qna.question)}</div>
                <div class="qna-answer"><strong>A:</strong> ${escapeHtml(qna.answer)}</div>
                <div class="qna-time">${new Date(qna.created_at).toLocaleString()}</div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading Q&A:', error);
    }
}

async function askQuestion() {
    const input = document.getElementById('questionInput');
    const question = input.value.trim();
    
    if (!question) {
        showNotification('Please enter a question', 'error');
        return;
    }
    
    const btn = document.getElementById('askBtn');
    const originalContent = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div>';
    
    try {
        console.log('Asking question:', question);
        const response = await fetch(`${API_BASE}/folders/${currentFolderId}/qna`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question })
        });
        
        if (response.ok) {
            console.log('Answer received');
            await loadQnA();
            input.value = '';
            showNotification('Answer generated!', 'success');
        } else {
            showNotification('Failed to get answer', 'error');
        }
    } catch (error) {
        console.error('Q&A error:', error);
        showNotification('Failed to get answer. Please try again.', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = originalContent;
    }
}

// ==================== UTILITY FUNCTIONS ====================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // Add to page
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => notification.classList.add('show'), 100);
    
    // Remove after 3 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add notification styles dynamically
const notificationStyles = document.createElement('style');
notificationStyles.textContent = `
    .notification {
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        box-shadow: var(--shadow-lg);
        z-index: 1000;
        opacity: 0;
        transform: translateY(-20px);
        transition: all 0.3s ease;
    }
    .notification.show {
        opacity: 1;
        transform: translateY(0);
    }
    .notification-success {
        background: var(--success);
        color: white;
    }
    .notification-error {
        background: var(--danger);
        color: white;
    }
    .notification-info {
        background: var(--primary);
        color: white;
    }
`;
document.head.appendChild(notificationStyles);