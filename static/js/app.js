// CopyDesk Application JavaScript

// Global variables
let socket = null;
let currentEvaluationId = null;
let evaluationHistory = [];
let config = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

function initializeApp() {
    // Initialize Material Design components
    componentHandler.upgradeDom();
    
    // Connect to WebSocket
    connectWebSocket();
    
    // Load configuration
    loadConfiguration();
    
    // Set up event listeners
    setupEventListeners();
    
    // Load evaluation history
    loadEvaluationHistory();
    
    // Show input section by default
    showSection('input');
}

function connectWebSocket() {
    socket = io();
    
    socket.on('connect', function() {
        console.log('Connected to server');
        showNotification('Connected to CopyDesk server');
    });
    
    socket.on('disconnect', function() {
        console.log('Disconnected from server');
        showNotification('Disconnected from server', 'error');
    });
    
    socket.on('evaluation_started', function(data) {
        console.log('Evaluation started:', data);
        updateProgress(0, 'Evaluation started...');
    });
    
    socket.on('progress_update', function(data) {
        console.log('Progress update:', data);
        updateProgress(data.progress, data.message);
    });
    
    socket.on('section_started', function(data) {
        console.log('Section started:', data);
        updateSectionProgress(data.section, 'in_progress', null, false, data.pages);
        updateProgress(data.progress, `Analysing ${data.section} (${data.total_pages} pages)...`);
        addLiveUpdate(`Started analysing: ${data.section} (${data.total_pages} pages)`, 'play_arrow');
    });
    
    socket.on('page_started', function(data) {
        console.log('Page started:', data);
        updateCurrentUrl(data.url);
        updateSectionPageProgress(data.section, data.url, 'started');
        addLiveUpdate(`Checking: ${data.url}`, 'schedule');
    });
    
    socket.on('page_completed', function(data) {
        console.log('Page completed:', data);
        updateSectionPageProgress(data.section, data.url, 'completed', data.score);
        addLiveUpdate(`Completed: ${data.url} (${(data.score * 100).toFixed(1)}%)`, 'check');
    });
    
    socket.on('page_evaluated', function(data) {
        console.log('Page evaluated:', data);
        addLiveUpdate(`Evaluated page: ${data.page}`, 'check_circle');
    });
    
    socket.on('section_warning', function(data) {
        console.log('Section warning:', data);
        addLiveUpdate(`Warning in ${data.section}: ${data.message}`, 'warning');
    });
    
    socket.on('section_completed', function(data) {
        console.log('Section completed:', data);
        updateSectionProgress(data.section, 'completed', data.score, data.warnings);
        const icon = data.warnings ? 'warning' : 'done';
        const statusText = data.warnings ? ' (with warnings)' : '';
        addLiveUpdate(`Completed ${data.section}: ${(data.score * 100).toFixed(1)}%${statusText}`, icon);
    });
    
    socket.on('section_failed', function(data) {
        console.log('Section failed:', data);
        updateSectionProgress(data.section, 'failed', 0);
        addLiveUpdate(`Failed ${data.section}: ${data.error}`, 'error');
    });
    
    socket.on('editor_started', function(data) {
        console.log('Editor synthesis started:', data);
        updateProgress(90, 'Editor synthesizing final report...');
        addLiveUpdate('Editor creating final recommendations...', 'edit');
    });
    
    socket.on('evaluation_completed', function(data) {
        console.log('Evaluation completed:', data);
        currentEvaluationId = data.evaluation_id;
        updateProgress(100, 'Evaluation complete!');
        addLiveUpdate('Evaluation completed successfully!', 'done_all');
        setTimeout(() => {
            displayResults(data);
        }, 1000);
    });
    
    socket.on('evaluation_error', function(data) {
        console.log('Evaluation error:', data);
        showNotification('Evaluation error: ' + data.error, 'error');
        updateProgress(0, 'Error: ' + data.error);
        document.getElementById('cancel-button').textContent = 'Back';
    });
}

