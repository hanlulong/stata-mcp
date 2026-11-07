# Using the Stata MCP Server via Command Line

This guide explains how to run and use the Stata Model Context Protocol (MCP) server directly from the command line.

## Prerequisites

1. Ensure you have the required packages installed (from the extension or repository folder):
   ```
   pip install -r src/requirements.txt
   ```

2. Make sure Stata is installed and accessible on your system

## Running the Server Manually

### Option 1: Using the Included Script

The extension provides a Node script to start the server manually:

```bash
cd /path/to/extension
node ./src/start-server.js
```

This will start the MCP server on the default port (4000).

### Option 2: Running the Python Server Directly

You can also run the Python server script directly:

```bash
cd /path/to/extension
python src/stata_mcp_server.py --port 4000 --stata-path "/path/to/stata" --stata-edition mp
```

Command line arguments:
- `--port`: Port to run the server on (default: 4000)
- `--stata-path`: Path to your Stata installation
- `--stata-edition`: Stata edition to use: `mp`, `se` or `be` (default: `mp`)
- `--log-file`: Path to save logs (optional)
- `--log-level DEBUG`: Enable debug logging (optional; default `INFO`)

## Testing the Server Connection

Once the server is running, you can test it with:

```bash
curl http://localhost:4000/health
```

You should receive a JSON response indicating the server is running.

## Using with Cursor AI

To use the server with Cursor:

1. Create or update the MCP configuration file:
   ```
   ~/.cursor/mcp.json
   ```

2. Add the following configuration:
   ```json
   {
     "mcpServers": {
       "stata-mcp": {
         "url": "http://localhost:4000/mcp",
         "transport": "sse"
       }
     }
   }
   ```

3. Restart Cursor to apply the changes

## Available Endpoints

The server provides the following HTTP endpoints:

- `GET /health`: Server health check and status
- `POST /v1/tools`: Execute Stata tools/commands
- `/mcp-streamable`: MCP over Streamable HTTP (preferred)
- `GET /mcp`: MCP over SSE (legacy)
- `GET /docs`: Interactive API documentation (Swagger UI)

## Troubleshooting

If you encounter issues:

1. Check that the server is running with `curl http://localhost:4000/health`
2. Verify that your Stata path is correct
3. Look at the server logs for specific error messages
4. Ensure Python dependencies are properly installed

## Credits

Developed by Lu Han
Published by DeepEcon 
