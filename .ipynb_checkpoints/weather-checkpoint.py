from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP
import sys
import logging
import os
import asyncio
import signal

# Configure logging to output to stderr with DEBUG level
logging.basicConfig(level=logging.DEBUG, stream=sys.stderr, format='%(asctime)s [%(levelname)s] %(message)s')

# Initialize FastMCP server
logging.debug("Initializing FastMCP server...")
try:
    mcp = FastMCP("weather")
    logging.debug("FastMCP server initialized successfully")
except Exception as e:
    logging.error(f"Failed to initialize FastMCP server: {str(e)}")
    raise

# Constants
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"

async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Make a request to the NWS API with proper error handling."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json"
    }
    async with httpx.AsyncClient() as client:
        try:
            logging.debug(f"Making NWS request to {url}")
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            logging.debug(f"Received response from NWS: {data}")
            return data
        except Exception as e:
            logging.error(f"NWS request failed: {str(e)}")
            return None

def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    logging.debug(f"Formatting alert feature: {feature}")
    props = feature["properties"]
    return f"""
Event: {props.get('event', 'Unknown')}
Area: {props.get('areaDesc', 'Unknown')}
Severity: {props.get('severity', 'Unknown')}
Description: {props.get('description', 'No description available')}
Instructions: {props.get('instruction', 'No specific instructions provided')}
"""

@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state."""
    logging.debug(f"Fetching alerts for state: {state}")
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if not data or "features" not in data:
        logging.warning("No alerts data or features found")
        return "Unable to fetch alerts or no alerts found."

    if not data["features"]:
        logging.info("No active alerts for this state")
        return "No active alerts for this state."

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)

@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """Get weather forecast for a location."""
    logging.debug(f"Fetching forecast for lat: {latitude}, lon: {longitude}")
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)

    if not points_data:
        logging.warning("Failed to fetch forecast data")
        return "Unable to fetch forecast data for this location."

    forecast_url = points_data["properties"]["forecast"]
    forecast_data = await make_nws_request(forecast_url)

    if not forecast_data:
        logging.warning("Failed to fetch detailed forecast")
        return "Unable to fetch detailed forecast."

    periods = forecast_data["properties"]["periods"]
    forecasts = []
    for period in periods[:5]:
        forecast = f"""
{period['name']}:
Temperature: {period['temperature']}°{period['temperatureUnit']}
Wind: {period['windSpeed']} {period['windDirection']}
Forecast: {period['detailedForecast']}
"""
        forecasts.append(forecast)

    return "\n---\n".join(forecasts)

def handle_shutdown(loop):
    """Gracefully shut down the event loop."""
    logging.info("Handling shutdown...")
    tasks = [task for task in asyncio.all_tasks(loop) if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    loop.stop()
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.close()
    logging.info("Shutdown complete")

if __name__ == "__main__":
    logging.debug(f"Working directory: {os.getcwd()}")
    logging.debug("Starting MCP server with stdio transport...")
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: handle_shutdown(loop))
    try:
        mcp.run(transport='stdio')
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down...")
        handle_shutdown(loop)
    except Exception as e:
        logging.error(f"Error running MCP server: {str(e)}")
        raise
    finally:
        logging.debug("MCP server stopped")