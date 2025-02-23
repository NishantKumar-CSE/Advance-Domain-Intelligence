import requests
import ipaddress
import socket
import re
import urllib.parse
from bs4 import BeautifulSoup
import joblib
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import whois  # For WHOIS lookups
import dns.resolver  # For DNS-related scanning


def validate_domain_or_ip(input_string):
    """
    Validate if the input is a valid domain or IP address.

    Args:
        input_string (str): Domain or IP to validate

    Returns:
        tuple: (is_valid, normalized_url)
    """
    # IP validation
    try:
        ipaddress.ip_address(input_string)
        return True, f"http://{input_string}"
    except ValueError:
        pass

    # Domain validation using regex and DNS lookup
    domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    if re.match(domain_pattern, input_string):
        try:
            # Attempt DNS lookup to verify domain
            socket.gethostbyname(input_string)
            return True, f"http://{input_string}"
        except socket.gaierror:
            return False, None

    return False, None


def normalize_url(base_input, url):
    """
    Normalize URLs, converting relative to absolute URLs.

    Args:
        base_input (str): Base domain or URL
        url (str): URL to normalize

    Returns:
        str: Normalized absolute URL
    """
    # Ensure base_input is a full URL
    if not base_input.startswith(('http://', 'https://')):
        base_input = f"http://{base_input}"

    # Handle relative URLs
    return urllib.parse.urljoin(base_input, url)


def load_ml_components():
    """
    Load machine learning components safely.

    Returns:
        tuple: (model, vectorizer, encoder)
    """
    try:
        model = joblib.load('models/url_classification_model.pkl')
        vectorizer = joblib.load('models/vectorizer.pkl')
        encoder = joblib.load('models/label_encoder.pkl')
        return model, vectorizer, encoder
    except FileNotFoundError:
        print("Error: Machine learning model files not found. Please ensure all required .pkl files are present.")
        return None, None, None


def classify_url(url, model, vectorizer, encoder):
    """
    Classify a single URL using the trained model.

    Args:
        url (str): URL to classify
        model: Trained classification model
        vectorizer: URL vectorizer
        encoder: Label encoder

    Returns:
        str: Predicted URL category
    """
    if not all([model, vectorizer, encoder]):
        return "Classification Unavailable"

    try:
        url_vectorized = vectorizer.transform([url])
        prediction = model.predict(url_vectorized)
        predicted_label = encoder.inverse_transform(prediction)[0]
        return predicted_label
    except Exception as e:
        print(f"Classification error for {url}: {e}")
        return "Classification Error"


def advanced_url_analysis(df):
    """
    Perform advanced URL analysis.

    Args:
        df (pd.DataFrame): DataFrame with URL classifications

    Returns:
        dict: Advanced analysis results
    """
    # Longest URLs in each category
    longest_urls = df.loc[df.groupby('Category')['URL'].idxmax()]
    print("\nLongest URLs per Category:")
    print(longest_urls)

    # URL Length Analysis
    df['URL_Length'] = df['URL'].str.len()
    url_length_by_category = df.groupby('Category')['URL_Length'].agg(['mean', 'median', 'max'])
    print("\nURL Length Statistics by Category:")
    print(url_length_by_category)

    # Visualization of URL Lengths
    plt.figure(figsize=(10, 6))
    sns.boxplot(x='Category', y='URL_Length', data=df)
    plt.title('URL Length Distribution by Category')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('static/url_length_boxplot.png')  # Save in static folder
    plt.close()

    # Additional advanced analyses
    analysis_results = {
        'longest_urls': longest_urls,
        'url_length_stats': url_length_by_category,
        'category_domain_breakdown': analyze_domains_by_category(df)
    }

    return analysis_results


def analyze_domains_by_category(df):
    """
    Analyze unique domains within each URL category.

    Args:
        df (pd.DataFrame): DataFrame with URL classifications

    Returns:
        pd.DataFrame: Domain breakdown by category
    """
    # Extract domains from URLs
    df['Domain'] = df['URL'].apply(lambda x: urllib.parse.urlparse(x).netloc)

    # Count unique domains per category
    domain_breakdown = df.groupby('Category')['Domain'].agg([
        ('Total_Domains', 'nunique'),
        ('Domain_List', lambda x: ', '.join(set(x)))
    ])

    print("\nDomain Breakdown by Category:")
    print(domain_breakdown)

    return domain_breakdown