async function loadConfiguration() {
    try {
        const response = await fetch('/api/config');
        config = await response.json();
        
        // Populate section checkboxes
        const container = document.getElementById('section-checkboxes');
        container.innerHTML = '';
        
        config.sections.forEach((section, index) => {
            const checkboxId = `section-${index}`;
            const html = `
                <label class="mdl-checkbox mdl-js-checkbox mdl-js-ripple-effect" for="${checkboxId}">
                    <input type="checkbox" id="${checkboxId}" class="mdl-checkbox__input" 
                           value="${section.name}" checked>
                    <span class="mdl-checkbox__label">${section.name} (${section.pages.length} pages)</span>
                </label>
            `;
            container.innerHTML += html;
        });
        
        componentHandler.upgradeDom();
    } catch (error) {
        console.error('Failed to load configuration:', error);
        showNotification('Failed to load configuration', 'error');
    }
}

function setupEventListeners() {
    // Text input word counter
    const textInput = document.getElementById('input-text');
    textInput.addEventListener('input', function() {
        const text = textInput.value;
        const words = text.trim().split(/\s+/).filter(word => word.length > 0).length;
        const chars = text.length;
        
        document.getElementById('word-count').textContent = words;
        document.getElementById('char-count').textContent = chars;
    });
}

async function startEvaluation() {
    const textInput = document.getElementById('input-text');
    const text = textInput.value.trim();
    
    if (!text) {
        showNotification('Please enter some text to evaluate');
        return;
    }
    
    // Get selected sections
    const selectedSections = [];
    document.querySelectorAll('#section-checkboxes input[type="checkbox"]:checked').forEach(checkbox => {
        selectedSections.push(checkbox.value);
    });
    
    if (selectedSections.length === 0) {
        showNotification('Please select at least one evaluation section');
        return;
    }
    
    // Show loading
    showLoading(true);
    
    try {
        // Start evaluation
        const response = await fetch('/api/evaluate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text: text,
                options: {
                    sections: selectedSections
                }
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showNotification('Error: ' + data.error, 'error');
            showLoading(false);
            return;
        }
        
        currentEvaluationId = data.evaluation_id;
        
        // Join evaluation room for updates
        socket.emit('join_evaluation', { evaluation_id: currentEvaluationId });
        
        // Show progress section
        showSection('progress');
        initializeProgressSection(selectedSections);
        
    } catch (error) {
        console.error('Failed to start evaluation:', error);
        showNotification('Failed to start evaluation', 'error');
    } finally {
        showLoading(false);
    }
}

function initializeProgressSection(sections) {
    // Clear previous progress
    document.getElementById('section-progress-items').innerHTML = '';
    document.getElementById('live-updates-list').innerHTML = '';
    
    // Create section progress items
    sections.forEach(section => {
        const item = document.createElement('div');
        item.className = 'section-progress-item';
        item.id = `section-progress-${section.replace(/\s+/g, '-')}`;
        item.innerHTML = `
            <span class="section-name">${section}</span>
            <div class="section-status">
                <span class="status-icon material-icons">pending</span>
                <span class="section-score" style="display: none;"></span>
            </div>
            <i class="material-icons section-expand-icon" style="display: none;">expand_more</i>
        `;
        
        // Add click handler for expansion
        item.addEventListener('click', () => {
            const pages = item.getAttribute('data-pages');
            if (pages && item.classList.contains('clickable')) {
                const expandedView = document.getElementById(`expanded-${section.replace(/\s+/g, '-')}`);
                if (expandedView && expandedView.style.display !== 'none') {
                    hideSectionDetails(section);
                } else {
                    showSectionDetails(section);
                }
            }
        });
        
        document.getElementById('section-progress-items').appendChild(item);
    });
    
    // Reset progress bar
    updateProgress(0, 'Initialising evaluation...');
}

function updateProgress(percentage, status) {
    const progressBar = document.getElementById('overall-progress');
    const statusText = document.getElementById('progress-status');
    
    if (progressBar) {
        progressBar.MaterialProgress.setProgress(percentage);
    }
    
    if (statusText) {
        statusText.textContent = status;
    }
}

function updateCurrentUrl(url) {
    const currentUrlElement = document.getElementById('current-url');
    if (currentUrlElement) {
        currentUrlElement.textContent = url;
        currentUrlElement.href = url;
        currentUrlElement.style.display = 'inline';
    }
}

