import os
import time
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from redis import Redis


class CrawlUtil:
    r = Redis(host='localhost', port=6379, db=0)

    def __init__(self, client, vector_storage_id, progress_text) -> None:
        self.client: OpenAI = client
        self.vector_storage_id = vector_storage_id
        self.progress_text = progress_text

    def fetch_html(self, url):
        try:
            res = requests.get(url)
            if res.status_code == 200:
                return res.text
            else:
                return None
        except requests.RequestException as e:
            print(f"Request failed: {e}")
            return None

    def parse_html_for_links(self, base_url, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        links = set()
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.startswith('/'):
                href = urljoin(base_url, href)
            elif not urlparse(href).netloc:
                href = urljoin(base_url, href)
            if base_url in href:
                links.add(href)
        return links

    def crawl_website(self, base_url, my_bar):
        visited = set()
        to_visit = [base_url]
        to_links = []
        all_pages_content = []
        progress_each = 0
        progress_total = 0

        while to_visit:
            current_url = to_visit.pop(0)
            if current_url not in to_links and current_url != base_url:
                break
            if current_url not in visited:
                html_content = self.fetch_html(current_url)
                if html_content:
                    all_pages_content.append((current_url, html_content))
                    links = self.parse_html_for_links(base_url, html_content)
                    to_visit.extend(links - visited)
                    if current_url == base_url:
                        to_links = set(links)
                        if to_links:
                            progress_each = 1 / len(to_links)
                        else:
                            progress_each = 0.01  # Small value to ensure progress updates

                progress_total += progress_each
                if progress_total <= 1.0:
                    my_bar.progress(progress_total, text=self.progress_text)
                else:
                    my_bar.progress(1.0, text=self.progress_text)  # Ensure it reaches 100%

                visited.add(current_url)

        return all_pages_content

    def get_website_data(self, base_url, my_bar):
        all_pages_content = self.crawl_website(base_url, my_bar)
        all_data = ''
        for url, content in all_pages_content:
            soup = BeautifulSoup(content, 'html.parser')
            all_data += soup.prettify()

        return all_data

    def website_crawler(self, url, my_bar):
        base_url = url
        data = self.get_website_data(base_url, my_bar)

        if file_id := self.r.get(url):
            self.r.zadd("vs_files", {file_id: int(time.time())})
            return

        # Uploading file into vector database
        file_name = urlparse(base_url).netloc + ".txt"
        os.makedirs('data', exist_ok=True)
        with open('data/' + file_name, "w") as text_file:
            text_file.write(data)

        file_ = self.client.files.create(
            file=open('data/' + file_name, "rb"), purpose="assistants"
        )
        # map url to file id and file id to url
        self.r.set(url, file_.id)
        self.r.set(file_.id, url)

        vector_store_file = self.client.beta.vector_stores.files.create(
            vector_store_id=self.vector_storage_id, file_id=file_.id
        )

        self.r.zadd(
            "vs_files", {vector_store_file.id: int(vector_store_file.created_at)}
        )

    @staticmethod
    def extract_company_from_url(url):
        # Parse the URL
        parsed_url = urlparse(
            url if url.startswith(('http://', 'https://')) else 'http://' + url
        )
        # Get the hostname
        hostname = parsed_url.hostname or url
        # Split the hostname into parts
        parts = hostname.split('.')

        # Handle different TLD structures
        if len(parts) > 2:
            if parts[-2] in ['co', 'com', 'net', 'org', 'gov']:
                # For domains like co.uk, com.au, etc.
                domain = parts[-3]
            else:
                # For regular subdomains
                domain = parts[-2]
        else:
            # For simple domains
            domain = parts[0]

        return domain
