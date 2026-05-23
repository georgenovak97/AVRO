#### Tools

- **Family Browser** — browse and load Revit families from your local library
  ![Family Browser](familybrowser.jpg)
	- Browse folders with `.rfa` files and thumbnail previews
	- Folder tree with multiple levels
	- Search by name
	- Left double-click or "Load" button — load family into project
	- Right double-click — open family location in Windows Explorer
	- Place in model with return to the browser window
	- Recent files list
	- Dark/light theme
	- Library path is saved to `%APPDATA%\pyRevit\AVRO\config.json`
	
---
#### Installation

1. Copy the `AVRO.extension` folder to `%APPDATA%\pyRevit\Extensions\`  
   (or add it via **pyRevit → Settings → Custom Extension Directories**).
2. Reload pyRevit (**Reload**).
3. In the Revit ribbon: tab **"AVRO"** → panel **"Tools"** → **"Family Browser"**.

---
#### First Launch

1. Go to the **"AVRO"** tab in Revit.
2. Open **"Family Browser"**.
3. Click **"Library"** and select the root folder with your families.
4. Wait for the cache to load.

---
#### Requirements

- pyRevit 4.8+
- Revit 2020+