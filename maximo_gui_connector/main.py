"""
	Contains all the logic behind Maximo Automation
"""
import time
import re
import logging
import sys

import selenium
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

from webdriver_manager.chrome import ChromeDriverManager

# Just for Debug
import json

import maximo_gui_connector.constants as constants

# cSpell:includeRegExp #.*
# cSpell:includeRegExp ("""|''')[^\1]*\1


# ----------------------------------------------------------------------------------------------------
# 
#											Main Class 
# 
# ----------------------------------------------------------------------------------------------------
class MaximoAutomation():
	"""
		Abstraction layer over IBM Maximo Asset Management UI
	"""

	debug = False
	headless = False

	sections_cache = {}
	
	def __init__(self, config: dict = {}):
		"""Establish a connection to Maximo

		Args:
			config (dict, optional): [description]. Defaults to {}.
			config.debug (bool, optional): Add verbosity and tweak config Webdriver to log more info
			config.headless (bool, optional): Whether to start
			config.driver (Webdriver, optional): If you have already defined a Webdriver instance, you can pass that using this argument.
		"""		


		chrome_flags = []

		"""
		From: https://docs.python.org/2/howto/logging.html
		
		Possible logging levels:
		- 	DEBUG	:	Detailed information, typically of interest only when diagnosing problems.
		- 	INFO 	:	Confirmation that things are working as expected.
		- 	WARNING	:	An indication that something unexpected happened, or indicative of some problem in the near future (e.g. ‘disk space low’). The software is still working as expected.
		- 	ERROR	:	Due to a more serious problem, the software has not been able to perform some function.
		- 	CRITICAL:	A serious error, indicating that the program itself may be unable to continue running.

		https://blog.muya.co.ke/configuring-multiple-loggers-python/
		"""
		self.logger = logging.getLogger(__name__)
		self.logger.addHandler(logging.NullHandler())
		
		self.debug = bool(config["debug"]) if "debug" in config else False

		# https://peter.sh/experiments/chromium-command-line-switches/#log-level
		if self.debug: 
			chrome_flags.append("--log-level=1") # Prints starting from DEBUG messages
			self.logger.setLevel(logging.DEBUG)

			self.logger.debug("Debug mode enabled")
		else:
			chrome_flags.append("--log-level=3") # Prints starting from CRITICAL messages
			self.logger.setLevel(logging.INFO)

		if not "driver" in config:
			self.logger.debug("Using default WebDriver instance")
			chrome_flags = chrome_flags + [
				# "--disable-extensions",
				"start-maximized",
				"--disable-gpu",
				"--ignore-certificate-errors",
				"--ignore-ssl-errors",
				#"--no-sandbox # linux only,
				# "--headless",
			]

			# If passed configuration contains headless
			self.headless = bool(config["headless"]) if "headless" in config else False
			
			# If the browser needs to be started as a headless browser
			if self.headless: 
				chrome_flags.append("--headless")

			# Create the Chrome Options
			chrome_options = Options()
			for flag in chrome_flags: chrome_options.add_argument(flag)

			# To remove "DevTools listening on ws:..." message (https://stackoverflow.com/a/56118790/8965861)
			if not self.debug:
				chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

			# Create the actual WebDriver instance
			self.driver = webdriver.Chrome( ChromeDriverManager().install(), options=chrome_options )

		else:
			self.logger.debug("Using custom WebDriver instance")

			self.driver = config["driver"]
			
		self.driver.get("https://ism.italycsc.com/UI/maximo/webclient/login/login.jsp")


		# Sub-class
		self.routeWorkflowDialog = RouteWorkflowInterface(self)

		


	
	def login (self, username: str, password: str):
		"""Logs the user into Maximo, using the provided credentials"""
		self.logger.info("Trying to log in...")
		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "j_username")))

		# Send data to the Login form
		self.driver.find_element_by_id("j_username").send_keys(username)
		self.driver.find_element_by_id("j_password").send_keys(password)

		if self.debug: self.logger.debug(f"Username/Password were sent to the login Form (using {username})")

		# Click the 'Login' button
		self.driver.find_element_by_css_selector("button#loginbutton").click()
		if self.debug: self.logger.debug("Clicked on Submit button")
		
		# Wait until Maximo has finished logging in
		try:
			if self.debug: self.logger.debug("Waiting until Maximo has finished logging in...")
			WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "titlebar_hyperlink_9-lbsignout")))
		except TimeoutException as e:
			login_dialog_title = self.driver.find_element_by_css_selector("div.dialog[role='main'] > .message")

			# If there is an error message raise a `MaximoLoginFailed` Exception
			if login_dialog_title:
				text_login_dialog_msg = self.driver.find_element_by_css_selector("div.dialog[role='main'] > .messageDesc").get_attribute("innerText")
				text_login_dialog_title = self.driver.find_element_by_css_selector("div.dialog[role='main'] > .message").get_attribute("innerText")

				self.logger.critical(f"{text_login_dialog_title}: {text_login_dialog_msg}")
				raise MaximoLoginFailed(f"{text_login_dialog_title}: {text_login_dialog_msg}")

			else:
				self.logger.exception(f"Timeout not handled occurred during login phase: {str(e)}")
				raise MaximoLoginFailed(f"Timeout not handled occurred during login phase: {str(e)}")
				
		except Exception as e:
			self.logger.critical("Unknown error occurred during login phase: " + str(e))
			raise MaximoLoginFailed("Unknown error occurred during login phase: " + str(e))

		self.waitUntilReady()

		self.logger.info("User successfully logged in")


	def logout (self):
		""" Performs the logout """
		# Maximo has a special constant (LOGOUTURL) containing the direct url that can be used to logout
		self.driver.execute_script("window.location = LOGOUTURL")
		
		# Wait until have finished logging out and the confirm button is present
		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#returnFrm > button#submit")))

		# Click on the Submit button 
		self.driver.find_element_by_id("submit").click()

		# Wait until the Login page is shown
		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "j_username")))
		self.logger.info("User successfully logged out\n\n")


	def close (self):
		""" Closes the Browser instance """
		self.driver.quit()


	def isReady(self):
		""" Returns whether or not Maximo is ready to be automated. """
		js_result = self.driver.execute_script("""
			return waitOn == false && !document.getElementById('m935819a1-longop_message');
		""")

		return bool(js_result)

	def waitUntilReady (self):
		""" Stops the execution of the script until Maximo is ready or no 'Long operation' dialog is present """
		WebDriverWait(self.driver, 30).until(EC.invisibility_of_element((By.ID, "wait")))
		
		if self.driver.find_elements_by_id("query_longopwait-dialog_inner_dialogwait"): 
			if self.debug: self.logger.debug("Long loading message box detected. Waiting more time...")
			WebDriverWait(self.driver, 30).until(EC.invisibility_of_element((By.ID, "query_longopwait-dialog_inner_dialogwait")))

			self.waitUntilReady()

		return self


	def get_sections (self, force_rescan: bool = False):
		""" Populate the cache ONLY the first time, so that it speeds up on the next calls """
		if len(self.sections_cache) != 0 and not force_rescan:
			return self.sections_cache

		# Reset sections cache in case we are forcing a rescan
		if force_rescan: self.sections_cache = []
		
		if self.debug: self.logger.debug("Sections cache is empty. Analyzing DOM...")
		
		# Send click to the GoTo button and wait for the sections to expand
		self.driver.find_element_by_id("titlebar-tb_gotoButton").click()
		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#menu0_changeapp_startcntr_a")))

		# Loop through every section and save it into the `self.sections_cache` property
		for section in self.driver.find_elements_by_css_selector("#menu0 li:not(.submenu) > a"): 
			originalText = section.get_attribute("innerText")
			
			# Strip useless strings
			text = re.sub(r'\(MP\)', '', originalText)
			text = re.sub(r'\s+', ' ', text).strip().lower()

			# Get HTML_Element data
			s_id = section.get_attribute("id") 
			s_href = re.sub(r'javascript:\s+', '', section.get_attribute("href"))

			self.sections_cache[text] = {
				"id": f"#{s_id}",
				"href": s_href,
				"name": originalText
			}

		if self.debug:
			self.logger.debug("Sections have been successfully cached. Next calls will be faster")

		return self.sections_cache


	def goto_section (self, section_name: str):
		""" 
			Goes to the one of the sections you can find under the GoTo Menu in Maximo (Ex. changes, problems...) 
			
			Args:
				section_name (str): Name of the section to open (Case Insensitive).

		"""
		# Get available sections
		sections = self.get_sections()
		
		# Loop through all the available sections and check if there is one that matches with the one provided to this method
		section_name_parsed = section_name.lower().replace("(MP)", "")
		if section_name_parsed in sections:
			self.driver.execute_script(sections[section_name_parsed]["href"])
			if self.debug: self.logger.debug(f"Clicked on section '{sections[section_name_parsed]['name']}'")

		else:
			raise Exception(f"Section '{section_name}' does not exist. The following were found:\n" + json.dumps(sections, sort_keys=True, indent=4))

		self.waitUntilReady()

		# Removed for compatibility in case a section doesn't have a quicksearch field
		# self.waitForInputEditable("#quicksearch")


	def goto_tab (self, tab_name: str):
		"""Goes to a specific tab inside an Incident/Change/Task detail page

		Args:
			tab_name (str): Name of the tab (Case Sensitive)
		"""
		self.driver.find_element_by_link_text(tab_name).click()
		self.waitUntilReady()
		self.logger.info(f"Changed tab to '{tab_name}'")
		
		
	def getMaximoInternalVariable(self, variable_name: str):
		"""Returns the value of a variable inside the Maximo JavaScript code

		Args:
			variable_name (str): The variable name

		Returns:
			any: The requested variable value
		"""
		return self.driver.execute_script(f"return {variable_name};")

	def getCurrentSection(self):
		"""
		Gets the name of the current section:
			- mp2activ		= Activities and Tasks(MP)
			- mp2change		= Changes (MP)
			- mp2inc		= Incidents (MP)
		"""
		return { 
			"target_id": 	self.getMaximoInternalVariable("APPTARGET").lower(),
			"app_label":	self.getMaximoInternalVariable("APP_KEY_LABEL")
		}

	def getAvailableFiltersInListView (self):
		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "m6a7dfd2f_tbod_ttrow-tr")))
		
		filters_found = {}
		
		for label in self.driver.find_elements_by_css_selector('#m6a7dfd2f_tbod_ttrow-tr th > [id$="_ttitle-lb"]'):
			filter_label = label.get_attribute("innerText").strip().lower()

			if filter_label == "": continue

			cell = label.find_element_by_xpath('..')

			filter_sort = cell.find_element_by_css_selector("img").get_attribute("alt")

			filter_label_id = cell.get_attribute("id")
			filter_id = ""
			filter_column_number = self.getColumnNumberFromId(filter_label_id)

			input_selector = "[headers='" + filter_label_id + "'] > input"
			try:
				filter_id = self.driver.find_element_by_css_selector(input_selector).get_attribute("id")
			except Exception:
				if self.debug: self.logger.debug(f"Couldn't find filter input for column '{filter_label}' ({input_selector})")

			filters_found[filter_label] = { "element_id": filter_id, "sorting": filter_sort, "column_number": filter_column_number }


		# if self.debug: self.logger.debug("Pretty printing filters found:\n" + json.dumps(filters_found, sort_keys=True, indent=4))

		return filters_found

	def setFilters (self, filter_config: dict):
		""" 
			Change filters for the change list

		Args:
			filter_config (dict): A key-value pair dictionary containing the filters to set in the form of "Filter Name" (key) / "Filter Value" (value)
		"""
		self.waitUntilReady()
		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "m6a7dfd2f_tbod_ttrow-tr")))
		
		filters_cache = self.getAvailableFiltersInListView()


		element = self.driver.find_element_by_id('m6a7dfd2f-ti_img')
		filters_enabled = element.get_attribute("src") != "tablebtn_filter_off.gif"

		if not filters_enabled:
			apri_filters = self.driver.find_element_by_id("m6a7dfd2f-lb2")
			ActionChains(self.driver).move_to_element(apri_filters).click(apri_filters).perform()


		for filter_name, filter_value in filter_config.items():
			if not filter_name.lower() in filters_cache:
				self.logger.warning(f"Filter name '{filter_name}' does not exist. The following filters were found:\n" + json.dumps(filters_cache, sort_keys=True, indent=4))
				continue
			if filters_cache[filter_name.lower()]["element_id"].strip() == "":
				self.logger.warning(f"Filter name '{filter_name}' is not editable:")
				continue


			self.driver.find_element_by_css_selector("[id='" + filters_cache[filter_name.lower()]["element_id"] + "']").send_keys(filter_value)
			self.driver.find_element_by_css_selector("[id='" + filters_cache[filter_name.lower()]["element_id"] + "']").send_keys(Keys.TAB)
			if self.debug: self.logger.debug(f"Filter '{filter_name}' was set with value '{filter_value}'")
			time.sleep(0.25)
			
		time.sleep(0.5)

		self.logger.info(f"Filters successfully set")
		self.driver.find_element_by_id("m6a7dfd2f-ti2_img").click()
		self.waitUntilReady()

		# Sometimes for long searches a dialog is shown
		if self.driver.find_elements_by_id("m4b77cc6f-pb"):
			WebDriverWait(self.driver, 30).until(EC.invisibility_of_element_located((By.ID, "m4b77cc6f-pb")))
			self.waitUntilReady()


	def quickSearch(self, resource_id: str):
		"""Performs a Quick Search using the field at the top left corner of the view

		Args:
			resource_id (str): The ID of the resource to search (ex. INxxxxxx or CHxxxxxxx)

		Returns:
			bool: True if at least one record was found
		"""
		self.waitUntilReady()
		self.waitForInputEditable("#quicksearch")
		self.driver.find_element_by_id("quicksearch").clear()
		self.driver.find_element_by_id("quicksearch").send_keys(resource_id.strip())
		
		self.driver.find_element_by_id("quicksearchQSImage").click()

		self.logger.info(f"Searching for id: {resource_id}")
		
		self.waitUntilReady()
		if self.driver.find_elements_by_id("m88dbf6ce-pb") and "No records were found that match the specified query" in self.driver.find_element_by_id("mb_msg").get_attribute("innerText"):
			self.logger.error(f"Cannot find requested id: '{resource_id}'")
			return False
		
		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "m397b0593-tabs_middle")))

	def advancedSearch(self, params: dict, submitForm: bool = True):
		"""Performs an Advanced Search

		Args:
			params (dict): The data to send
			submitForm (bool): The data to send

		"""
		self.waitUntilReady()

		self.logger.debug(f"Performing advanced search with params: '{params}'")

		WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "quicksearchQSMenuImage")))
		self.driver.find_element_by_id("quicksearchQSMenuImage").click()
		self.waitUntilReady()

		# Popup content is generated dynamically. Wait for it to open
		WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "menu0_SEARCHMORE_OPTION_a")))
		self.driver.find_element_by_id("menu0_SEARCHMORE_OPTION_a").click()
		self.waitUntilReady()

		# Wait for it to load
		WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.ID, "maa8a5ebf-pb")))

		for key, value in params.items():
			self.setNamedInput({ key: value })

		if submitForm:
			# Find with the provided filters
			self.driver.find_element_by_id("maa8a5ebf-pb").click()
			self.waitUntilReady()


	def getBrowserInstance(self):
		"""
			Returns the Selenium Webdriver instance needed to perform operations in the current 
		"""
		return self.driver

	def getColumnNumberFromId(self, row_id):
		"""
		Given an id of a table row/field, returns the column number 

		Args:
			row_id (str): The column HTML element ID

		Returns:
			int: The column number
		"""
		regex_result = re.search("\[C:([0-9]+)\]", row_id)
		if regex_result: 
			return regex_result.groups(1)[0].strip()
		else:
			return None
		

	def getTableRows (self): 
		return self.driver.execute_script("""
			return document.querySelectorAll("#m6a7dfd2f_tbod-tbd tr.tablerow[id^='m6a7dfd2f_tbod_tdrow-tr']")
		""")



	# Table Methods
	def getTableHeaders (self): 
		return self.driver.execute_script("""
			let columns = document.querySelectorAll("#m6a7dfd2f_tbod_ttrow-tr th");
			let headers = Array.from(columns).reduce((accum, curr) => {
				let text = curr.innerText.trim();
				if (text) accum.push({ id: curr.cellIndex, text: text });
		
				return accum;
			}, [])
		
			return headers;
		""")

	def getTableRowsAll (self):
		return self.driver.execute_script("""
			function getTableHeaders () {
				let columns = document.querySelectorAll("#m6a7dfd2f_tbod_ttrow-tr th");
				let headers = Array.from(columns).reduce((accum, curr) => {
					let text = curr.innerText.trim();
					if (text) accum.push({ id: curr.cellIndex, text: text });
			
					return accum;
				}, [])
			
				return headers;
			}

			function getTableRowsDetails () {
				let data = [];
				
				// Prendo gli header
				let headers = getTableHeaders();
				console.log("Headers: %o", headers)

				// Prendo i dati per ogni riga
				document.querySelectorAll("#m6a7dfd2f_tbod-tbd tr.tablerow[id^='m6a7dfd2f_tbod_tdrow-tr[']").forEach(r => {
					columns = Array.from(r.querySelectorAll("td")).map(c => {
						return {
							"id": c.cellIndex,
							"text": c.innerText.trim()
						}
					}).filter(column => { 
						// Prendo solo i dati che hanno un rispettivo header
						return headers.some(header => column.id === header.id)
					}).reduce((final, column) => {
						// Associo ad ogni colonna il rispettivo nome
						let header_text = headers.find(h => column.id === h.id).text;
						final[header_text] = column.text
						
						return final;
					}, {});

					data.push({
						"data": columns,
						"element_id": r.id
					});
				});
				
				return data;
			}
			
			
			return getTableRowsDetails ();
		""")

	def getRecordDetailsFromTable (self, record: selenium.webdriver.remote.webelement.WebElement, filters, required_fields: list = []):
		"""When inside a Section with a Table list (ex. when inside the list of Changes open owned by my groups)

		Args:
			record (selenium.webdriver.remote.webelement.WebElement): The Selenium element of the current row
			required_fields (list): A list containing the fields to return. Defaults to [].

		Returns:
			[type]: [description]
		"""
		
		current_row = {}
		for column in record.find_elements_by_tag_name("td"):
			field = {
				"element_id": column.get_attribute("id").strip(),
				"value": column.text.replace("\n", "").strip(),
				"column_number": self.getColumnNumberFromId(column.get_attribute("id")),
				"column_name": ""
			}



			# Find the filter column name associated to the current field
			for key, values in filters.items():
				if values["column_number"] == field['column_number']:
					field['column_name'] = key.strip()
					break

			# Add the current field to the list of fields ONLY if it has both a valid column name and a valid value
			if field['column_name'] != "" and field['value'] != "":
				current_row[field['column_name']] = field
			
		return current_row

	def getAllRecordsFromTable (self):
		"""
		In a List View (for example 'Changes open owned by my groups') analyzes the current table and returns all the rows details. 
		If there are more pages, goes through all them

		Returns:
			list: List of Dictionaries of all the table rows 
		"""
		start = time.time()

		record_list = []

		while True:
			counter = self.driver.find_element_by_id("m6a7dfd2f-lb3").get_attribute("innerText").strip()

			self.logger.info(f"[Paging] Analyzing records for page: {counter}")

			table_rows = self.getTableRowsAll()
			record_list.extend(table_rows)

			# If more pages are found, continue with the next cycle
			next_page_available = self.driver.find_element_by_id("m6a7dfd2f-ti7_img").get_attribute("source") == "tablebtn_next_on.gif"
			if not next_page_available: break

			if self.debug: self.logger.debug("[Paging] Changing page...")

			# Click on the Arrow icon to change page
			self.driver.find_element_by_id("m6a7dfd2f-ti7_img").click()
			self.waitUntilReady()

		return record_list

	def getRowNumberFromFieldId(self, row_id: str):
		"""Given a field from a table row (ex. Changes) or even a row, returns the row number

		Args:
			row_id (str): The id of the element you want to find the row number

		Returns:
			str: The row number
		"""
		return str(self.driver.execute_script("return getRowFromId(arguments[0])", row_id))






	def waitForInputEditable(self, element_selector: str, timeout: int = 30):
		"""
		Waits for an input/textarea to be editable

		Args:
			element_selector (str): The CSS element selector
			timeout (int, optional): The timeout after which an error is thrown. Defaults to 30.
		"""
		# Waits until Maximo is ready (input wouldn't be ready anyway)
		#
		self.waitUntilReady()

		# Waits for the input to be visible
		# 
		# From the Docs:
		#		Visibility means that the element is not only displayed but also has a height and width that is greater than 0
		#
		WebDriverWait(self.driver, timeout).until(
			EC.visibility_of_element_located((By.CSS_SELECTOR, element_selector))
		)
		
		# Waits for the input not to be in readonly mode
		WebDriverWait(self.driver, timeout).until(
			lambda s: self.isInputEditable(element_selector)
		)

		return self.driver.find_element_by_css_selector(element_selector)


	def isInputEditable(self, element_selector: str):
		"""
		Checks whether an input/textarea is editable at the moment

		Args:
			element_selector (str): The CSS element selector
		"""
		# Waits until Maximo is ready (input wouldn't be ready anyway)
		#
		self.waitUntilReady()

		return "fld_ro" not in self.driver.find_element_by_css_selector(element_selector).get_attribute('class').split()

	def clickRouteWorkflow(self):
		self.driver.find_element_by_id("ROUTEWF__-tbb_anchor").click()
		self.waitUntilReady()

		foregroundDialog = self.getForegroundDialog()

		# TODO: Da portare all'interno dei singoli script per una migliore astrazione
		if foregroundDialog:
			if "Complete Workflow Assignment" in foregroundDialog["title"]:
				foregroundDialog["buttons"]["OK"].click()
				self.waitUntilReady()

			if self.driver.find_elements_by_id("msgbox-dialog_inner"):
				msg_box_text = self.driver.find_element_by_id("mb_msg").get_attribute("innerText").strip()

				if "Change SCHEDULED DATE is not reach to start Activity" in msg_box_text:
					btn_close = self.driver.find_element_by_id("m15f1c9f0-pb")
					btn_close.click()

					self.waitUntilReady()
					raise MaximoWorkflowError(f"Error while trying to route Workflow. Message: {msg_box_text}")



	def detectDialogs(self):
		"""
		Checks if there is any dialog on foreground
		
		Returns:
			List of Dictionaries
		"""
		dialogs = self.driver.execute_script(r"""
				function detectMaximoDialogs() {
					let data = [];

					document.querySelectorAll("[id$='-dialog_inner'").forEach(e => {
						// Solo il dialog in primo piano ha la classe 'wait_modal'. Lo prendo e controllo
						let wait_elem = document.getElementById(`${e.id}_dialogwait`);
						let is_in_front = wait_elem.classList.contains("wait_modal");

						let type = e.getAttribute("role")
						
						let dialog_head = e.querySelector("[id$='-dialog_content0']");
						let dialog_body = e.querySelector("[id$='-dialog_content1']");

						let title 	= dialog_head.innerText.trim();
						let body 	= dialog_body.querySelector("[id*='_bodydiv']");

						let buttons = Array.from(dialog_body.querySelectorAll("button.pb[type='button'][ctype='pushbutton']")).reduce((accum, curr_button) => {
							accum[curr_button.innerText.trim()] = curr_button;

							return accum;
						}, {})

						data.push({
							is_foreground: is_in_front,
							title: title,
							text: body.innerText.trim().replace(/\r?\n/, " ").trim(),
							type: type,
							buttons: buttons,
							html: {
								head: dialog_head,
								body: body,
								full_element: e
							}
						})
					});

					return data;
				};

				return detectMaximoDialogs();
			""")

		if dialogs:
			if self.debug: self.logger.debug(f"Found {len(dialogs)} dialog/s!")

		return dialogs

	def getForegroundDialog(self):
		"""Returns the foreground dialog

		Returns:
			Dict: Dictionary containing details of the foreground dialog
		"""
		return next((item for item in self.detectDialogs() if item["is_foreground"] == True), None)


	def setNamedInput(self, targets: dict):
		"""Sets the value of a named input in the current view
		

		Args:
			targets (dict): The EXACT label text you want to search
		"""
		MAX_RETRY_TIMES = 5

		retries = 1
		while retries <= MAX_RETRY_TIMES:
			retries += 1

			try:
				for label in self.driver.find_elements_by_css_selector("label.text.label"):
					if not label.get_attribute("innerText") or label.get_attribute("innerText").strip() == "": 
						continue

					if len(label.get_attribute("class").split()) != 2: 
						continue

					if not label.get_attribute("for") or label.get_attribute("for").strip() == "": 
						continue

					label_text = label.get_attribute("innerText").strip()
					if label_text in targets:
						input_id = label.get_attribute("for")

						if not self.driver.find_elements_by_id(input_id):
							self.logger.error(f"No inputs are bound to the label named '{label_text}'")
							
							continue
						
						self.logger.debug(f"Now waiting for it to be editable")

						self.waitForInputEditable(f"#{input_id}")

						self.driver.find_element_by_id(input_id).clear()
						self.driver.find_element_by_id(input_id).send_keys(targets[label_text])
						self.driver.find_element_by_id(input_id).send_keys(Keys.TAB)

						self.waitUntilReady()
						time.sleep(0.5)
						if self.debug: self.logger.debug(f"Value '{targets[label_text]}' was set for named input '{label_text}'")

						del targets[label_text]
				
					if not targets:
						if self.debug: self.logger.debug("No more targets. Finished my job")
						break

				self.waitUntilReady()
				break
			except StaleElementReferenceException:
				if self.debug: self.logger.debug(f"Page changed while trying to access input element ({retries} attempt of {MAX_RETRY_TIMES} MAX)")
				time.sleep(0.5)
		else:
			msg = f"Reached maximum retries number ({MAX_RETRY_TIMES}) while trying to set input value"
			self.logger.error(msg)

			raise MaximoError(msg)


	def getNamedInput(self, target: str):
		"""Gets the element of a named input in the current view
		

		Args:
			target (str): The EXACT label text you want to search
		"""
		for label in self.driver.find_elements_by_css_selector("label.text.label"):
			if len(label.get_attribute("class").split()) != 2 or not label.get_attribute("for").strip(): 
				continue
			
			label_text = label.get_attribute("innerText").strip()
			if label_text == target.strip():
				input_id = label.get_attribute("for")

				if not self.driver.find_elements_by_id(input_id):
					self.logger.error(f"No inputs are bound to the label named '{label_text}'")
					
					continue
				
				return self.driver.find_element_by_id(input_id)
		else:
			raise Exception("Element not found")
		
	def getNamedLabel(self, target: str):
		"""Gets the element of a named input in the current view

		Args:
			target (str): The EXACT label text you want to search
		"""
		for label in self.driver.find_elements_by_css_selector(".anchor.text.label"):
			""" if len(label.get_attribute("class").split()) != 2 or not label.get_attribute("for").strip(): 
				continue """
			
			label_text = label.get_attribute("innerText").strip()
			if label_text == target.strip():				
				return label
		else:
			raise Exception("Element not found")

	def handleIfComingFromDetail(self):		
		foregroundDialog = self.getForegroundDialog()

		if foregroundDialog and "Do you want to save your changes before continuing?" in foregroundDialog["text"]:
			if self.debug: self.logger.debug(f"MsgBox has appeared: {foregroundDialog['text']}")

			foregroundDialog["buttons"]["No"].click()
			if self.debug: self.logger.debug("Clicked on 'No'")

			self.waitUntilReady()


	def checkUpdateError(self):
		foregroundDialog = self.getForegroundDialog()

		if foregroundDialog and "has been updated by another user. Your changes have not been saved. Refresh the record and try again" in foregroundDialog["text"]:
			foregroundDialog["buttons"]["OK"].click()
			self.waitUntilReady()

			return True

		return False


