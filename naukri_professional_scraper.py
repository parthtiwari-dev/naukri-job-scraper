

import requests
import pandas as pd
import json
import csv
import time
import random
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import urljoin
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('naukri_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class JobData:
    """Data structure for job information"""
    job_title: str = ""
    company_name: str = ""
    job_id: str = ""
    job_description: str = ""
    location: str = ""
    job_url: str = ""
    scraped_at: str = ""

class NaukriScraper:
    """
    Professional Naukri.com job scraper implementing best practices
    for handling dynamic content and anti-bot measures.
    """

    def __init__(self):
        self.session = self._setup_session()
        self.base_url = "https://www.naukri.com"
        self.api_endpoint = f"{self.base_url}/jobapi/v2/search"
        self.jobs_scraped = []
        self.errors_encountered = []

    def _setup_session(self) -> requests.Session:
        """
        Configure session with anti-bot headers and settings

        Returns:
            Configured requests session
        """
        session = requests.Session()

        # Rotate user agents to avoid detection
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]

        session.headers.update({
            "User-Agent": random.choice(user_agents),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            # Remove Accept-Encoding to avoid gzip compression issues
            "Referer": "https://www.naukri.com/",
            "Origin": "https://www.naukri.com",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })

        return session

    def _get_location_id(self, location: str) -> str:
        """
        Convert location name to Naukri's internal location ID

        Args:
            location: Location name (e.g., 'bangalore', 'mumbai')

        Returns:
            Location ID string or original location if not mapped
        """
        location_mapping = {
            "bangalore": "4", "mumbai": "1", "delhi": "2", "pune": "3",
            "hyderabad": "5", "chennai": "6", "kolkata": "7", 
            "gurugram": "2050", "noida": "2051", "gurgaon": "2050"
        }
        return location_mapping.get(location.lower(), location.lower())

    def _safe_extract(self, data: Dict, key: str, default: str = "") -> str:
        """
        Safely extract and clean data from API response

        Args:
            data: Dictionary containing job data
            key: Key to extract
            default: Default value if key not found

        Returns:
            Cleaned string value
        """
        try:
            value = data.get(key, default)
            if value is None:
                return default
            return str(value).strip()
        except Exception as e:
            logger.warning(f"Error extracting {key}: {e}")
            return default

    def _safe_int_convert(self, value) -> str:
        """Safely convert scientific notation to integer string"""
        try:
            if value is None or value == "":
                return ""
            return str(int(float(str(value))))
        except (ValueError, TypeError):
            return str(value)

    def _parse_job_data(self, job_raw: Dict) -> JobData:
        """
        Parse raw job data from API response into structured format

        Args:
            job_raw: Raw job data from API

        Returns:
            Structured JobData object
        """
        try:
            # Extract job ID and create URL
            job_id_raw = job_raw.get("jobId", "")
            job_id = self._safe_int_convert(job_id_raw)
            job_url = f"{self.base_url}/job-listings-{job_id}" if job_id else ""

            # Extract and clean job description
            description_parts = []
            if job_raw.get("jobDesc"):
                description_parts.append(self._safe_extract(job_raw, "jobDesc"))
            if job_raw.get("tagsAndSkills"):
                description_parts.append(f"Skills: {self._safe_extract(job_raw, 'tagsAndSkills')}")

            description = " | ".join(description_parts)
            # Limit description length for clean output
            if len(description) > 300:
                description = description[:300] + "..."

            return JobData(
                job_title=self._safe_extract(job_raw, "post"),
                company_name=self._safe_extract(job_raw, "companyName"),
                job_id=job_id,
                job_description=description,
                location=self._safe_extract(job_raw, "city"),
                job_url=job_url,
                scraped_at=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            )

        except Exception as e:
            logger.error(f"Error parsing job data: {e}")
            self.errors_encountered.append(f"Parse error: {e}")
            return JobData()

    def _make_api_request(self, params: Dict) -> Tuple[bool, Dict]:
        """
        Make API request with error handling and retry logic

        Args:
            params: Request parameters

        Returns:
            Tuple of (success: bool, response_data: dict)
        """
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                logger.info(f"Making API request (attempt {attempt + 1})")

                response = self.session.get(
                    self.api_endpoint,
                    params=params,
                    timeout=30
                )

                if response.status_code == 200:
                    try:
                        return True, response.json()
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {e}")
                        logger.debug(f"Response content: {response.text[:200]}")
                        self.errors_encountered.append(f"JSON decode error: {e}")
                        return False, {}

                elif response.status_code == 429:  # Rate limited
                    logger.warning(f"Rate limited. Waiting {retry_delay * 2} seconds...")
                    time.sleep(retry_delay * 2)
                    continue

                else:
                    logger.error(f"HTTP {response.status_code}: {response.text[:200]}")
                    self.errors_encountered.append(f"HTTP {response.status_code}")

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                self.errors_encountered.append(f"Request failed: {e}")

                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

        return False, {}

    def scrape_jobs(self, keyword: str, location: str = "", max_results: int = 100) -> List[JobData]:
        """
        Main scraping method with comprehensive error handling

        Args:
            keyword: Job search keyword
            location: Location filter (optional)
            max_results: Maximum number of jobs to scrape

        Returns:
            List of JobData objects
        """
        logger.info(f"Starting scrape: keyword='{keyword}', location='{location}', max_results={max_results}")

        jobs = []
        page = 1
        jobs_per_page = min(20, max_results)  # API limit is 20 per page

        while len(jobs) < max_results:
            # Prepare request parameters
            params = {
                "noOfResults": jobs_per_page,
                "keyword": keyword,
                "pageNo": page
            }

            if location:
                params["location"] = self._get_location_id(location)

            logger.info(f"Scraping page {page} (jobs collected: {len(jobs)})")

            # Make API request
            success, data = self._make_api_request(params)

            if not success:
                logger.error(f"Failed to fetch page {page}")
                break

            # Extract jobs from response
            job_list = data.get("list", [])
            total_available = data.get("totaljobs", 0)

            if not job_list:
                logger.info("No more jobs found")
                break

            logger.info(f"Processing {len(job_list)} jobs from page {page} (Total available: {total_available})")

            # Process each job
            for job_raw in job_list:
                if len(jobs) >= max_results:
                    break

                job_data = self._parse_job_data(job_raw)

                # Only add jobs with valid titles
                if job_data.job_title:
                    jobs.append(job_data)
                else:
                    logger.warning("Skipped job with missing title")

            # Check if we should continue
            total_pages = data.get("totalpages", 0)
            if page >= total_pages:
                logger.info(f"Reached last page ({total_pages})")
                break

            page += 1

            # Implement polite delay to avoid rate limiting
            delay = random.uniform(1, 3)
            logger.debug(f"Waiting {delay:.1f}s before next request")
            time.sleep(delay)

        logger.info(f"Scraping completed. Collected {len(jobs)} jobs")
        self.jobs_scraped = jobs
        return jobs

    def save_to_csv(self, jobs: List[JobData], filename: str = "naukri_jobs.csv") -> bool:
        """
        Save job data to CSV file

        Args:
            jobs: List of JobData objects
            filename: Output filename

        Returns:
            Success status
        """
        try:
            if not jobs:
                logger.warning("No jobs to save")
                return False

            df = pd.DataFrame([asdict(job) for job in jobs])
            df.to_csv(filename, index=False, encoding='utf-8')

            logger.info(f"Saved {len(jobs)} jobs to {filename}")
            return True

        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")
            return False

    def save_to_excel(self, jobs: List[JobData], filename: str = "naukri_jobs.xlsx") -> bool:
        """
        Save job data to Excel file with formatting

        Args:
            jobs: List of JobData objects
            filename: Output filename

        Returns:
            Success status
        """
        try:
            if not jobs:
                logger.warning("No jobs to save")
                return False

            df = pd.DataFrame([asdict(job) for job in jobs])

            # Try to use openpyxl if available
            try:
                with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='Jobs', index=False)

                    # Auto-adjust column widths
                    worksheet = writer.sheets['Jobs']
                    for column in worksheet.columns:
                        max_length = 0
                        column_letter = column[0].column_letter
                        for cell in column:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(str(cell.value))
                            except:
                                pass
                        adjusted_width = min(max_length + 2, 50)
                        worksheet.column_dimensions[column_letter].width = adjusted_width

            except ImportError:
                # Fallback to xlsxwriter if openpyxl not available
                df.to_excel(filename, index=False)

            logger.info(f"Saved {len(jobs)} jobs to {filename}")
            return True

        except Exception as e:
            logger.error(f"Error saving to Excel: {e}")
            return False

    def generate_summary_report(self, jobs: List[JobData]) -> Dict:
        """
        Generate summary statistics for scraped jobs

        Args:
            jobs: List of JobData objects

        Returns:
            Summary statistics dictionary
        """
        if not jobs:
            return {"total_jobs": 0, "errors_encountered": len(self.errors_encountered)}

        df = pd.DataFrame([asdict(job) for job in jobs])

        summary = {
            "total_jobs": len(jobs),
            "unique_companies": df['company_name'].nunique(),
            "unique_locations": df['location'].nunique(),
            "top_companies": df['company_name'].value_counts().head(10).to_dict(),
            "top_locations": df['location'].value_counts().head(10).to_dict(),
            "errors_encountered": len(self.errors_encountered),
            "success_rate": f"{((len(jobs) / (len(jobs) + len(self.errors_encountered))) * 100):.1f}%" if self.errors_encountered else "100%"
        }

        return summary

