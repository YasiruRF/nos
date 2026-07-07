# NOS Language Support for VS Code

This extension provides syntax highlighting and bracket matching support for the Node Orchestration System (NOS) DSL files (`.nos`, `.node`, `.interface`).

## Features

* **Keywords:** Highlights package declarations, nodes, publishers, subscribers, services, and actions.
* **Annotations:** Highlights custom constraints (such as `@topic`, `@qos`, `@client`, `@reentrant`, and `@range`).
* **Python Code Injection:** Safely delegates and embeds full Python highlighting within all code execution blocks (`-> { ... }`).

## Manual Local Installation

To load the extension locally into your VS Code instance:

1. Copy or link this directory to your VS Code extensions directory:
   ```bash
   ln -s "/media/yasiru/New Volume/Praxis/NOS/nos/extensions/vscode-nos" ~/.vscode/extensions/vscode-nos
   ```
2. Restart VS Code.
3. Open any `.nos` file to see the highlighting active!