def scrape_and_classify(base_input):
    """
    Comprehensive URL scraping and classification with robust error handling
    and extended scanning capabilities.

    Args:
        base_input (str): Domain, IP, or URL to analyze

    Returns:
        dict: Comprehensive analysis results
    """
    # Validate input
    is_valid, base_url = validate_domain_or_ip(base_input)

    if not is_valid:
        print(f"Invalid domain or IP: {base_input}")
        return None

    # Prepare results dictionary
    analysis_results = {
        'input': base_input,
        'url_classification': None,
        'insights': None
    }

    # Perform existing scraping and classification functionality
    try:
        # Load ML components
        model, vectorizer, encoder = load_ml_components()
        if not model:
            return analysis_results

        # Existing webpage scraping and link classification logic
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()

        # Parse webpage
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract and normalize links
        links = [
            normalize_url(base_url, a['href'])
            for a in soup.find_all('a', href=True)
            if a['href'].startswith(('http', '/'))
        ]

        print(f"Found {len(links)} links. Classifying them...\n")

        # Classify links
        results = []
        for link in links:
            try:
                label = classify_url(link, model, vectorizer, encoder)
                results.append((link, label))
            except Exception as e:
                print(f"Error classifying {link}: {e}")

        # Create DataFrame
        df = pd.DataFrame(results, columns=['URL', 'Category'])

        # Descriptive Statistics
        print("Classification Statistics:")
        category_counts = df['Category'].value_counts()
        print("\nCategory Distribution:")
        print(category_counts)

        # Calculate percentages
        total_links = len(df)
        category_percentages = (category_counts / total_links) * 100

        # Generate insights
        insights = []
        for category, percentage in category_percentages.items():
            if category in ["Phishing", "Malware", "Defacement", "Spam"]:
                insights.append(f"✅ {base_input} shows a high risk of {category.lower()} attacks ({percentage:.1f}%).")
            elif category in ["Benign", "Safe"]:
                insights.append(f"✅ {base_input} has a significant portion of safe links ({percentage:.1f}%).")
            else:
                insights.append(f"✅ {base_input} has {percentage:.1f}% of links categorized as {category.lower()}.")

        # Add overall risk assessment
        malicious_categories = ["Phishing", "Malware", "Defacement", "Spam"]
        malicious_percentage = category_percentages[category_percentages.index.isin(malicious_categories)].sum()
        if malicious_percentage > 50:
            insights.append(f"🚨 {base_input} is highly suspicious, with {malicious_percentage:.1f}% of links classified as malicious.")
        elif malicious_percentage > 20:
            insights.append(f"⚠️ {base_input} shows moderate risk, with {malicious_percentage:.1f}% of links classified as malicious.")
        else:
            insights.append(f"✅ {base_input} appears to be relatively safe, with only {malicious_percentage:.1f}% of links classified as malicious.")

        # Save insights
        analysis_results['insights'] = insights

        # Visualizations
        plt.figure(figsize=(15, 5))

        # Pie Chart
        plt.subplot(1, 2, 1)
        plt.pie(category_counts, labels=category_counts.index, autopct='%1.1f%%')
        plt.title(f'URL Categories for {base_input}')
        plt.savefig('static/url_categories_pie.png')  # Save in static folder

        # Bar Chart
        plt.subplot(1, 2, 2)
        sns.barplot(x=category_counts.index, y=category_counts.values)
        plt.title(f'URL Categories Distribution')
        plt.xlabel('Category')
        plt.ylabel('Number of URLs')
        plt.xticks(rotation=45)
        plt.savefig('static/url_categories_bar.png')  # Save in static folder

        plt.tight_layout()
        plt.close()

        # Perform Advanced Analysis
        advanced_analysis = advanced_url_analysis(df)

        # Save results
        df.to_csv('static/url_classification_results.csv', index=False)  # Save in static folder

        # Update analysis results
        analysis_results['url_classification'] = df

        print("\nResults and visualizations saved.")
        return analysis_results

    except requests.RequestException as e:
        print(f"Network error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

    return analysis_results


def main():
    base_input = input("Enter domain, IP, or URL to analyze: ")
    results = scrape_and_classify(base_input)

    if results:
        print("\nAnalysis Results:")

        # Print URL Classification Results
        if results.get('url_classification') is not None:
            print("\nURL Classification:")
            print(results['url_classification'])

        # Print Insights
        if results.get('insights'):
            print("\nInsights:")
            for insight in results['insights']:
                print(insight)

        print("\nAnalysis complete. Check the generated output files in the 'static' folder.")


if __name__ == "__main__":
    main()