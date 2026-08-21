[AVRO](https://avro.pro/en/) — BIM & IT Consulting by George Novak

#### Tools

- **Family Browser** — browse and load Revit families from a local or network library
  ![Family Browser](familybrowser.jpg)
	- Browse folders with `.rfa` files and thumbnail previews
	- Folder tree with multiple levels
    - Search by name, folder, and Revit version
    - Middle-click — open the family in Windows Explorer
    - Left-click — load and place the family in the project
    - Right-click — inspect family properties
	- Place in model with return to the browser window
    - Recent files list
    - Dark/light theme
    - Library and Refresh buttons for managing the family library

---
#### Installation
  ![Install](install.jpg)
1. Add `https://github.com/georgenovak97/AVRO.git` via **pyRevit → Extensions → Git URL → Add and install**.
2. In the Revit ribbon, open **"AVRO"** → **"Tools"** → **"Family Browser"**.

---
#### First Launch

1. Go to the **"AVRO"** tab in Revit.
2. Open **"Family Browser"**.
3. Click **"Library"** and select the root folder with your families.
4. Wait for the cache to load.

---
#### Requirements

- pyRevit 4.8+
- AVRO version 1.3
- Revit 2020–2025 (2026+ untested)

Reloading a family that is already in the project intentionally overwrites its
parameter values through Revit's `IFamilyLoadOptions` callback.
