from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import os, requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote_plus

# NLP libs
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk import pos_tag
from textblob import TextBlob

# SerpAPI
from serpapi import GoogleSearch

# ------------------- Flask + DB -------------------
# Fixed paths for proper Flask structure
app = Flask(
    __name__,
    static_folder="static",      # static folder for CSS/JS
    template_folder="templates"   # templates folder for HTML
)
CORS(app)

# Use PostgreSQL on Render, SQLite locally
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Fix for Render's PostgreSQL URL
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///truthguard.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ------------------- DB Models -------------------
class FakeNewsReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    label = db.Column(db.String(16), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Create database tables
@app.before_first_request
def create_tables():
    try:
        db.create_all()
        print("Database tables created successfully!")
    except Exception as e:
        print(f"Database creation error: {e}")

# ------------------- NLTK setup -------------------
def ensure_nltk():
    nltk_data_path = '/tmp/nltk_data'
    os.makedirs(nltk_data_path, exist_ok=True)
    nltk.data.path.append(nltk_data_path)
    
    for pkg in ['punkt', 'stopwords', 'averaged_perceptron_tagger']:
        try:
            nltk.data.find(pkg if pkg != 'averaged_perceptron_tagger' else f'taggers/{pkg}')
        except LookupError:
            try:
                nltk.download(pkg, download_dir=nltk_data_path)
            except Exception as e:
                print(f"NLTK download failed for {pkg}: {e}")

ensure_nltk()

# ------------------- Content extraction -------------------
def extract_text_from_url(url, max_paragraphs=15):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TruthGuard/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string.strip() if soup.title else url
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")][:max_paragraphs]
        content = " ".join(paragraphs) or title
        if not content:
            meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
            content = meta.get("content", "") if meta else title
        return title, content
    except Exception as e:
        app.logger.warning(f"extract_text_from_url error for {url}: {e}")
        return url, url

# ------------------- NLP analysis -------------------
def analyze_text(text):
    if not text or len(text.strip()) < 10:
        return {"tokens": [], "sentiment": 0.0, "label": "uncertain", "preview": ""}

    try:
        tokens = [t.lower() for t in word_tokenize(text) if t.isalpha()]
        stop = set(stopwords.words("english"))
        tokens = [t for t in tokens if t not in stop]
    except Exception as e:
        # Fallback tokenization if NLTK fails
        tokens = [t.lower() for t in text.split() if t.isalpha()]

    try:
        pos_tag(tokens)
    except Exception:
        pass

    try:
        polarity = TextBlob(text).sentiment.polarity
    except Exception:
        polarity = 0.0

    sensational_words = [
        'click','shocking','unbelievable','hate','secret','miracle','cure',
        'conspiracy','pharma','believe','weird','trick','scientists','baffled',
        'hidden','truth','wake','sheeple','fake','hoax','breaking','news',
        'urgent','alert','warning','scandal','exposed','leaked','bombshell',
        'revolutionary','guaranteed','limited','act','free','money','cancer',
        'theory','deep','state','alternative','facts','zombie','apocalypse'
    ]

    indicator_count = sum(1 for t in tokens if any(w in t for w in sensational_words))
    punct_indicators = (text.count('!') + text.count('?')) // 2
    caps_indicators = 1 if sum(1 for t in text.split() if t.isupper() and len(t) > 3) > 1 else 0
    total_indicators = indicator_count + punct_indicators + caps_indicators

    if total_indicators >= 3 or polarity < -0.25 or polarity > 0.5:
        label = "fake"
    elif total_indicators >= 1 or abs(polarity) > 0.15:
        label = "suspicious"
    else:
        label = "real"

    preview = text.strip()[:300].replace("\n", " ") + ("…" if len(text.strip()) > 300 else "")
    return {"tokens": tokens[:20], "sentiment": round(polarity, 4), "label": label, "preview": preview, "indicators": total_indicators}

# ------------------- Google search -------------------
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "d53af08d64040d65f5bbedbf4f8a738aecec19137d839257f547b1128702e14e")

def google_search_serpapi(query, num=5):
    if not SERPAPI_KEY:
        return []
    try:
        search = GoogleSearch({"q": query, "api_key": SERPAPI_KEY, "num": num})
        results = search.get_dict()
        return [{"title": it.get("title"), "url": it.get("link"), "snippet": it.get("snippet")} 
                for it in results.get("organic_results", [])[:num]]
    except Exception as e:
        app.logger.warning(f"google_search_serpapi error: {e}")
        return []

