# Contributing to Stata MCP Extension

Thank you for your interest in contributing to the Stata MCP Extension for VS Code! This guide will help you get started with the development process.

## Prerequisites

- Node.js (v18 or higher)
- Python (v3.11 or higher)
- Stata (for testing)
- Git

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/hanlulong/stata-mcp.git
   cd stata-mcp
   ```

2. Install dependencies:
   ```
   npm install
   ```
   This will also install the required Python dependencies.

3. Configure your system:
   - Ensure Stata is installed and accessible on your system
   - Update the settings in VS Code to point to your Stata installation

## Development Workflow

1. Make your changes to the codebase
2. Run tests to ensure everything is working:
   ```
   npm run test
   ```
3. Package the extension for testing:
   ```
   npm run package
   ```
4. Install the extension in VS Code by using the "Install from VSIX" option

## Testing the MCP Server

You can test the MCP server independently:

```
npm run test:mcp-server
```

To start the server manually:

```
npm run start-mcp-server
```

## Code Structure

- `extension.js` - The main VS Code extension code
- `stata_mcp_server.py` - The FastAPI-based MCP server
- `scripts/` - Helper scripts for development and testing
- `.github/workflows/` - CI/CD workflow definitions

## Pull Request Process

1. Create a feature branch from `main`:
   ```
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and commit them with clear commit messages

3. Push your branch to GitHub:
   ```
   git push origin feature/your-feature-name
   ```

4. Open a pull request against the `main` branch

5. Ensure all CI checks pass

## Code Style

- Follow the existing code style in the project
- Use meaningful variable and function names
- Add comments for complex logic

## Release Process

Releases are managed by the project maintainer. When a new release is ready:

1. Update the version in `package.json`
2. Create a new release on GitHub
3. The CI will automatically build and attach the VSIX package to the release

## License

By contributing to this project, you agree that your contributions will be licensed under the project's MIT license.

## Maintainer

This project is maintained by Lu Han. 