function updateSectionProgress(sectionName, status, score, hasWarnings = false, pages = null) {
    const itemId = `section-progress-${sectionName.replace(/\s+/g, '-')}`;
    const item = document.getElementById(itemId);
    
    if (!item) return;
    
    const statusIcon = item.querySelector('.status-icon');
    const scoreElement = item.querySelector('.section-score');
    
    // Store pages data for the expandable view
    if (pages) {
        item.setAttribute('data-pages', JSON.stringify(pages));
        item.classList.add('clickable');
        const expandIcon = item.querySelector('.section-expand-icon');
        if (expandIcon) {
            expandIcon.style.display = 'block';
        }
    }
    
    if (status === 'in_progress') {
        item.classList.add('active');
        statusIcon.textContent = 'autorenew';
        statusIcon.style.color = '#2196f3';
    } else if (status === 'completed') {
        item.classList.remove('active');
        item.classList.add('completed');
        
        if (hasWarnings) {
            statusIcon.textContent = 'warning';
            statusIcon.style.color = '#ff9800';
            item.style.borderLeftColor = '#ff9800';
        } else {
            statusIcon.textContent = 'check_circle';
            statusIcon.style.color = '#4caf50';
        }
        
        if (score !== null && scoreElement) {
            scoreElement.textContent = `${(score * 100).toFixed(1)}%`;
            scoreElement.style.display = 'inline-block';
        }
    } else if (status === 'failed') {
        item.classList.remove('active');
        item.classList.add('failed');
        item.style.borderLeftColor = '#f44336';
        statusIcon.textContent = 'error';
        statusIcon.style.color = '#f44336';
        
        if (scoreElement) {
            scoreElement.textContent = 'Failed';
            scoreElement.style.display = 'inline-block';
            scoreElement.style.backgroundColor = '#ffebee';
            scoreElement.style.color = '#f44336';
        }
    }
}

function addLiveUpdate(message, icon = 'info') {
    const updatesList = document.getElementById('live-updates-list');
    const now = new Date();
    const time = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    const update = document.createElement('div');
    update.className = 'update-item';
    update.innerHTML = `
        <span class="update-time">${time}</span>
        <span class="update-icon material-icons">${icon}</span>
        <span class="update-message">${message}</span>
    `;
    
    updatesList.insertBefore(update, updatesList.firstChild);
    
    // Keep only last 20 updates
    while (updatesList.children.length > 20) {
        updatesList.removeChild(updatesList.lastChild);
    }
}

function displayResults(data) {
    const report = data.report;
    const markdown = data.markdown;
    
    // Update score
    const score = Math.round(report.score * 100);
    document.getElementById('final-score').textContent = score;
    
    // Create score chart
    createScoreChart(score);
    
    // Update statistics
    const issues = report.issues || [];
    let critical = 0, high = 0, medium = 0, low = 0, info = 0;
    
    issues.forEach(issue => {
        const severity = issue.severity.name;
        if (severity === 'CRITICAL') critical++;
        else if (severity === 'HIGH') high++;
        else if (severity === 'MEDIUM') medium++;
        else if (severity === 'LOW') low++;
        else info++;
    });
    
    document.getElementById('total-issues').textContent = issues.length;
    document.getElementById('critical-issues').textContent = critical + high;
    document.getElementById('warning-issues').textContent = medium;
    document.getElementById('info-issues').textContent = low + info;
    
    // Display recommendations
    displayRecommendations(issues.slice(0, 5));
    
    // Display all issues
    displayIssues(issues);
    
    // Display artifacts and debug info
    displayArtifacts(report);
    
    // Display markdown report
    displayMarkdownReport(markdown);
    
    // Show results section
    showSection('results');
    
    // Update history
    loadEvaluationHistory();
}

function createScoreChart(score) {
    const ctx = document.getElementById('score-chart').getContext('2d');
    
    // Destroy existing chart if it exists
    if (window.scoreChart) {
        window.scoreChart.destroy();
    }
    
    // Determine color based on score
    let color = '#4caf50'; // Green
    if (score < 50) color = '#f44336'; // Red
    else if (score < 75) color = '#ff9800'; // Orange
    
    window.scoreChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [score, 100 - score],
                backgroundColor: [color, '#e0e0e0'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: false
                }
            }
        }
    });
}

