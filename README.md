# Maximo GUI Connector for Python
A small package that uses Selenium to automate the most basic operations you could do on IBM Maximo Asset Management

## Installation
1. Install the **package** by typing  `pip install maximo-gui-connector`
2. Download the **chromedriver** (see [this note](#IMPORTANT)) matching your browser version and put it into **PATH**

You can include the package into your script and use it like this: 
```python
import maximo_gui_connector as MGC

YOUR_USERNAME = ""
YOUR_PASSWORD = ""
YOUR_GROUP = ""

if __name__ == "__main__":
	try:
		maximo = MGC.MaximoAutomation({ "debug": False, "headless": False })
		maximo.login(YOUR_USERNAME, YOUR_PASSWORD)

		maximo.goto_section("changes")
		maximo.setFilters({ "status": "!=REVIEW", "owner group": YOUR_GROUP })

		print(maximo.getAllRecordsFromTable())

		maximo.logout()

	except Exception as e:
		print(e)

	finally:
		print()
		input("Press any key to stop the script and close chrome")

		maximo.close()

```

### IMPORTANT
As of now (v. 0.0.1) this package **only** allows to use the **Chromedriver** (which MUST be installed). The possibility to change the browser is in roadmap.
