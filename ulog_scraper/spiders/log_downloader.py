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
    
    def __init__(self, username=None, password=None, *args, **kwargs):
        """
        Initialize the spider with credentials and set up logging and browser.
        
        Args:
            username (str, optional): Auterion Suite username/email. If not provided, 
                                     will be read from environment variable.
            password (str, optional): Auterion Suite password. If not provided, 
                                     will be read from environment variable.
        """
        super(LogDownloaderSpider, self).__init__(*args, **kwargs)
        
        # Set up file logging FIRST
        self.setup_logger()
        
        # THEN load .env file if dotenv is installed
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
            # This will ensure the browser stays open after the script finishes
        else:
            # Default behavior - close the browser
            self.driver.quit()
            self.log(f"Spider closed: {reason}")
    
    def start_requests(self):
        """
        Start the login process by navigating to the login page.
        
        Returns:
            list: A list of requests to process, or an empty list if we're keeping
                 the browser open for examination
        """
        self.log("Starting login process")
        
        try:
            # Navigate to login page
            self.driver.get('https://suite.auterion.com/login')
            self.log("Navigated to login page")
            
            # Wait for the page to load
            time.sleep(5)
            
            # Take a screenshot for debugging
            self.driver.save_screenshot('logs/login_page.png')
            self.log("Saved screenshot of initial login page")
            
            # Attempt to login
            login_success = self.perform_login()
            
            if login_success:
                self.log("Login successful - keeping browser open for examination")
                # Set flag to prevent browser from closing when spider finishes
                self.keep_browser_open = True
                
                # Create a file to signal we're keeping the browser open
                with open('browser_open.txt', 'w') as f:
                    f.write(f"Browser remains open with session at: {self.driver.current_url}\n")
                    f.write("Script has finished execution, but browser should remain open.\n")
                    f.write("Close browser manually when finished examining.")
                    
                # Return empty list to let spider finish normally
                return []
            
            # This code will only run if login failed
            return self.navigate_to_logs()
            
        except Exception as e:
            self.log(f"Login process failed: {str(e)}", logging.ERROR)
            self.driver.save_screenshot('logs/error_state.png')
            self.log("Saved error state screenshot", logging.ERROR)
            # Return empty list to avoid "not iterable" error
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
                self.log(f"Trying selector: {selector_type} - {selector}")
                elements = self.driver.find_elements(selector_type, selector)
                if elements:
                    self.log(f"Found {len(elements)} elements with selector {selector}")
                    login_button = elements[0]
                    break
            
            if not login_button:
                self.log("Could not find initial login button", logging.ERROR)
                self.driver.save_screenshot('logs/no_login_button.png')
                raise Exception("Could not find login button")
            
            self.log(f"Found login button: {login_button.text}")
            login_button.click()
            self.log("Clicked login button, waiting for email form")
            
            # Step 2: Find and fill email field
            self.log("Step 2: Looking for email input field")
            email_selectors = [
                # Specific to "Email address" label
                (By.XPATH, "//label[contains(text(), 'Email address')]/following::input[1]"),
                (By.XPATH, "//label[text()='Email address']/following::input[1]"),
                (By.CSS_SELECTOR, "input[aria-label='Email address']"),
                (By.CSS_SELECTOR, "input[placeholder='Email address']"),
                # Common email selectors
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.CSS_SELECTOR, "input[name='email']"),
                (By.CSS_SELECTOR, "input[placeholder*='mail']"),
                (By.XPATH, "//input[@type='email']"),
                (By.XPATH, "//input[contains(@placeholder, 'mail')]"),
                (By.CSS_SELECTOR, "input.email-input"),
                # The username field (sometimes used for email)
                (By.CSS_SELECTOR, "input[name='username']"),
                (By.XPATH, "//input[@name='username']")
            ]
            
            email_input = None
            for selector_type, selector in email_selectors:
                self.log(f"Trying to find email field with: {selector_type} - {selector}")
                try:
                    elements = self.driver.find_elements(selector_type, selector)
                    if elements:
                        email_input = elements[0]
                        self.log(f"Found email input with selector {selector}")
                        break
                except Exception as e:
                    self.log(f"Error with selector {selector}: {e}")
            
            if not email_input:
                self.log("Could not find email input field, trying to identify all input elements", logging.WARNING)
                # List all input fields to help debug
                inputs = self.driver.find_elements(By.TAG_NAME, "input")
                for i, inp in enumerate(inputs):
                    try:
                        input_type = inp.get_attribute("type") or "none"
                        input_name = inp.get_attribute("name") or "none"
                        input_placeholder = inp.get_attribute("placeholder") or "none"
                        self.log(f"Input {i}: type={input_type}, name={input_name}, placeholder={input_placeholder}")
                    except:
                        self.log(f"Input {i}: Could not get attributes")
                
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
                (By.XPATH, "//button[contains(text(), 'Next')]"),
                (By.CSS_SELECTOR, "button.continue-button"),
                (By.CSS_SELECTOR, "button.next-button")
            ]
            
            continue_button = None
            for selector_type, selector in continue_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector)
                    if elements:
                        continue_button = elements[0]
                        self.log(f"Found continue button with selector {selector}")
                        break
                except Exception as e:
                    self.log(f"Error with continue button selector {selector}: {e}")
            
            if not continue_button:
                self.log("No continue button found, trying to submit with Enter key", logging.WARNING)
                email_input.send_keys(Keys.RETURN)
            else:
                continue_button.click()
                self.log("Clicked continue button")
            
            # Step 3: Wait for password field and enter password
            self.log("Step 3: Waiting for password field")
            time.sleep(3)
            self.driver.save_screenshot('logs/after_email_entry.png')
            
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
                    self.log(f"Found password input with selector {selector}")
                    break
                except:
                    self.log(f"Selector {selector} for password field failed")
            
            if not password_input:
                self.log("Could not find password field", logging.ERROR)
                self.driver.save_screenshot('logs/password_not_found.png')
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
                (By.XPATH, "//button[contains(text(), 'Login')]"),
                (By.CSS_SELECTOR, "button.submit-button"),
                (By.CSS_SELECTOR, "button.login-button")
            ]
            
            submit_button = None
            for selector_type, selector in submit_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector)
                    if elements:
                        submit_button = elements[0]
                        self.log(f"Found submit button with selector {selector}")
                        break
                except Exception as e:
                    self.log(f"Error with submit button selector {selector}: {e}")
            
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
                
                # Save detailed state information
                self.driver.save_screenshot('logs/post_login_state.png')
                self.log(f"Current URL after login: {self.driver.current_url}")
                
                # Navigate to Vehicles page and stop
                self.navigate_to_vehicles()
                
                # Flag to keep browser open - this is already set in navigate_to_vehicles()
                self.keep_browser_open = True
                
                # Return True to indicate successful login
                return True
                
            except Exception as e:
                self.log(f"Login completion detection failed: {str(e)}", logging.ERROR)
                self.driver.save_screenshot('logs/login_completion_failure.png')
                raise Exception(f"Login process failed - could not verify successful page load: {str(e)}")
            
        except Exception as e:
            self.log(f"Error during login process: {str(e)}", logging.ERROR)
            self.driver.save_screenshot('logs/login_error.png')
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
            
            # Take a screenshot of the current state
            self.driver.save_screenshot('logs/after_login_fully_loaded.png')
            
            # Directly navigate to Vehicles page
            self.log("Direct navigation to Vehicles page")
            self.driver.get("https://suite.auterion.com/vehicles")
            
            # Wait for the Vehicles page to load
            self.log("Waiting for Vehicles page to load")
            WebDriverWait(self.driver, 30).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            time.sleep(5)  # Additional wait to ensure UI elements are rendered
            
            # Take screenshot of the Vehicles page
            self.driver.save_screenshot('logs/vehicles_page_direct.png')
            self.log(f"Current URL after direct navigation: {self.driver.current_url}")
            
            # STEP 1: Search for DV21
            # Looking for the search box at the bottom of the page from the screenshot
            self.log("Looking for search input field")
            search_input_selectors = [
                # Bottom search box selector from screenshot
                (By.CSS_SELECTOR, "input[placeholder='dv21']"),
                (By.CSS_SELECTOR, "input.search"),
                (By.XPATH, "//div[@class='search']//input"),
                # More generic fallbacks
                (By.CSS_SELECTOR, "input[type='text']"),
                (By.XPATH, "//input")
            ]
            
            search_input = None
            for selector_type, selector in search_input_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector)
                    for element in elements:
                        if element.is_displayed():
                            search_input = element
                            self.log(f"Found search input with selector {selector}")
                            break
                    if search_input:
                        break
                except Exception as e:
                    self.log(f"Error with search input selector {selector}: {e}")
            
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
                
                # Take screenshot of search results
                self.driver.save_screenshot('logs/search_results_dv21.png')
                self.log("Screenshot taken of search results")
            else:
                self.log("No search input found, skipping search", logging.WARNING)
            
            # STEP 2: Find and click on "Astro DV21 (Nate)" link within the All Vehicles section
            self.log("Looking for 'Astro DV21 (Nate)' link")
            dv21_link_selectors = [
                # Based on the HTML from screenshot - direct link
                (By.CSS_SELECTOR, "a[href='/vehicles/1661']"),
                (By.XPATH, "//a[contains(@href, '/vehicles/1661')]"),
                # Based on text content
                (By.XPATH, "//a[contains(text(), 'Astro DV21')]"),
                (By.XPATH, "//a[contains(., 'DV21')]"),
                # More specific based on HTML structure
                (By.XPATH, "//div[contains(@class, 'flex-row')]//a[contains(text(), 'DV21')]"),
                (By.XPATH, "//div[contains(@class, 'items-center')]//a[contains(text(), 'DV21')]")
            ]
            
            dv21_link = None
            for selector_type, selector in dv21_link_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector)
                    for element in elements:
                        if element.is_displayed() and "DV21" in element.text:
                            dv21_link = element
                            self.log(f"Found DV21 link: {element.text}")
                            break
                    if dv21_link:
                        break
                except Exception as e:
                    self.log(f"Error with DV21 link selector {selector}: {e}")
                
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
                
                # Take screenshot of the vehicle details page
                self.driver.save_screenshot('logs/astro_dv21_details.png')
                self.log(f"Current URL after clicking DV21 link: {self.driver.current_url}")
                
                # STEP 3: Find and click on "All Flights" link
                self.log("Looking for 'All Flights' link")
                all_flights_selectors = [
                    # Based on the HTML from screenshot - specific href attribute
                    (By.CSS_SELECTOR, "a[href='/flights?vehicle=1661&showRoute=true']"),
                    (By.XPATH, "//a[contains(@href, '/flights?vehicle=1661')]"),
                    # Based on text and class
                    (By.XPATH, "//a[contains(@class, 'button-link') and contains(text(), 'All Flights')]"),
                    (By.XPATH, "//a[text()='All Flights']"),
                    # Based on the section it appears in
                    (By.XPATH, "//h2[contains(text(), 'Recent flights')]/..//a[contains(text(), 'All Flights')]"),
                    # Most generic
                    (By.XPATH, "//*[contains(text(), 'All Flights')]")
                ]
                
                all_flights_link = None
                for selector_type, selector in all_flights_selectors:
                    try:
                        elements = self.driver.find_elements(selector_type, selector)
                        for element in elements:
                            if element.is_displayed() and "All Flights" in element.text:
                                all_flights_link = element
                                self.log(f"Found All Flights link: {element.text}")
                                break
                        if all_flights_link:
                            break
                    except Exception as e:
                        self.log(f"Error with All Flights link selector {selector}: {e}")
                
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
                    
                    # Take screenshot of the flights page
                    self.driver.save_screenshot('logs/astro_dv21_flights.png')
                    self.log(f"Current URL after clicking All Flights link: {self.driver.current_url}")
                    
                    # STEP 4: Find and click on the MXNT flight entry
                    self.log("Looking for MXNT flight entry")
                    mxnt_flight_selectors = [
                        # Based on the HTML from screenshot - specifically targeting MXNT flight
                        (By.XPATH, "//tr[contains(., 'MXNT')]"),
                        (By.XPATH, "//a[contains(., 'MXNT')]"),
                        (By.XPATH, "//td[contains(., 'MXNT')]/parent::tr"),
                        # More specific targeting based on class or structure
                        (By.XPATH, "//a[contains(@href, '/flights/') and contains(., 'MXNT')]"),
                        (By.CSS_SELECTOR, "a[href^='/flights/'][href*='MXNT']"),
                        # Most specific based on the exact structure seen in screenshot
                        (By.XPATH, "//span[contains(text(), 'MXNT')]/ancestor::tr"),
                        (By.XPATH, "//td//span[contains(text(), 'MXNT')]"),
                        # Look for the MXNT01 • #87 text pattern
                        (By.XPATH, "//td[contains(., 'MXNT') and contains(., '#')]")
                    ]
                    
                    mxnt_flight_element = None
                    for selector_type, selector in mxnt_flight_selectors:
                        try:
                            elements = self.driver.find_elements(selector_type, selector)
                            for element in elements:
                                if element.is_displayed() and "MXNT" in element.text:
                                    mxnt_flight_element = element
                                    self.log(f"Found MXNT flight element: {element.text}")
                                    break
                            if mxnt_flight_element:
                                break
                        except Exception as e:
                            self.log(f"Error with MXNT flight selector {selector}: {e}")
                    
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
                        
                        # Take screenshot of the flight details page
                        self.driver.save_screenshot('logs/mxnt_flight_details.png')
                        self.log(f"Current URL after clicking MXNT flight: {self.driver.current_url}")
                        
                        # STEP 5: Find and click on the "log" button
                        self.log("Looking for 'log' button")
                        log_button_selectors = [
                            # Based on the HTML from the new screenshot
                            (By.CSS_SELECTOR, "a[href*='/logs']"),
                            (By.XPATH, "//a[contains(@href, '/logs')]"),
                            # Based on the visible "log" text in the screenshot
                            (By.XPATH, "//a[text()='log']"),
                            (By.XPATH, "//span[text()='log']"),
                            (By.CSS_SELECTOR, "a.tab-item[href*='logs']"),
                            # Based on the "files" tab nearby
                            (By.XPATH, "//a[contains(@href, '/flights/') and contains(@href, '/logs')]"),
                            # More generic fallbacks
                            (By.XPATH, "//*[contains(text(), 'log') and not(contains(text(), 'login'))]"),
                            # The URL shown in the screenshot
                            (By.CSS_SELECTOR, "a[href='https://suite.auterion.com/flights/01JSCNXARJVCSG3PZV6MXNTQT/logs']")
                        ]
                        
                        log_button = None
                        for selector_type, selector in log_button_selectors:
                            try:
                                elements = self.driver.find_elements(selector_type, selector)
                                for element in elements:
                                    if element.is_displayed():
                                        # Check if the element contains 'log' text but not as part of a longer word
                                        text = element.text.lower()
                                        if "log" in text and not any(x in text for x in ["login", "logout", "catalog"]):
                                            log_button = element
                                            self.log(f"Found log button: {element.text if element.text else element.get_attribute('href')}")
                                            break
                                if log_button:
                                    break
                            except Exception as e:
                                self.log(f"Error with log button selector {selector}: {e}")
                        
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
                            
                            # Take screenshot of the logs page
                            self.driver.save_screenshot('logs/mxnt_flight_logs.png')
                            self.log(f"Current URL after clicking log button: {self.driver.current_url}")
                            
                            # STEP 6: Find and click on "View Analytics" button
                            self.log("Looking for 'View Analytics' button")
                            view_analytics_selectors = [
                                # Based on the HTML from the newest screenshot
                                (By.XPATH, "//span[contains(text(), 'View Analytics')]"),
                                (By.XPATH, "//a[contains(text(), 'View Analytics')]"),
                                # Based on the visible text in the screenshot
                                (By.XPATH, "//*[contains(text(), 'View Analytics')]"),
                                # Based on the structure in the HTML
                                (By.CSS_SELECTOR, "a.button-default span"),
                                (By.CSS_SELECTOR, "span.whitespace-nowrap"),
                                # From the HTML, the link appears to have a specific structure
                                (By.XPATH, "//a[@data-v-7131a226]"),
                                (By.XPATH, "//div[@class='self-center ml-auto']//a"),
                                # Direct reference to the button/link
                                (By.CSS_SELECTOR, "a.button-default")
                            ]
                            
                            view_analytics_button = None
                            for selector_type, selector in view_analytics_selectors:
                                try:
                                    elements = self.driver.find_elements(selector_type, selector)
                                    for element in elements:
                                        if element.is_displayed() and "View Analytics" in element.text:
                                            view_analytics_button = element
                                            self.log(f"Found View Analytics button: {element.text}")
                                            break
                                    if view_analytics_button:
                                        break
                                except Exception as e:
                                    self.log(f"Error with View Analytics button selector {selector}: {e}")
                            
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
                                
                                # Take screenshot of the analytics page
                                self.driver.save_screenshot('logs/mxnt_flight_analytics.png')
                                self.log(f"Current URL after clicking View Analytics button: {self.driver.current_url}")
                                
                                # STEP 7: Find and click on the "Download log" button
                                self.log("Looking for 'Download log' button")
                                download_log_selectors = [
                                    # Based on the HTML from the newest screenshot
                                    (By.XPATH, "//span[contains(text(), 'Download log')]"),
                                    (By.XPATH, "//button[contains(., 'Download log')]"),
                                    # Based on the search bar at the bottom of the page
                                    (By.CSS_SELECTOR, "input[placeholder='Download log']"),
                                    (By.XPATH, "//input[@placeholder='Download log']"),
                                    # Based on the visible text in the screenshot
                                    (By.XPATH, "//span[text()='Download log']"),
                                    # Based on the form element in the HTML
                                    (By.CSS_SELECTOR, "form[method='post'][action*='/api/logs/'][target='_blank']"),
                                    (By.XPATH, "//form[@method='post' and @action[contains(., '/api/logs/')]]/button"),
                                    # Direct reference to the button/link with SVG icon
                                    (By.CSS_SELECTOR, "button.button-default.w-full"),
                                    (By.XPATH, "//svg[@role='log']/ancestor::button"),
                                    # Most generic approach
                                    (By.XPATH, "//*[contains(text(), 'Download')]")
                                ]
                                
                                download_log_button = None
                                for selector_type, selector in download_log_selectors:
                                    try:
                                        elements = self.driver.find_elements(selector_type, selector)
                                        for element in elements:
                                            if element.is_displayed():
                                                if "Download" in element.text:
                                                    download_log_button = element
                                                    self.log(f"Found Download log button: {element.text}")
                                                    break
                                                elif element.get_attribute("placeholder") and "Download" in element.get_attribute("placeholder"):
                                                    download_log_button = element
                                                    self.log(f"Found Download log input: {element.get_attribute('placeholder')}")
                                                    break
                                        if download_log_button:
                                            break
                                    except Exception as e:
                                        self.log(f"Error with Download log button selector {selector}: {e}")
                                
                                # If we found the Download log button, click on it
                                if download_log_button:
                                    self.log("Clicking on 'Download log' button")
                                    download_log_button.click()
                                    
                                    # Wait a moment for the download to start
                                    time.sleep(5)
                                    
                                    # Take a screenshot after clicking download
                                    self.driver.save_screenshot('logs/log_download_initiated.png')
                                    self.log("Screenshot taken after initiating log download")
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
            self.driver.save_screenshot('logs/navigation_error.png')
    
    def log_vehicles_page_info(self):
        """
        Log information about the content of the Vehicles page.
        """
        self.log("--- VEHICLES PAGE CONTENT ---")
        
        # Log page title
        try:
            page_title = self.driver.title
            self.log(f"Page title: {page_title}")
        except:
            self.log("Could not get page title")
        
        # Get all headings
        try:
            headings = self.driver.find_elements(By.XPATH, "//h1 | //h2 | //h3 | //h4")
            self.log(f"Found {len(headings)} headings on the page")
            for i, heading in enumerate(headings):
                if heading.is_displayed():
                    self.log(f"Heading {i}: {heading.text}")
        except Exception as e:
            self.log(f"Error getting headings: {e}")
        
        # Get vehicle information from tables or lists
        try:
            # Try to find vehicle elements - adjust selectors based on actual page structure
            vehicle_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.vehicle-item, tr.vehicle-row")
            self.log(f"Found {len(vehicle_elements)} vehicle elements")
            
            # If no specific vehicle elements found, try to get table data
            if not vehicle_elements:
                tables = self.driver.find_elements(By.TAG_NAME, "table")
                self.log(f"Found {len(tables)} tables")
                
                for t, table in enumerate(tables):
                    if table.is_displayed():
                        rows = table.find_elements(By.TAG_NAME, "tr")
                        self.log(f"Table {t}: Found {len(rows)} rows")
                        
                        # Get headers
                        headers = table.find_elements(By.TAG_NAME, "th")
                        if headers:
                            header_texts = [h.text for h in headers if h.text.strip()]
                            self.log(f"Table {t} headers: {' | '.join(header_texts)}")
                        
                        # Get row data
                        for i, row in enumerate(rows[:10]):  # Log up to 10 rows
                            cells = row.find_elements(By.TAG_NAME, "td")
                            if cells:
                                cell_texts = [c.text.strip() for c in cells]
                                self.log(f"Vehicle {i}: {' | '.join(cell_texts)}")
            else:
                # Log information about each vehicle
                for i, vehicle in enumerate(vehicle_elements[:10]):  # Log up to 10 vehicles
                    self.log(f"Vehicle {i}: {vehicle.text}")
        
        except Exception as e:
            self.log(f"Error getting vehicle information: {str(e)}", logging.ERROR)
        
        # Save page source
        try:
            with open('logs/vehicles_page.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            self.log("Saved Vehicles page source to logs/vehicles_page.html")
        except Exception as e:
            self.log(f"Error saving page source: {str(e)}", logging.ERROR)
    
    def navigate_to_logs(self):
        """
        Navigate to the logs page and extract information.
        
        This method is called after successful login to navigate to the logs page
        and transfer control to Scrapy for downloading log files.
        
        Returns:
            list: Scrapy Request objects for further processing
        """
        # Get cookies from Selenium
        self.log("Getting cookies from browser")
        selenium_cookies = self.driver.get_cookies()
        
        # Navigate to the logs page
        self.log("Navigating to logs page")
        self.driver.get('https://suite.auterion.com/logs')
        time.sleep(3)
        
        # Take a screenshot of logs page
        self.driver.save_screenshot('logs/logs_page.png')
        self.log("Saved screenshot of logs page")
        
        # Extract URL after login
        log_page_url = self.driver.current_url
        self.log(f"Logs page URL: {log_page_url}")
        
        # Create cookie dictionary for Scrapy
        cookies_dict = {cookie['name']: cookie['value'] for cookie in selenium_cookies}
        
        # Now use Scrapy to continue
        self.log("Transferring control to Scrapy for further processing")
        yield scrapy.Request(
            url=log_page_url,
            cookies=cookies_dict,
            callback=self.parse_logs_page,
            dont_filter=True
        )
    
    def parse_logs_page(self, response):
        """
        Process the logs page HTML to find log file links.
        
        Args:
            response (scrapy.Response): The response containing the logs page HTML
            
        Yields:
            scrapy.Request: Requests to download individual log files
        """
        # Extract log file links
        self.log("Processing logs page with Scrapy")
        
        # Find all links to log files (adjust selector based on actual HTML)
        log_links = response.css('a[href*=".log"]::attr(href)').getall()
        
        if not log_links:
            self.log("No log links found. Check the CSS selector.", logging.WARNING)
        else:
            self.log(f"Found {len(log_links)} log files")
        
        for link in log_links:
            # Make absolute URL if needed
            if not link.startswith('http'):
                link = response.urljoin(link)
            
            self.log(f"Requesting log file: {link}")
            yield scrapy.Request(
                url=link,
                callback=self.save_log_file
            )
    
    def save_log_file(self, response):
        """
        Save a downloaded log file to disk.
        
        Args:
            response (scrapy.Response): The response containing the log file data
            
        Returns:
            dict: Information about the saved file
        """
        # Create logs directory if it doesn't exist
        os.makedirs('logs/downloaded', exist_ok=True)
        
        # Save the log file
        filename = response.url.split('/')[-1]
        file_path = f'logs/downloaded/{filename}'
        
        with open(file_path, 'wb') as f:
            f.write(response.body)
        
        self.log(f'Saved log file: {filename}')
        
        # Return information about the saved file
        return {
            'filename': filename,
            'path': file_path,
            'url': response.url,
            'size': len(response.body)
        }