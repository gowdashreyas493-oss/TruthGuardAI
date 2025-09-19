// Truth Guard AI - JavaScript Functionality
class TruthGuardAI {
    constructor() {
        this.currentInputType = 'text';
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadStats();
        this.loadReports();
    }

    bindEvents() {
        document.querySelectorAll('.nav-btn').forEach(btn =>
            btn.addEventListener('click', e => this.switchSection(e.target.dataset.section))
        );

        document.querySelectorAll('.type-btn').forEach(btn =>
            btn.addEventListener('click', e => this.switchInputType(e.target.dataset.type))
        );

        document.getElementById('analyzeBtn').addEventListener('click', () => this.analyzeContent());
        document.getElementById('clearBtn').addEventListener('click', () => this.clearInput());
        document.getElementById('refreshReports').addEventListener('click', () => this.loadReports());

        document.getElementById('inputText').addEventListener('keydown', e => {
            if (e.ctrlKey && e.key === 'Enter') this.analyzeContent();
        });
    }

    switchSection(section) {
        document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelector(`[data-section="${section}"]`).classList.add('active');

        document.querySelectorAll('.content-section').forEach(sec => sec.classList.remove('active'));
        document.getElementById(section).classList.add('active');

        if (section === 'reports') this.loadReports();
        else if (section === 'stats') this.loadStats();
    }

