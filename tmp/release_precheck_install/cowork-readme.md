# Microsoft Copilot Cowork plugin scaffold

This folder was generated to match the Cowork packaging model:
- `manifest.json`
- `skills/sive/SKILL.md`
- icons (`color.png` 192x192 and `outline.png` 32x32)

Before packaging:
1. Replace `manifest.json` `id` with your stable GUID.
2. Add required icons: `color.png` and `outline.png`.
3. (Optional) add `agentConnectors` if you use a remote HTTPS MCP server.

Create zip from this folder root (manifest/icons/skills at zip root).
Example PowerShell:
Compress-Archive -Path manifest.json, color.png, outline.png, skills -DestinationPath sive-cowork.zip