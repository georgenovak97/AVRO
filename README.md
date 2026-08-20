[AVRO](https://avro.pro/en/) — BIM & IT Consulting by George Novak

#### Tools

- **Family Browser** — browse and load Revit families from a local or network library
  ![Family Browser](familybrowser.jpg)
	- Browse folders with `.rfa` files and thumbnail previews
	- Folder tree with multiple levels
    - Search by name, folder, and Revit version
    - Family properties and quality constraints are available from the properties view
    - Left-click — load and place the family in the project
    - Right-click — inspect family properties
	- Place in model with return to the browser window
    - Recent files list
    - Dark/light theme

  The former category, hosting, placement, and quality filter axes are not part of
  the current Family Browser UI.

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

Reloading a family that is already in the project intentionally overwrites its
parameter values through Revit's `IFamilyLoadOptions` callback.