function displayRecommendations(recommendations) {
    const container = document.getElementById('recommendations-list');
    container.innerHTML = '';
    
    if (recommendations.length === 0) {
        container.innerHTML = '<p>No recommendations available.</p>';
        return;
    }
    
    recommendations.forEach((rec, index) => {
        const severity = rec.severity.name.toLowerCase();
        const item = document.createElement('div');
        item.className = `recommendation-item ${severity}`;
        item.innerHTML = `
            <div class="recommendation-header">
                <span class="recommendation-number">#${index + 1}</span>
                <span class="severity-badge ${severity}">${rec.severity.name}</span>
            </div>
            <div class="recommendation-title">${rec.description.split('.')[0]}</div>
            <div class="recommendation-description">${rec.description}</div>
            ${rec.suggestion ? `<div class="recommendation-action">${rec.suggestion}</div>` : ''}
        `;
        container.appendChild(item);
    });
}

function displayIssues(issues) {
    const container = document.getElementById('issues-list');
    container.innerHTML = '';
    
    if (issues.length === 0) {
        container.innerHTML = '<p>No issues found.</p>';
        return;
    }
    
    // Group issues by section
    const groupedIssues = {};
    issues.forEach(issue => {
        const section = issue.section || 'General';
        if (!groupedIssues[section]) {
            groupedIssues[section] = [];
        }
        groupedIssues[section].push(issue);
    });
    
    // Display grouped issues
    Object.keys(groupedIssues).forEach(section => {
        const sectionDiv = document.createElement('div');
        sectionDiv.innerHTML = `<h4>${section}</h4>`;
        
        groupedIssues[section].forEach(issue => {
            const severity = issue.severity.name.toLowerCase();
            const item = document.createElement('div');
            item.className = `issue-item ${severity}`;
            item.innerHTML = `
                <div class="issue-header">
                    <span class="issue-title">${issue.description}</span>
                    <span class="severity-badge ${severity}">${issue.severity.name}</span>
                </div>
                ${issue.location ? `<div class="issue-location">Location: ${issue.location}</div>` : ''}
                ${issue.suggestion ? `<div class="issue-suggestion">${issue.suggestion}</div>` : ''}
            `;
            sectionDiv.appendChild(item);
        });
        
        container.appendChild(sectionDiv);
    });
}

function displayMarkdownReport(markdown) {
    const container = document.getElementById('markdown-report');
    if (markdown) {
        container.innerHTML = marked.parse(markdown);
    } else {
        container.innerHTML = '<p>No markdown report available.</p>';
    }
}

