[AVRO](https://avro.pro/en/) — BIM & IT Consulting by George Novak

#### Tools

- **Family Browser** — browse and load Revit families from a local or network library
  ![Family Browser](familybrowser.jpg)
	- Browse folders with `.rfa` files and thumbnail previews
	- Folder tree with multiple levels
	- Search by name
	- Filter axes: Revit category, hosting behavior, placement, Revit version
	- Constraints: shared family, work plane-based, no imported CAD, and limits on types, reference planes, formulas and file size
	- Inspect family properties: types, parameters, formulas
	- Left double-click or "Load" button — load family into project
	- Right double-click — open family location in Windows Explorer
	- Place in model with return to the browser window
	- Recent files list
	- Dark/light theme

---
#### Installation
  ![Install](install.jpg)
1. Add `https://github.com/georgenovak97/AVRO.git` via **pyRevit → Extensions → Git URL → Add and install**.
2. In the Revit ribbon: tab **"AVRO"** → panel **"Tools"** → **"Family Browser"**.

---
#### First Launch

1. Go to the **"AVRO"** tab in Revit.
2. Open **"Family Browser"**.
3. Click **"Library"** and select the root folder with your families.
4. Wait for the cache to load.

---
#### Requirements

- pyRevit 4.8+
- Revit 2020–2025 (2026+ untested)
