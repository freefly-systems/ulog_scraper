# Basic imports
import scrapy
import time
import os
import json
import logging

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

def parse_config_file(config_file_path):
    """
    Parses the configuration file and returns a list of vehicle configs
    Format: "vehicle_name : start_date - end_date"
    
    Returns:
        list of tuples: [(vehicle_name, start_date, end_date), ...]
    """
    vehicle_configs = []
    
    with open(config_file_path, 'r') as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith('#'):
                continue  # Skip empty lines and comments
                
            # Parse line in format "vehicle_name : start_date - end_date"
            try:
                vehicle_part, date_part = line.split(':', 1)
                vehicle_name = vehicle_part.strip()
                
                start_date_str, end_date_str = date_part.split('-', 1)
                start_date = start_date_str.strip()
                end_date = end_date_str.strip()
                
                vehicle_configs.append((vehicle_name, start_date, end_date))
            except ValueError:
                print(f"Warning: Could not parse line: {line}")
    
    return vehicle_configs

class LogDownloaderSpider(scrapy.Spider):
    """
    Spider for logging into Auterion Suite and downloading log files.
    
    This spider uses Selenium to handle the login process, which involves multiple steps:
    1. Navigate to the login page
    2. Click the login button
    3. Enter email address
    4. Enter password
    5. Navigate to the logs page
    6. Download log files
    
    The spider can be configured to keep the browser window open after login for debugging.
    """
    name = 'log_downloader'
    allowed_domains = ['suite.auterion.com']
    
    def __init__(self, config_file=None, username=None, password=None, *args, **kwargs):
        """
        Initialize the spider with credentials and set up logging and browser.
        
        Args:
            config_file (str, optional): Path to the configuration file.
            username (str, optional): Auterion Suite username/email. If not provided, 
                                     will be read from environment variable.
            password (str, optional): Auterion Suite password. If not provided, 
                                     will be read from environment variable.
        """
        super(LogDownloaderSpider, self).__init__(*args, **kwargs)
        
        # Setup logging
        self.setup_logger()
        
        # Load environment variables
        try:
            from dotenv import load_dotenv
            load_dotenv()
            self.log("Loaded .env file")
        except ImportError:
            self.log("python-dotenv not installed, skipping .env file loading", logging.WARNING)
        
        # Store credentials
        self.username = username or os.environ.get('AUTERION_USERNAME')
        self.password = password or os.environ.get('AUTERION_PASSWORD')
        
        if not self.username or not self.password:
            self.log("Username and password must be provided", logging.ERROR)
            raise ValueError("Username and password must be provided")
            
        # Parse config file if provided
        self.config_file = config_file or 'vehicle_logs.conf'
        self.vehicle_configs = parse_config_file(self.config_file)
        self.log(f"Loaded {len(self.vehicle_configs)} vehicle configurations")
        
        # Vehicle processing state
        self.current_vehicle_index = 0
        
        # Initialize Selenium driver
        self.driver = webdriver.Chrome()
        self.log("Selenium driver initialized")
        
    def setup_logger(self):
        """
        Set up a file logger in addition to the console logger.
        
        Creates a logs directory if it doesn't exist and configures a file handler
        to log messages to logs/scraper.log.
        """
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Set up the file handler
        file_handler = logging.FileHandler('logs/scraper.log')
        file_handler.setLevel(logging.INFO)
        
        # Set up the formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # Add the handler to the logger
        logger = logging.getLogger('ulog_scraper')
        logger.setLevel(logging.INFO)
        logger.addHandler(file_handler)
        
        # Connect our logger to self.logger
        self.custom_logger = logger
        self.logger.info("File logger initialized")
    
    def log(self, message, level=logging.INFO):
        """
        Log to both Scrapy logger and our custom file logger.
        
        Args:
            message (str): The message to log
            level (int): The logging level (INFO, WARNING, ERROR)
        """
        if level == logging.ERROR:
            self.logger.error(message)
            self.custom_logger.error(message)
        elif level == logging.WARNING:
            self.logger.warning(message)
            self.custom_logger.warning(message)
        else:
            self.logger.info(message)
            self.custom_logger.info(message)
        
    def closed(self, reason):
        """
        Handle spider close event. Keeps browser open if requested.
        
        Args:
            reason (str): Reason for spider closing
        """
        if hasattr(self, 'keep_browser_open') and self.keep_browser_open:
            self.log("Spider closed but keeping browser open as requested")
            # Do not call self.driver.quit() to keep browser window open
        else:
            # Default behavior - close the browser
            self.driver.quit()
            self.log(f"Spider closed: {reason}")
    
    def start_requests(self):
        """Start the login process and then begin vehicle processing"""
        self.log("Starting login process")
        
        try:
            # Navigate to login page
            self.driver.get('https://suite.auterion.com/login')
            self.log("Navigated to login page")
            
            # Wait for the page to load
            time.sleep(5)
            
            # Attempt login
            login_success = self.perform_login()
            
            if login_success:
                self.log("Login successful - proceeding to process vehicles")
                # Process the first vehicle
                return self.process_next_vehicle()
            else:
                self.log("Login failed", logging.ERROR)
                return []
            
        except Exception as e:
            self.log(f"Login process failed: {str(e)}", logging.ERROR)
            return []
    
    def process_next_vehicle(self):
        """Process the next vehicle in the queue and yield any necessary requests"""
        
        if self.current_vehicle_index >= len(self.vehicle_configs):
            self.log("All vehicles processed, spider will close")
            return []
        
        # Get the current vehicle config
        vehicle_name, start_date, end_date = self.vehicle_configs[self.current_vehicle_index]
        self.log(f"Processing vehicle: {vehicle_name} for date range: {start_date} to {end_date}")
        
        # Navigate to the vehicles page
        self.driver.get("https://suite.auterion.com/vehicles")
        self.log("Navigated to vehicles page")
        
        # Wait for the page to load completely
        WebDriverWait(self.driver, 30).until(
            lambda driver: driver.execute_script("return document.readyState") == "complete"
        )
        time.sleep(5)  # Additional wait for UI elements
        
        # Search for the vehicle
        self.search_for_vehicle(vehicle_name)
        
        # Navigate to vehicle logs and download them
        logs_downloaded = self.navigate_to_vehicle_logs(vehicle_name, start_date, end_date)
        
        # Increment the index for the next vehicle
        self.current_vehicle_index += 1
        
        # After we're done with this vehicle, recursively process the next one
        if self.current_vehicle_index < len(self.vehicle_configs):
            return self.process_next_vehicle()
        else:
            self.log("Finished processing all vehicles")
            return []
    
    def perform_login(self):
        """
        Handle the login process with multiple steps and proper element detection.
        
        The login flow consists of:
        1. Click initial login button
        2. Find and fill email input field
        3. Click continue/next button
        4. Find and fill password field
        5. Click final submit button
        6. Wait for successful login
        7. Navigate to vehicles page and stop
        
        Returns:
            bool: True if login was successful, raises exception otherwise
        """
        self.log("Starting multi-step login process")
        
        # Step 1: Find and click initial login button on landing page
        self.log("Step 1: Finding initial login button")
        try:
            # Try multiple selectors for the initial login button
            selectors_to_try = [
                (By.CSS_SELECTOR, "button.button-primary"),
                (By.XPATH, "//button[contains(text(), 'Login')]"),
                (By.XPATH, "//button[normalize-space()='Login']")
            ]
            
            login_button = None
            for selector_type, selector in selectors_to_try:
                elements = self.driver.find_elements(selector_type, selector)
                if elements:
                    login_button = elements[0]
                    break
            
            if not login_button:
                self.log("Could not find initial login button", logging.ERROR)
                raise Exception("Could not find login button")
            
            login_button.click()
            self.log("Clicked login button, waiting for email form")
            
            # Step 2: Find and fill email field
            self.log("Step 2: Looking for email input field")
            email_selectors = [
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.CSS_SELECTOR, "input[name='email']"),
                (By.XPATH, "//input[@type='email']"),
                (By.CSS_SELECTOR, "input[name='username']"),
                (By.XPATH, "//input[@name='username']")
            ]
            
            email_input = None
            for selector_type, selector in email_selectors:
                elements = self.driver.find_elements(selector_type, selector)
                if elements:
                    email_input = elements[0]
                    break
            
            if not email_input:
                self.log("Could not find email input field", logging.ERROR)
                raise Exception("Email input field not found")
            
            # Enter email
            self.log("Entering email address")
            email_input.clear()
            email_input.send_keys(self.username)
            
            # Step 3: Look for continue button after entering email
            self.log("Looking for continue/next button after email entry")
            continue_selectors = [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Continue')]"),
                (By.XPATH, "//button[contains(text(), 'Next')]")
            ]
            
            continue_button = None
            for selector_type, selector in continue_selectors:
                elements = self.driver.find_elements(selector_type, selector)
                if elements:
                    continue_button = elements[0]
                    break
            
            if not continue_button:
                self.log("No continue button found, trying to submit with Enter key", logging.WARNING)
                email_input.send_keys(Keys.RETURN)
            else:
                continue_button.click()
                self.log("Clicked continue button")
            
            # Step 3: Wait for password field and enter password
            self.log("Step 3: Waiting for password field")
            time.sleep(3)
            
            # Try to find password field
            password_selectors = [
                (By.CSS_SELECTOR, "input[type='password']"),
                (By.XPATH, "//input[@type='password']"),
                (By.CSS_SELECTOR, "input[name='password']")
            ]
            
            password_input = None
            for selector_type, selector in password_selectors:
                try:
                    wait = WebDriverWait(self.driver, 5)
                    password_input = wait.until(EC.presence_of_element_located((selector_type, selector)))
                    break
                except:
                    continue
            
            if not password_input:
                self.log("Could not find password field", logging.ERROR)
                raise Exception("Password field not found")
            
            # Enter password
            self.log("Entering password")
            password_input.clear()
            password_input.send_keys(self.password)
            
            # Look for login/submit button
            self.log("Looking for final submit button")
            submit_selectors = [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Sign in')]"),
                (By.XPATH, "//button[contains(text(), 'Login')]")
            ]
            
            submit_button = None
            for selector_type, selector in submit_selectors:
                elements = self.driver.find_elements(selector_type, selector)
                if elements:
                    submit_button = elements[0]
                    break
            
            if not submit_button:
                self.log("No submit button found, trying to submit with Enter key", logging.WARNING)
                password_input.send_keys(Keys.RETURN)
            else:
                submit_button.click()
                self.log("Clicked submit button")
            
            # Wait for successful login with a longer timeout (3 minutes)
            self.log("Waiting for successful login (up to 3 minutes)")
            try:
                # Wait longer as requested - 180 seconds = 3 minutes
                WebDriverWait(self.driver, 180).until(
                    lambda driver: 'suite.auterion.com' in driver.current_url and 
                                  driver.execute_script("return document.readyState") == "complete"
                )
                self.log("Login appears successful! Page loaded completely.")
                self.log(f"Current URL after login: {self.driver.current_url}")
                
                # Navigate to Vehicles page and stop
                self.navigate_to_vehicles()
                
                # Flag to keep browser open - this is already set in navigate_to_vehicles()
                self.keep_browser_open = True
                
                # Return True to indicate successful login
                return True
                
            except Exception as e:
                self.log(f"Login completion detection failed: {str(e)}", logging.ERROR)
                raise Exception(f"Login process failed - could not verify successful page load: {str(e)}")
            
        except Exception as e:
            self.log(f"Error during login process: {str(e)}", logging.ERROR)
            raise
    
    def navigate_to_vehicles(self):
        """
        Navigate to the Vehicles page, search for 'dv21', click on the specific vehicle,
        click on "All Flights" button, click on the MXNT flight entry, click on the "log" button,
        click on "View Analytics", and finally click on "Download log".
        """
        self.log("Attempting to navigate to Vehicles page")
        try:
            # First ensure the page is fully loaded after login
            self.log("Ensuring page is fully loaded")
            WebDriverWait(self.driver, 30).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            time.sleep(5)  # Additional wait to ensure UI elements are rendered
            
            # Directly navigate to Vehicles page
            self.log("Direct navigation to Vehicles page")
            self.driver.get("https://suite.auterion.com/vehicles")
            
            # Wait for the Vehicles page to load
            self.log("Waiting for Vehicles page to load")
            WebDriverWait(self.driver, 30).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            time.sleep(5)  # Additional wait to ensure UI elements are rendered
            
            self.log(f"Current URL after direct navigation: {self.driver.current_url}")
            
            # STEP 1: Search for DV21
            self.log("Looking for search input field")
            search_input_selectors = [
                (By.CSS_SELECTOR, "input[placeholder='dv21']"),
                (By.CSS_SELECTOR, "input.search"),
                (By.XPATH, "//div[@class='search']//input"),
                (By.CSS_SELECTOR, "input[type='text']")
            ]
            
            search_input = None
            for selector_type, selector in search_input_selectors:
                elements = self.driver.find_elements(selector_type, selector)
                for element in elements:
                    if element.is_displayed():
                        search_input = element
                        break
                if search_input:
                    break
            
            # If we found the search input, enter "dv21" and press Enter
            if search_input:
                self.log("Entering 'dv21' in search field")
                search_input.clear()
                search_input.send_keys("dv21")
                time.sleep(1)  # Brief pause
                self.log("Submitting search")
                search_input.send_keys(Keys.RETURN)
                
                # Wait for search results to load
                self.log("Waiting for search results to load")
                WebDriverWait(self.driver, 30).until(
                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                )
                time.sleep(5)  # Additional wait for AJAX results
            else:
                self.log("No search input found, skipping search", logging.WARNING)
            
            # STEP 2: Find and click on "Astro DV21 (Nate)" link within the All Vehicles section
            self.log("Looking for 'Astro DV21 (Nate)' link")
            dv21_link_selectors = [
                (By.CSS_SELECTOR, "a[href='/vehicles/1661']"),
                (By.XPATH, "//a[contains(@href, '/vehicles/1661')]"),
                (By.XPATH, "//a[contains(text(), 'Astro DV21')]"),
                (By.XPATH, "//a[contains(., 'DV21')]")
            ]
            
            dv21_link = None
            for selector_type, selector in dv21_link_selectors:
                elements = self.driver.find_elements(selector_type, selector)
                for element in elements:
                    if element.is_displayed() and "DV21" in element.text:
                        dv21_link = element
                        break
                if dv21_link:
                    break
                
            # If we found the link, click on it
            if dv21_link:
                self.log("Clicking on 'Astro DV21 (Nate)' link")
                dv21_link.click()
                
                # Wait for vehicle details page to load
                self.log("Waiting for vehicle details page to load")
                WebDriverWait(self.driver, 30).until(
                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                )
                time.sleep(8)  # Longer wait to ensure all content is loaded
                
                self.log(f"Current URL after clicking DV21 link: {self.driver.current_url}")
                
                # STEP 3: Find and click on "All Flights" link
                self.log("Looking for 'All Flights' link")
                all_flights_selectors = [
                    (By.CSS_SELECTOR, "a[href='/flights?vehicle=1661&showRoute=true']"),
                    (By.XPATH, "//a[contains(@href, '/flights?vehicle=1661')]"),
                    (By.XPATH, "//a[contains(@class, 'button-link') and contains(text(), 'All Flights')]"),
                    (By.XPATH, "//a[text()='All Flights']")
                ]
                
                all_flights_link = None
                for selector_type, selector in all_flights_selectors:
                    elements = self.driver.find_elements(selector_type, selector)
                    for element in elements:
                        if element.is_displayed() and "All Flights" in element.text:
                            all_flights_link = element
                            break
                    if all_flights_link:
                        break
                
                # If we found the All Flights link, click on it
                if all_flights_link:
                    self.log("Clicking on 'All Flights' link")
                    all_flights_link.click()
                    
                    # Wait for flights page to load
                    self.log("Waiting for flights page to load")
                    WebDriverWait(self.driver, 30).until(
                        lambda driver: driver.execute_script("return document.readyState") == "complete"
                    )
                    time.sleep(8)  # Longer wait to ensure all content is loaded
                    
                    self.log(f"Current URL after clicking All Flights link: {self.driver.current_url}")
                    
                    # STEP 4: Find and click on the MXNT flight entry
                    self.log("Looking for MXNT flight entry")
                    mxnt_flight_selectors = [
                        (By.XPATH, "//tr[contains(., 'MXNT')]"),
                        (By.XPATH, "//a[contains(., 'MXNT')]"),
                        (By.XPATH, "//td[contains(., 'MXNT')]/parent::tr"),
                        (By.XPATH, "//span[contains(text(), 'MXNT')]/ancestor::tr")
                    ]
                    
                    mxnt_flight_element = None
                    for selector_type, selector in mxnt_flight_selectors:
                        elements = self.driver.find_elements(selector_type, selector)
                        for element in elements:
                            if element.is_displayed() and "MXNT" in element.text:
                                mxnt_flight_element = element
                                break
                        if mxnt_flight_element:
                            break
                    
                    # If we found the MXNT flight element, click on it
                    if mxnt_flight_element:
                        # Try to find a clickable element within the row (like a link)
                        try:
                            # First try to find a link within the element
                            clickable = mxnt_flight_element.find_element(By.TAG_NAME, "a")
                            self.log("Found clickable link within MXNT flight row")
                        except:
                            # If no link found, use the element itself
                            clickable = mxnt_flight_element
                            self.log("Using the flight row element directly for clicking")
                        
                        self.log("Clicking on MXNT flight entry")
                        clickable.click()
                        
                        # Wait for flight details page to load
                        self.log("Waiting for flight details page to load")
                        WebDriverWait(self.driver, 30).until(
                            lambda driver: driver.execute_script("return document.readyState") == "complete"
                        )
                        time.sleep(8)  # Longer wait to ensure all content is loaded
                        
                        self.log(f"Current URL after clicking MXNT flight: {self.driver.current_url}")
                        
                        # STEP 5: Find and click on the "log" button
                        self.log("Looking for 'log' button")
                        log_button_selectors = [
                            (By.CSS_SELECTOR, "a[href*='/logs']"),
                            (By.XPATH, "//a[contains(@href, '/logs')]"),
                            (By.XPATH, "//a[text()='log']"),
                            (By.XPATH, "//span[text()='log']")
                        ]
                        
                        log_button = None
                        for selector_type, selector in log_button_selectors:
                            elements = self.driver.find_elements(selector_type, selector)
                            for element in elements:
                                if element.is_displayed():
                                    # Check if the element contains 'log' text but not as part of a longer word
                                    text = element.text.lower()
                                    if "log" in text and not any(x in text for x in ["login", "logout", "catalog"]):
                                        log_button = element
                                        break
                            if log_button:
                                break
                        
                        # If we found the log button, click on it
                        if log_button:
                            self.log("Clicking on 'log' button")
                            log_button.click()
                            
                            # Wait for logs page to load
                            self.log("Waiting for logs page to load")
                            WebDriverWait(self.driver, 30).until(
                                lambda driver: driver.execute_script("return document.readyState") == "complete"
                            )
                            time.sleep(8)  # Longer wait to ensure all content is loaded
                            
                            self.log(f"Current URL after clicking log button: {self.driver.current_url}")
                            
                            # STEP 6: Find and click on "View Analytics" button
                            self.log("Looking for 'View Analytics' button")
                            view_analytics_selectors = [
                                (By.XPATH, "//span[contains(text(), 'View Analytics')]"),
                                (By.XPATH, "//a[contains(text(), 'View Analytics')]"),
                                (By.XPATH, "//*[contains(text(), 'View Analytics')]")
                            ]
                            
                            view_analytics_button = None
                            for selector_type, selector in view_analytics_selectors:
                                elements = self.driver.find_elements(selector_type, selector)
                                for element in elements:
                                    if element.is_displayed() and "View Analytics" in element.text:
                                        view_analytics_button = element
                                        break
                                if view_analytics_button:
                                    break
                            
                            # If we found the View Analytics button, click on it
                            if view_analytics_button:
                                self.log("Clicking on 'View Analytics' button")
                                view_analytics_button.click()
                                
                                # Wait for analytics page to load
                                self.log("Waiting for analytics page to load")
                                WebDriverWait(self.driver, 30).until(
                                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                                )
                                time.sleep(8)  # Longer wait to ensure all content is loaded
                                
                                self.log(f"Current URL after clicking View Analytics button: {self.driver.current_url}")
                                
                                # STEP 7: Find and click on the "Download log" button
                                self.log("Looking for 'Download log' button")
                                download_log_selectors = [
                                    (By.XPATH, "//span[contains(text(), 'Download log')]"),
                                    (By.XPATH, "//button[contains(., 'Download log')]"),
                                    (By.XPATH, "//span[text()='Download log']"),
                                    (By.XPATH, "//*[contains(text(), 'Download')]")
                                ]
                                
                                download_log_button = None
                                for selector_type, selector in download_log_selectors:
                                    elements = self.driver.find_elements(selector_type, selector)
                                    for element in elements:
                                        if element.is_displayed() and "Download" in element.text:
                                            download_log_button = element
                                            break
                                    if download_log_button:
                                        break
                                
                                # If we found the Download log button, click on it
                                if download_log_button:
                                    self.log("Clicking on 'Download log' button")
                                    download_log_button.click()
                                    
                                    # Wait a moment for the download to start
                                    time.sleep(5)
                                    
                                    self.log(f"Current URL after clicking Download log button: {self.driver.current_url}")
                                    self.log("Log file should now be downloading to your downloads folder")
                                else:
                                    self.log("Could not find Download log button", logging.WARNING)
                            else:
                                self.log("Could not find View Analytics button", logging.WARNING)
                        else:
                            self.log("Could not find log button", logging.WARNING)
                    else:
                        self.log("Could not find MXNT flight entry", logging.WARNING)
                else:
                    self.log("Could not find All Flights link", logging.WARNING)
            else:
                self.log("Could not find DV21 link, will not navigate to details page", logging.WARNING)
            
            # Set flag to keep browser open
            self.keep_browser_open = True
            
            # Create a file to signal we're keeping the browser open
            with open('browser_open.txt', 'w') as f:
                f.write(f"Browser remains open with session at: {self.driver.current_url}\n")
                f.write("Navigation completed through: Vehicles page -> DV21 details -> All Flights -> MXNT flight -> Logs -> View Analytics -> Download log\n")
                f.write("Script has finished execution, but browser should remain open.\n")
                f.write("Close browser manually when finished examining.")
            
            self.log("Script execution complete - browser window will remain open for manual inspection")
            
        except Exception as e:
            self.log(f"Error in navigation process: {str(e)}", logging.ERROR)

    def search_for_vehicle(self, vehicle_name):
        """Search for a specific vehicle by name in the vehicles page"""
        self.log(f"Searching for vehicle: {vehicle_name}")
        
        # Look for search input
        search_input_selectors = [
            (By.CSS_SELECTOR, "input[type='text']"),
            (By.CSS_SELECTOR, "input.search"),
            (By.XPATH, "//div[@class='search']//input")
        ]
        
        search_input = None
        for selector_type, selector in search_input_selectors:
            elements = self.driver.find_elements(selector_type, selector)
            for element in elements:
                if element.is_displayed():
                    search_input = element
                    break
            if search_input:
                break
        
        if search_input:
            self.log(f"Entering '{vehicle_name}' in search field")
            search_input.clear()
            search_input.send_keys(vehicle_name)
            time.sleep(1)
            search_input.send_keys(Keys.RETURN)
            
            # Wait for search results
            WebDriverWait(self.driver, 30).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            time.sleep(5)
        else:
            self.log("No search input found", logging.WARNING)