def main():
    """
    Main execution function with command line interface
    """
    if len(sys.argv) < 2:
        print("\nNaukri.com Job Scraper - Professional Version")
        print("=" * 50)
        print("Usage: python naukri_scraper.py <keyword> [location] [max_results]")
        print("\nExamples:")
        print("  python naukri_scraper.py 'python developer'")
        print("  python naukri_scraper.py 'data scientist' bangalore")
        print("  python naukri_scraper.py 'software engineer' mumbai 50")
        print("\nSupported locations: bangalore, mumbai, delhi, pune, hyderabad, chennai, etc.")
        return

    # Parse command line arguments
    keyword = sys.argv[1]
    location = sys.argv[2] if len(sys.argv) > 2 else ""
    max_results = int(sys.argv[3]) if len(sys.argv) > 3 else 100

    # Initialize scraper
    scraper = NaukriScraper()

    try:
        # Perform scraping
        jobs = scraper.scrape_jobs(keyword, location, max_results)

        if not jobs:
            logger.error("No jobs were scraped successfully")
            return

        # Generate output filenames
        safe_keyword = "".join(c for c in keyword if c.isalnum() or c in (' ', '-', '_')).replace(' ', '_').lower()
        base_filename = f"naukri_{safe_keyword}"
        if location:
            base_filename += f"_{location.lower()}"

        # Save to multiple formats
        csv_filename = f"{base_filename}.csv"
        excel_filename = f"{base_filename}.xlsx"

        csv_success = scraper.save_to_csv(jobs, csv_filename)
        excel_success = scraper.save_to_excel(jobs, excel_filename)

        # Generate and display summary
        summary = scraper.generate_summary_report(jobs)

        print("\n" + "=" * 60)
        print("SCRAPING COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print(f"📊 Total Jobs Scraped: {summary['total_jobs']}")
        print(f"🏢 Unique Companies: {summary['unique_companies']}")
        print(f"📍 Unique Locations: {summary['unique_locations']}")
        print(f"✅ Success Rate: {summary['success_rate']}")

        if csv_success:
            print(f"📄 CSV File: {csv_filename}")
        if excel_success:
            print(f"📊 Excel File: {excel_filename}")

        print("\n📈 Top Companies:")
        for company, count in list(summary['top_companies'].items())[:5]:
            print(f"  • {company}: {count} jobs")

        print("\n🌍 Top Locations:")
        for location, count in list(summary['top_locations'].items())[:5]:
            print(f"  • {location}: {count} jobs")

        print("\n🔗 Sample Jobs:")
        for i, job in enumerate(jobs[:3], 1):
            print(f"  {i}. {job.job_title}")
            print(f"     Company: {job.company_name}")
            print(f"     Location: {job.location}")
            print(f"     URL: {job.job_url}")
            print()

        logger.info("Scraping process completed successfully")

    except Exception as e:
        logger.error(f"Scraping failed with error: {e}")
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