# ----------------------------------------------------------------------------------------------------
# 
#											Interfaces 
# 
# ----------------------------------------------------------------------------------------------------
class RouteWorkflowInterface():
	def __init__(self, maximo):
		self.__maximo = maximo

	def openDialog(self):
		"""Click on the "Change Status" button

		Raises:
			MaximoError: If cannot find the button
		"""
		if not self.__maximo.driver.find_elements_by_link_text("Change Status/Group/Owner (MP)"):
			self.__maximo.logger.critical("No 'Change Status/Group/Owner (MP)' button was found")

			raise MaximoError("No 'Change Status/Group/Owner (MP)' button was found")
		# self.__maximo.driver.find_element_by_link_text("Change Status/Group/Owner (MP)").click()
		self.__maximo.driver.find_element_by_xpath("//span[contains(text(), 'Change Status/Group/Owner (MP)')]/parent::a").click()
		self.__maximo.waitUntilReady()

		self.__maximo.logger.info(f"Opened 'Change Status' dialog")

		return self

	def closeDialog(self):
		"""Click on "Close Window" button to close the dialog"""
		self.__maximo.driver.find_element_by_id("mbdb65f6b-pb").click()
		self.__maximo.waitUntilReady()

	def getStatus(self):
		"""Get the current Status"""
		
		return self.__maximo.getNamedInput("Status:").get_attribute("value")
		
	def setStatus(self, new_status: str):
		"""Sets a new status for the current record

		Args:
			new_status (str): The new status 
		"""
		self.__maximo.setNamedInput({ "New Status:": new_status })
		self.__maximo.waitUntilReady()

		return self

	def clickRouteWorkflow(self):
		"""Clicks on the 'Route Workflow' button, and checks if there are any errors

		Raises:
			MaximoWorkflowError: Exception occurred inside Maximo when trying to change the status

		Returns:
			[type]: [description]
		"""
		self.__maximo.driver.find_element_by_id("m24bf0ed1-pb").click()
		self.__maximo.waitUntilReady()
	
		if self.__maximo.driver.find_elements_by_id("msgbox-dialog_inner"):
			msg_box_text = self.__maximo.driver.find_element_by_id("mb_msg").get_attribute("innerText").strip()
			self.__maximo.logger.error(f"MsgBox has appeared: {msg_box_text}")

			button_ok = self.__maximo.driver.find_element_by_id("m88dbf6ce-pb")
			additional_error_text = ""

			if "Errors exist in the application that prevent this action from being performed" in msg_box_text:
				additional_error_text = f"Errors exist in the application. Your changes have not been saved\n"
				
			elif "has been updated by another user. Your changes have not been saved" in msg_box_text:
				additional_error_text = f"Record have been changed by another user/instance. Your changes have not been saved\n"
				
			elif "mp2# The transition of status from INPROG to CLOSE is not permitted." in msg_box_text:
				additional_error_text = f"Record have been changed by another user/instance. Your changes have not been saved\n"
			else:
				additional_error_text = ""
				self.__maximo.logger.warning("Error not handled by this script")

			if additional_error_text: self.__maximo.logger.error(additional_error_text)

			button_ok.click()
			self.__maximo.waitUntilReady()

			self.closeDialog()


			raise MaximoWorkflowError("Errors exist in the application. Your changes have not been saved")

		return self




# ----------------------------------------------------------------------------------------------------
# 
#											Exceptions 
# 
# ----------------------------------------------------------------------------------------------------
# 
# Source: 
# 	https://stackoverflow.com/a/60465422/8965861
#
class MaximoError(Exception):
    """A base class for Maximo exceptions."""

class MaximoWorkflowError(MaximoError):
	"""Exception raised when something in Maximo Workflow fails"""

	def __init__(self, *args, **kwargs):
		super().__init__(*args)
		self.foo = kwargs.get('foo')

class MaximoLoginFailed(MaximoError):
	"""Exception raised when something in Maximo Login fails"""

	def __init__(self, *args, **kwargs):
		super().__init__(*args)
		self.foo = kwargs.get('foo')
