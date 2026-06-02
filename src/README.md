# Subprojects Directory

## Overview
The `src/` folder contains subprojects — modular components of the MAIN-PROJECT. Each subproject inherits rules and conventions from the MAIN-PROJECT but may define its own specifics.

### Adding a New Subproject
1. Choose the appropriate template for your language:
   - **Generic (any language)**: `cp -r .agents/templates/subproject-template/subproject-generic src/<subproject>/`
   - **Python**: `cp -r .agents/templates/subproject-template/subproject-python src/<subproject>/`
2. Rename the source directory to match your subproject name following your language's convention
3. Update the config file and `README.md` with the new subproject details

## Available Subprojects

| Subproject | Description |
|------------|-------------|
| [opencode-tool](opencode-tool/) | Python CLI for OpenCode server management |
