"""
	Contains all the logic behind Maximo Automation
"""
import selenium
import time
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
import re
import logging
import time
import sys

# Just for Debug
import json

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
	
	def __init__(self, config = {}):
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

		self.logger_consoleHandler = logging.StreamHandler(sys.stdout)
		self.logger_consoleHandler.setFormatter(logging.Formatter(fmt='[%(levelname)s] - %(message)s'))

		self.logger_fileHandler = logging.FileHandler(filename='MaximoPyAutomation.log')
		self.logger_fileHandler.setFormatter(logging.Formatter(fmt='[%(asctime)s] %(process)d - %(levelname)s - %(message)s', datefmt='%d-%m-%y %H:%M:%S'))

		# Add handlers to the logger
		self.logger.addHandler(self.logger_consoleHandler)
		self.logger.addHandler(self.logger_fileHandler)


		if "debug" in config:
			self.debug = bool(config["debug"])

			# https://peter.sh/experiments/chromium-command-line-switches/#log-level
			if self.debug: 
				chrome_flags.append("--log-level=1") # Prints starting from DEBUG messages

				# self.logger_consoleHandler.setLevel(logging.DEBUG) # Needed only for finer and different control
				self.logger.setLevel(logging.DEBUG)
				self.logger_fileHandler.setFormatter(logging.Formatter(fmt='[%(asctime)s] %(process)d (%(filename)s:%(funcName)s:%(lineno)d) - %(levelname)s - %(message)s'))

				self.logger.debug("Debug mode enabled")
			else:
				chrome_flags.append("--log-level=3") # Prints starting from CRITICAL messages

				# self.logger_consoleHandler.setLevel(logging.INFO)
				self.logger.setLevel(logging.INFO)

		if "headless" in config:
			self.headless = bool(config["headless"])
			if self.headless: chrome_flags.append("--headless")

		chrome_flags = chrome_flags + [
			# "--disable-extensions",
			"start-maximized",
			"--disable-gpu",
			"--ignore-certificate-errors",
			"--ignore-ssl-errors",
			#"--no-sandbox # linux only,
			# "--headless",
		]
		chrome_options = Options()
			
		for flag in chrome_flags:
			chrome_options.add_argument(flag)

		self.driver = webdriver.Chrome( options=chrome_options )
		self.driver.get("https://ism.italycsc.com/UI/maximo/webclient/login/login.jsp?appservauth=true")

		self.routeWorkflowDialog = RouteWorkflowInterface(self)

		


	
	def login (self, username, password):
		"""Logs the user into Maximo, using the provided credentials"""
		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "j_username")))

		self.driver.find_element_by_id("j_username").send_keys(username)
		self.driver.find_element_by_id("j_password").send_keys(password)

		if self.debug: self.logger.debug(f"Username/Password were sent to the login Form (using {username})")

		self.driver.find_element_by_css_selector("button#loginbutton").click()
		if self.debug: self.logger.debug("Clicked on Submit button")
		
		# Wait until Maximo has finished logging in
		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "titlebar_hyperlink_9-lbsignout")))
		self.waitUntilReady()

		self.logger.info("User successfully logged in")


	def logout (self):
		""" Performs the logout """
		""" 
			WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "titlebar_hyperlink_9-lbsignout")))
			self.driver.find_element_by_id("titlebar_hyperlink_9-lbsignout").click()
			if self.debug: print("Clicked on the logout button") 
		"""
		# Maximo has a special constant (LOGOUTURL) containing the direct url that can be used to logout
		self.driver.execute_script("window.location = LOGOUTURL")
		
		# Wait until have finished logging out and the confirm button is present
		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#returnFrm > button#submit")))

		# Click on the Submit button 
		self.driver.find_element_by_id("submit").click()

		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "j_username")))
		self.logger.info("User successfully logged out\n\n")


	def close (self):
		""" Closes the Browser instance """
		self.driver.quit()


	def isReady(self):
		""" Returns whether or not Maximo is ready to be automated """
		js_result = self.driver.execute_script("return waitOn == false && !document.getElementById('m935819a1-longop_message');")

		return bool(js_result)

	def waitUntilReady (self):
		""" Stops the execution of the script until Maximo is ready or no 'Long operation' dialog is present """
		WebDriverWait(self.driver, 30).until(EC.invisibility_of_element((By.ID, "wait")))
		
		if self.driver.find_elements_by_id("query_longopwait-dialog_inner_dialogwait"): 
			if self.debug: self.logger.debug("Long loading message box detected. Waiting more time...")
			WebDriverWait(self.driver, 30).until(EC.invisibility_of_element((By.ID, "query_longopwait-dialog_inner_dialogwait")))

			self.waitUntilReady()

		return self



	def goto_section (self, section_name):
		""" 
			Goes to the one of the sections you can find under the GoTo Menu in Maximo (Ex. changes, problems...) 
		"""
	
		""" Populate the cache ONLY the first time, so that it speeds up on the next calls """
		if len(self.sections_cache) == 0:
			if self.debug: self.logger.debug("Sections cache is empty. Analyzing DOM...")
			
			self.driver.find_element_by_id("titlebar-tb_gotoButton").click()
			WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#menu0_changeapp_startcntr_a")))


			for section in self.driver.find_elements_by_css_selector("#menu0 li:not(.submenu) > a"): 
				originalText = section.get_attribute("innerText")
				text = re.sub(r'\(MP\)', '', originalText)
				text = re.sub(r'\s+', ' ', text).strip().lower()
				s_id = section.get_attribute("id") 
				s_href = section.get_attribute("href") 

				self.sections_cache[text] = {
					"id": f"#{s_id}",
					"href": re.sub(r'javascript:\s+', '', s_href),
					"name": originalText
				}

			if self.debug:
				self.logger.debug("Sections have been successfully cached")

		section_name_parsed = section_name.lower().replace("(MP)", "")
		if section_name_parsed in self.sections_cache:
			self.driver.execute_script(self.sections_cache[section_name_parsed]["href"])
			self.logger.info(f"Clicked on section '{self.sections_cache[section_name_parsed]['name']}'")

		else:
			raise Exception(f"Section '{section_name}' does not exist. The following were found:\n" + json.dumps(self.sections_cache, sort_keys=True, indent=4))

		self.waitForInputEditable("#quicksearch")

	def goto_tab(self, tab_name):
		self.driver.find_element_by_link_text(tab_name).click()
		self.waitUntilReady()
		self.logger.info(f"Changed tab to '{tab_name}'")
		
		
	def getMaximoInternalVariable(self, variableName):
		return self.driver.execute_script(f"return {variableName};")

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
				self.logger.warning(f"Couldn't find filter input for column '{filter_label}' ({input_selector})")

			filters_found[filter_label] = { "element_id": filter_id, "sorting": filter_sort, "column_number": filter_column_number }


		# if self.debug: self.logger.debug("Pretty printing filters found:\n" + json.dumps(filters_found, sort_keys=True, indent=4))

		return filters_found

	def setFilters (self, filter_config):
		""" Change filters for the change list """
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
			self.logger.debug(f"Filter '{filter_name}' was set with value '{filter_value}'")
			
		self.logger.info(f"Filters successfully set")
		self.driver.find_element_by_id("m6a7dfd2f-ti2_img").click()
		self.waitUntilReady()

		if self.driver.find_elements_by_id("m4b77cc6f-pb"):
			WebDriverWait(self.driver, 30).until(EC.invisibility_of_element_located((By.ID, "m4b77cc6f-pb")))
			self.waitUntilReady()


	def quickSearch(self, resource_id):
		self.waitUntilReady()
		self.waitForInputEditable("#quicksearch")
		self.driver.find_element_by_id("quicksearch").clear()
		self.driver.find_element_by_id("quicksearch").send_keys(resource_id.strip())
		
		self.driver.find_element_by_id("quicksearchQSImage").click()

		if self.debug: self.logger.debug(f"Searching for id: {resource_id}")
		
		self.waitUntilReady()
		if self.driver.find_elements_by_id("m88dbf6ce-pb") and "No records were found that match the specified query" in self.driver.find_element_by_id("mb_msg").get_attribute("innerText"):
			self.logger.error(f"Cannot find requested id: '{resource_id}'")
		
		WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "m397b0593-tabs_middle")))

	def getBrowserInstance(self):
		"""
			Returns the Selenium Webdriver instance needed to perform operations in the current 
		"""
		return self.driver

	def getColumnNumberFromId(self, row_id):
		"""
		Given an id of a table row/field, returns the column number 

		Args:
			row_id ([type]): [description]

		Returns:
			[type]: [description]
		"""
		regex_result = re.search("\[C:([0-9]+)\]", row_id)
		if regex_result: 
			return regex_result.groups(1)[0].strip()
		else:
			return None
		pass

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
		record_list = []

		while True:
			counter = self.driver.find_element_by_id("m6a7dfd2f-lb3").get_attribute("innerText").strip()

			table_rows = self.driver.find_elements_by_css_selector("#m6a7dfd2f_tbod-tbd tr.tablerow[id*='tbod_tdrow-tr[R:']")

			if self.debug: self.logger.info(f"[Paging] Analyzing records for page: {counter}")

			filters = self.getAvailableFiltersInListView()

			
			for index, row in enumerate(table_rows): 
				record_list.append(
					{
						"data": self.getRecordDetailsFromTable(row, filters),
						"element_id": row.get_attribute("id")
					}
				)
				if self.debug: self.logger.debug("\tRow n." + str(index + 1))
			

			next_page_available = self.driver.find_element_by_id("m6a7dfd2f-ti7_img").get_attribute("source") == "tablebtn_next_on.gif"

			if not next_page_available: break

			if self.debug: self.logger.debug("[Paging] Changing page")
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
			lambda s:"fld_ro" not in s.find_element_by_css_selector(element_selector).get_attribute('class').split()
		)

		return self.driver.find_element_by_css_selector(element_selector)

	def clickRouteWorkflow(self):
		self.driver.find_element_by_id("ROUTEWF__-tbb_anchor").click()
		self.waitUntilReady()

	def setNamedInput(self, targets: dict):
		"""Sets the value of a named input in the current view
		

		Args:
			targets (dict): The EXACT label text you want to search
		"""
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
				self.logger.info(f"Value '{targets[label_text]}' was set for named input '{label_text}'")

				del targets[label_text]
		
			if not targets:
				self.logger.debug("No more targets. Finished my job")
				break

		self.waitUntilReady()


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
		self.__maximo.driver.find_element_by_id("m24bf0ed1-pb").click()
		self.__maximo.waitUntilReady()
	
		if self.__maximo.driver.find_elements_by_id("msgbox-dialog_inner"):
			msg_box_text = self.__maximo.driver.find_element_by_id("mb_msg").get_attribute("innerText").strip()
			self.__maximo.logger.error(f"MsgBox has appeared: {msg_box_text}")

			if "Errors exist in the application that prevent this action from being performed" in msg_box_text:
				# browser.find_elements_by_id("m88dbf6ce-pb").click()
				self.__maximo.logger.error(f"Errors exist in the application. Your changes have not been saved\n")

				raise MaximoWorkflowError("Errors exist in the application. Your changes have not been saved")

			if "has been updated by another user. Your changes have not been saved" in msg_box_text:
				# browser.find_elements_by_id("m88dbf6ce-pb").click()
				self.__maximo.logger.error(f"Record have been changed by another user/instance. Your changes have not been saved\n")
				
				raise MaximoWorkflowError("Errors exist in the application. Your changes have not been saved")

			if "mp2# The transition of status from INPROG to CLOSE is not permitted." in msg_box_text:
				# browser.find_elements_by_id("m88dbf6ce-pb").click()
				self.__maximo.logger.error(f"Record have been changed by another user/instance. Your changes have not been saved\n")
				
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