function displayArtifacts(report) {
    // Display evaluated references
    const refsContainer = document.getElementById('evaluated-references');
    if (refsContainer) {
        refsContainer.innerHTML = '';
        
        // Extract sub-reports (senior evaluator reports)
        const subReports = report.sub_reports || [];
        
        if (subReports.length > 0) {
            const refsList = document.createElement('ul');
            refsList.className = 'mdl-list';
            
            subReports.forEach(subReport => {
                const section = subReport.metadata?.section || 'Unknown Section';
                const score = Math.round((subReport.score || 0) * 100);
                const issueCount = subReport.issues?.length || 0;
                const juniorCount = subReport.metadata?.junior_reports_count || 0;
                
                const item = document.createElement('li');
                item.className = 'mdl-list__item mdl-list__item--three-line';
                item.innerHTML = `
                    <span class="mdl-list__item-primary-content">
                        <i class="material-icons mdl-list__item-avatar">folder</i>
                        <span>${section}</span>
                        <span class="mdl-list__item-text-body">
                            Score: ${score}% | Issues: ${issueCount} | Pages evaluated: ${juniorCount}
                            <br/>
                            ${subReport.summary ? subReport.summary.substring(0, 150) + '...' : 'No summary available'}
                        </span>
                    </span>
                `;
                refsList.appendChild(item);
            });
            
            refsContainer.appendChild(refsList);
        } else {
            refsContainer.innerHTML = '<p>No section reports available.</p>';
        }
    }
    
    // Display section reports detail
    const sectionsContainer = document.getElementById('section-reports');
    if (sectionsContainer) {
        sectionsContainer.innerHTML = '';
        
        const subReports = report.sub_reports || [];
        if (subReports.length > 0) {
            subReports.forEach(subReport => {
                const section = subReport.metadata?.section || 'Unknown';
                const details = document.createElement('details');
                details.className = 'section-report-details';
                details.innerHTML = `
                    <summary>${section} (Score: ${Math.round(subReport.score * 100)}%)</summary>
                    <div class="section-report-content">
                        <p><strong>Summary:</strong> ${subReport.summary || 'No summary'}</p>
                        <p><strong>Issues found:</strong> ${subReport.issues?.length || 0}</p>
                        <p><strong>Pages evaluated:</strong> ${subReport.metadata?.junior_reports_count || 0}</p>
                        ${subReport.metadata?.failed_evaluations > 0 ? 
                            `<p class="warning"><strong>Failed evaluations:</strong> ${subReport.metadata.failed_evaluations}</p>` : ''}
                    </div>
                `;
                sectionsContainer.appendChild(details);
            });
        } else {
            sectionsContainer.innerHTML = '<p>No detailed section reports available.</p>';
        }
    }
    
    // Display debug JSON
    const debugContainer = document.getElementById('debug-json');
    if (debugContainer) {
        debugContainer.textContent = JSON.stringify(report, null, 2);
    }
}