def google_search_scrape(query, num=5):
    try:
        encoded = quote_plus(query)
        url = f"https://www.google.com/search?q={encoded}&num={num}"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        containers = soup.select('.tF2Cxc') or soup.select('.g') or soup.select('div.yuRUbf')
        results = []
        for g in containers[:num]:
            title_el = g.select_one('h3')
            link_el = g.select_one('a')
            snippet_el = g.select_one('.VwiC3b') or g.select_one('.IsZvec')
            title = title_el.get_text(strip=True) if title_el else None
            link = link_el['href'] if link_el else None
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            if title or link:
                results.append({"title": title or link, "url": link, "snippet": snippet})
        return results
    except Exception as e:
        app.logger.warning(f"google_search_scrape error: {e}")
        return []

def google_search(query, num=5):
    return google_search_serpapi(query, num) or google_search_scrape(query, num)

# ------------------- Helper -------------------
def prepare_query_from_input(raw_input):
    raw_input = raw_input.strip()
    if not raw_input:
        return "", ""
    if raw_input.startswith(("http://", "https://")):
        title, content = extract_text_from_url(raw_input)
        domain = urlparse(raw_input).netloc or ""
        return title or domain or raw_input, content or title or raw_input
    else:
        return raw_input, raw_input

# ------------------- Routes -------------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.get_json(force=True)
        raw = (data.get("url") or data.get("text") or "").strip()
        if not raw:
            return jsonify({"error":"No input provided"}), 400

        search_query, analysis_text = prepare_query_from_input(raw)
        analysis = analyze_text(analysis_text)
        search_results = google_search(search_query, num=6) if search_query else []

        # Adjust label if few corroborations
        if len(search_results) < 3:
            if analysis["label"] == "real":
                analysis["label"] = "suspicious"
            elif analysis["label"] == "uncertain":
                analysis["label"] = "fake"

        # Save to DB
        try:
            rec = FakeNewsReport(text=analysis_text[:2000], label=analysis["label"])
            db.session.add(rec)
            db.session.commit()
        except Exception as e:
            app.logger.warning("DB save failed: %s", e)

        return jsonify({"analysis": analysis, "search_results": search_results})
    except Exception as e:
        app.logger.exception("verify failed")
        return jsonify({"error":"Internal server error", "detail":str(e)}), 500

@app.route('/reports', methods=['GET'])
def reports():
    try:
        items = FakeNewsReport.query.order_by(FakeNewsReport.created_at.desc()).limit(100).all()
        return jsonify([{"id": r.id, "text": r.text, "label": r.label, "created_at": r.created_at.isoformat()} for r in items])
    except Exception as e:
        app.logger.exception("reports failed")
        return jsonify({"error":"failed to fetch reports"}), 500

@app.route('/stats', methods=['GET'])
def stats():
    from sqlalchemy import func
    try:
        total = db.session.query(func.count(FakeNewsReport.id)).scalar() or 0
        real_count = db.session.query(func.count(FakeNewsReport.id)).filter(FakeNewsReport.label=="real").scalar() or 0
        suspicious_count = db.session.query(func.count(FakeNewsReport.id)).filter(FakeNewsReport.label=="suspicious").scalar() or 0
        fake_count = db.session.query(func.count(FakeNewsReport.id)).filter(FakeNewsReport.label=="fake").scalar() or 0
        return jsonify({
            "total_reports": total,
            "real_count": real_count,
            "suspicious_count": suspicious_count,
            "fake_count": fake_count
        })
    except Exception as e:
        app.logger.exception("stats failed")
        return jsonify({"error":"failed to fetch stats"}), 500

@app.route('/top', methods=['GET'])
def top_searches():
    from sqlalchemy import func
    try:
        results = db.session.query(FakeNewsReport.label, func.count(FakeNewsReport.label))\
            .group_by(FakeNewsReport.label).all()
        return jsonify([{"label": r[0], "count": r[1]} for r in results])
    except Exception as e:
        app.logger.exception("top_searches failed")
        return jsonify([]), 500

# Health check endpoint for Render
@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

# ------------------- Run -------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
