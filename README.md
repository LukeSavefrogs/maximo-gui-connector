# Maximo-GUI-Automation-Python
A script written in Python/Selenium intended to be imported into other Python projects and used as a library

You can include the Library into your script and use it like this: 
```python
import maximo_gui_connector as MGC

if __name__ == "__main__":
	try:
		maximo = MGC.MaximoAutomation({ "debug": True })
		maximo.login(YOUR_USERNAME, YOUR_PASSWORD)

		maximo.goto_section("changes")
		maximo.setFilters({ "status": "!=REVIEW", "owner group": "V-OST-IT-SYO-OPS-TRENITALIA_ICTSM" })
		
		maximo.logout()
	
	except Exception as e:
		print(e)

	finally:
		print()
		input("Press any key to stop the script and close chrome")

		maximo.close()
```