async function loadEvaluationHistory() {
    try {
        const response = await fetch('/api/evaluations');
        const evaluations = await response.json();
        
        const tbody = document.getElementById('history-table-body');
        tbody.innerHTML = '';
        
        evaluations.forEach(eval => {
            const row = document.createElement('tr');
            const date = new Date(eval.start_time).toLocaleString();
            const statusClass = eval.status === 'completed' ? 'completed' : 
                               eval.status === 'running' ? 'running' : 'error';
            
            row.innerHTML = `
                <td class="mdl-data-table__cell--non-numeric">${date}</td>
                <td class="mdl-data-table__cell--non-numeric">
                    <div class="text-preview">${eval.text_preview}</div>
                </td>
                <td>${eval.score ? (eval.score * 100).toFixed(1) + '%' : '-'}</td>
                <td class="mdl-data-table__cell--non-numeric">
                    <span class="status-badge ${statusClass}">${eval.status}</span>
                </td>
                <td class="mdl-data-table__cell--non-numeric">
                    <button class="mdl-button mdl-js-button mdl-button--icon" 
                            onclick="viewEvaluation('${eval.id}')">
                        <i class="material-icons">visibility</i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Failed to load evaluation history:', error);
    }
}

async function viewEvaluation(evalId) {
    try {
        const response = await fetch(`/api/evaluation/${evalId}`);
        const data = await response.json();
        
        if (data.status === 'completed') {
            displayResults({
                report: data.report,
                markdown: data.markdown
            });
        } else {
            showNotification(`Evaluation is ${data.status}`);
        }
    } catch (error) {
        console.error('Failed to load evaluation:', error);
        showNotification('Failed to load evaluation', 'error');
    }
}

function cancelEvaluation() {
    if (currentEvaluationId) {
        socket.emit('leave_evaluation', { evaluation_id: currentEvaluationId });
    }
    showSection('input');
}

function startNewEvaluation() {
    showSection('input');
    document.getElementById('input-text').value = '';
    document.getElementById('word-count').textContent = '0';
    document.getElementById('char-count').textContent = '0';
}

function clearInput() {
    document.getElementById('input-text').value = '';
    document.getElementById('word-count').textContent = '0';
    document.getElementById('char-count').textContent = '0';
    document.getElementById('input-text').parentElement.classList.remove('is-dirty');
}

function exportReport(format) {
    // TODO: Implement export functionality
    showNotification(`Export to ${format.toUpperCase()} coming soon!`);
}

function saveReport() {
    // TODO: Implement save functionality
    showNotification('Save functionality coming soon!');
}

function showSettings() {
    // TODO: Implement settings dialog
    showNotification('Settings coming soon!');
}

function showSection(sectionName) {
    // Hide all sections
    document.querySelectorAll('.content-section').forEach(section => {
        section.style.display = 'none';
    });
    
    // Show requested section
    const section = document.getElementById(`${sectionName}-section`);
    if (section) {
        section.style.display = 'block';
    }
}

function showLoading(show) {
    const spinner = document.getElementById('loading-spinner');
    if (spinner) {
        spinner.style.display = show ? 'block' : 'none';
    }
}

function updateSectionPageProgress(sectionName, url, status, score = null) {
    // Store page progress for display when section is expanded
    const itemId = `section-progress-${sectionName.replace(/\s+/g, '-')}`;
    const item = document.getElementById(itemId);
    if (!item) return;
    
    // Get or create pages progress data
    let pagesProgress = item.getAttribute('data-pages-progress');
    if (!pagesProgress) {
        pagesProgress = {};
    } else {
        pagesProgress = JSON.parse(pagesProgress);
    }
    
    pagesProgress[url] = {
        status: status,
        score: score,
        timestamp: new Date().toISOString()
    };
    
    item.setAttribute('data-pages-progress', JSON.stringify(pagesProgress));
    
    // Update the page count display if section is expanded
    updateExpandedSectionView(sectionName);
}

function updateExpandedSectionView(sectionName) {
    const expandedView = document.getElementById(`expanded-${sectionName.replace(/\s+/g, '-')}`);
    if (expandedView && expandedView.style.display !== 'none') {
        // Refresh the expanded view content
        showSectionDetails(sectionName);
    }
}

function showSectionDetails(sectionName) {
    const itemId = `section-progress-${sectionName.replace(/\s+/g, '-')}`;
    const item = document.getElementById(itemId);
    if (!item) return;
    
    const pages = JSON.parse(item.getAttribute('data-pages') || '[]');
    const pagesProgress = JSON.parse(item.getAttribute('data-pages-progress') || '{}');
    
    let expandedView = document.getElementById(`expanded-${sectionName.replace(/\s+/g, '-')}`);
    if (!expandedView) {
        expandedView = document.createElement('div');
        expandedView.id = `expanded-${sectionName.replace(/\s+/g, '-')}`;
        expandedView.className = 'section-expanded-view';
        item.parentNode.insertBefore(expandedView, item.nextSibling);
    }
    
    let html = `<div class="expanded-content">
        <h5>${sectionName} - Page Details</h5>
        <div class="pages-list">`;
    
    pages.forEach(url => {
        const progress = pagesProgress[url];
        let statusIcon = 'schedule';
        let statusText = 'Pending';
        let statusClass = 'pending';
        
        if (progress) {
            if (progress.status === 'started') {
                statusIcon = 'autorenew';
                statusText = 'Checking...';
                statusClass = 'checking';
            } else if (progress.status === 'completed') {
                statusIcon = 'check_circle';
                statusText = `Complete (${(progress.score * 100).toFixed(1)}%)`;
                statusClass = 'complete';
            }
        }
        
        html += `
            <div class="page-item ${statusClass}">
                <i class="material-icons page-status-icon">${statusIcon}</i>
                <a href="${url}" target="_blank" class="page-url">${url}</a>
                <span class="page-status">${statusText}</span>
            </div>
        `;
    });
    
    html += `</div>
        <button class="mdl-button mdl-js-button" onclick="hideSectionDetails('${sectionName}')">
            <i class="material-icons">expand_less</i> Hide Details
        </button>
    </div>`;
    
    expandedView.innerHTML = html;
    expandedView.style.display = 'block';
    
    // Initialize MDL components
    componentHandler.upgradeDom();
}

function hideSectionDetails(sectionName) {
    const expandedView = document.getElementById(`expanded-${sectionName.replace(/\s+/g, '-')}`);
    if (expandedView) {
        expandedView.style.display = 'none';
    }
}

function showNotification(message, type = 'info') {
    const notification = document.querySelector('#snackbar');
    const data = {
        message: message,
        timeout: 3000
    };
    
    notification.MaterialSnackbar.showSnackbar(data);
}