    switchInputType(type) {
        this.currentInputType = type;
        document.querySelectorAll('.type-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelector(`[data-type="${type}"]`).classList.add('active');

        const textarea = document.getElementById('inputText');
        textarea.placeholder = type === 'url'
            ? 'Enter URL to verify (e.g., https://example.com/news-article)'
            : 'Enter text or paste URL to analyze for factual accuracy...';
    }

    clearInput() {
        document.getElementById('inputText').value = '';
        this.resetTruthMeter();
        this.clearResults();
        this.clearSearchResults();
    }

    async analyzeContent() {
        const inputText = document.getElementById('inputText').value.trim();
        if (!inputText) return this.showToast('Please enter some content to analyze', 'error');

        this.showLoading(true);
        try {
            // Map input type to backend keys
            const payload = this.currentInputType === 'url'
                ? { url: inputText }
                : { text: inputText };

            const response = await fetch('/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            if (!response.ok || data.error) throw new Error(data.error || `Status ${response.status}`);

            // Adjusted to match backend keys
            this.displayResults({
                sentiment: { label: data.analysis.label, score: data.analysis.sentiment },
                truth: { label: data.analysis.label, score: 100 - (data.analysis.indicators || 0) * 10 } // optional mapping
            });
            this.displaySearchResults(data.search_results);
            this.updateTruthMeter(100 - (data.analysis.indicators || 0) * 10);
            this.showToast('Analysis completed successfully!', 'success');

        } catch (error) {
            console.error('Analysis error:', error);
            this.showToast(`Analysis failed: ${error.message}`, 'error');
        } finally {
            this.showLoading(false);
        }
    }

    displayResults(data) {
        const resultsContent = document.getElementById('resultsContent');
        resultsContent.innerHTML = `
            <div class="result-item">
                <span class="result-label">Sentiment Analysis</span>
                <span class="result-value sentiment-${data.sentiment.label}">${this.capitalize(data.sentiment.label)} (${(data.sentiment.score*100).toFixed(1)}%)</span>
            </div>
            <div class="result-item">
                <span class="result-label">Truth Assessment</span>
                <span class="result-value truth-${data.truth.label}">${this.capitalize(data.truth.label)}</span>
            </div>
            <div class="result-item">
                <span class="result-label">Confidence Score</span>
                <span class="result-value">${data.truth.score}/100</span>
            </div>
            <div class="result-item">
                <span class="result-label">Analysis Type</span>
                <span class="result-value">${this.capitalize(this.currentInputType)} Analysis</span>
            </div>
        `;
    }

    displaySearchResults(results) {
        const searchResults = document.getElementById('searchResults');
        if (!results || results.length === 0) {
            searchResults.innerHTML = `
                <div class="placeholder-content">
                    <div class="placeholder-icon">🔍</div>
                    <p>No verification sources found</p>
                </div>
            `;
            return;
        }
        searchResults.innerHTML = results.map(result => `
            <div class="search-result">
                <a href="${result.url}" target="_blank" class="search-title">${result.title}</a>
                <div class="search-url">${result.url}</div>
                <div class="search-snippet">${result.snippet}</div>
            </div>
        `).join('');
    }

    updateTruthMeter(score) {
        const rotation = (score/100)*180;
        const needle = document.querySelector('.needle');
        needle.style.transform = `rotate(${rotation}deg)`;
        document.getElementById('truthScore').textContent = score;

        const meter = document.querySelector('.truth-meter');
        meter.classList.remove('glow-red','glow-yellow','glow-green');
        if(score<40) meter.classList.add('glow-red');
        else if(score<70) meter.classList.add('glow-yellow');
        else meter.classList.add('glow-green');
    }

    resetTruthMeter() {
        const needle = document.querySelector('.needle');
        needle.style.transform = 'rotate(0deg)';
        document.getElementById('truthScore').textContent = '--';
        const meter = document.querySelector('.truth-meter');
        meter.classList.remove('glow-red','glow-yellow','glow-green');
    }

    clearResults() {
        document.getElementById('resultsContent').innerHTML = `
            <div class="placeholder-content">
                <div class="placeholder-icon">📊</div>
                <p>Enter content above to see detailed analysis results</p>
            </div>
        `;
    }

    clearSearchResults() {
        document.getElementById('searchResults').innerHTML = `
            <div class="placeholder-content">
                <div class="placeholder-icon">🔗</div>
                <p>Verification sources will appear here after analysis</p>
            </div>
        `;
    }

    async loadReports() {
        try {
            const response = await fetch('/reports');
            const reports = await response.json();
            if (reports.error) throw new Error(reports.error);
            this.displayReports(reports);
        } catch (e) {
            console.error(e);
            this.showToast('Failed to load reports','error');
        }
    }

    displayReports(reports) {
        const reportsList = document.getElementById('reportsList');
        if(!reports || reports.length===0){
            reportsList.innerHTML = `
                <div class="placeholder-content">
                    <div class="placeholder-icon">📄</div>
                    <p>No analysis reports found</p>
                </div>
            `;
            return;
        }
        reportsList.innerHTML = reports.map(r=>`
            <div class="report-item">
                <div class="report-header">
                    <div class="report-text">${r.text || r.input_text}</div>
                    <div class="report-meta">
                        <div>ID: #${r.id}</div>
                        <div>${r.created_at || r.timestamp}</div>
                    </div>
                </div>
            </div>
        `).join('');
    }

    async loadStats() {
        try {
            const response = await fetch('/stats');
            const stats = await response.json();
            if (stats.error) throw new Error(stats.error);
            this.displayStats(stats);
        } catch (e) {
            console.error(e);
            this.showToast('Failed to load statistics','error');
        }
    }

    displayStats(stats){
        document.getElementById('totalReports').textContent = stats.total_reports || 0;
        document.getElementById('realCount').textContent = stats.real_count || 0;
        document.getElementById('suspiciousCount').textContent = stats.suspicious_count || 0;
        document.getElementById('fakeCount').textContent = stats.fake_count || 0;
    }

    showLoading(show){
        const overlay = document.getElementById('loadingOverlay');
        overlay.classList.toggle('active', show);
    }

    showToast(message, type='info'){
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(()=>{
            toast.style.animation='slideOutRight 0.3s forwards';
            setTimeout(()=>{ if(container.contains(toast)) container.removeChild(toast); },300);
        },5000);
    }

    capitalize(str){ return str.charAt(0).toUpperCase() + str.slice(1); }
}

document.addEventListener('DOMContentLoaded', ()=> new TruthGuardAI());

// Glow CSS
const style = document.createElement('style');
style.textContent = `
.glow-red .meter-svg { filter: drop-shadow(0 0 10px #ff4444); }
.glow-yellow .meter-svg { filter: drop-shadow(0 0 10px #ffbb33); }
.glow-green .meter-svg { filter: drop-shadow(0 0 10px #00ff88); }
@keyframes slideOutRight { from {opacity:1; transform:translateX(0);} to {opacity:0; transform:translateX(100%);} }
`;
document.head.appendChild(style);
