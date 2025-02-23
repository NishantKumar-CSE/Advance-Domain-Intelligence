from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import base64
from io import BytesIO
import requests
from bs4 import BeautifulSoup
import joblib
import re
import socket
import ipaddress
import urllib.parse

app = Flask(__name__)

# Ensure required directories exist
os.makedirs('static', exist_ok=True)
os.makedirs('models', exist_ok=True)


def validate_domain_or_ip(input_string):
    """Validate if input is domain or IP."""
    try:
        ipaddress.ip_address(input_string)
        return True, f"http://{input_string}"
    except ValueError:
        domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        if re.match(domain_pattern, input_string):
            try:
                socket.gethostbyname(input_string)
                return True, f"http://{input_string}"
            except socket.gaierror:
                return False, None
    return False, None


def normalize_url(base_input, url):
    """Normalize URLs to absolute form."""
    if not base_input.startswith(('http://', 'https://')):
        base_input = f"http://{base_input}"
    return urllib.parse.urljoin(base_input, url)


def load_ml_models():
    """Load ML models and components."""
    try:
        model = joblib.load('models/url_classification_model.pkl')
        vectorizer = joblib.load('models/vectorizer.pkl')
        encoder = joblib.load('models/label_encoder.pkl')
        return model, vectorizer, encoder
    except Exception as e:
        print(f"Error loading models: {e}")
        return None, None, None


def save_charts(category_counts):
    """Generate and save analysis charts."""
    # Create and save pie chart
    plt.figure(figsize=(8, 8))
    plt.pie(category_counts.values, labels=category_counts.index, autopct='%1.1f%%')
    plt.title('URL Categories Distribution')
    plt.savefig('static/url_categories_pie.png')
    plt.close()

    # Create and save bar chart
    plt.figure(figsize=(10, 6))
    sns.barplot(x=category_counts.index, y=category_counts.values)
    plt.title('URL Categories Distribution')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('static/url_categories_bar.png')
    plt.close()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        # Validate URL
        is_valid, normalized_url = validate_domain_or_ip(url)
        if not is_valid:
            return jsonify({'error': 'Invalid URL or domain'}), 400

        # Load ML components
        model, vectorizer, encoder = load_ml_models()
        if not all([model, vectorizer, encoder]):
            return jsonify({'error': 'Could not load ML models'}), 500

        # Scrape and analyze URLs
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(normalized_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract and normalize links
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith(('http', '/')):
                full_url = normalize_url(normalized_url, href)
                links.append(full_url)

        # Classify URLs
        results = []
        for link in links:
            try:
                url_vectorized = vectorizer.transform([link])
                prediction = model.predict(url_vectorized)
                category = encoder.inverse_transform(prediction)[0]
                results.append({'URL': link, 'Category': category})
            except Exception as e:
                print(f"Error classifying {link}: {e}")

        # Create DataFrame and generate statistics
        df = pd.DataFrame(results)
        category_counts = df['Category'].value_counts()

        # Generate and save charts
        save_charts(category_counts)

        # Generate insights
        insights = []
        total_urls = len(df)
        for category, count in category_counts.items():
            percentage = (count / total_urls) * 100
            if category.lower() in ['phishing', 'malware', 'spam']:
                insights.append(f"🚨 Found {percentage:.1f}% {category.lower()} URLs")
            elif category.lower() in ['suspicious', 'unknown']:
                insights.append(f"⚠️ {percentage:.1f}% URLs classified as {category.lower()}")
            else:
                insights.append(f"✅ {percentage:.1f}% URLs classified as {category.lower()}")

        # Read charts as base64
        with open('static/url_categories_pie.png', 'rb') as f:
            pie_chart = base64.b64encode(f.read()).decode('utf-8')
        with open('static/url_categories_bar.png', 'rb') as f:
            bar_chart = base64.b64encode(f.read()).decode('utf-8')

        return jsonify({
            'url_classification': results,
            'insights': insights,
            'charts': {
                'pie_chart': pie_chart,
                'bar_chart': bar_chart
            }
        })

    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Error accessing URL: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'Analysis error: {str(e)}'}), 500


if __name__ == "__main__":
    app.run(debug=True)