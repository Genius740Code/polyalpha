"""
Example: Using weather station configurations for weather bots.

This example demonstrates how to use the pre-configured city templates
to quickly set up weather trading bots, similar to how polymarker weather
bots use city configurations.
"""

from polyalpha import Client
from polyalpha.bots import CITIES, print_config, list_configs

# Example 1: List all available city configurations
print("Available city configurations:")
for name in list_configs():
    print(f"  - {name}")
print()

# Example 2: Print a configuration for copy-paste
print("Configuration for Seoul (copy-paste ready):")
print_config("Seoul")
print()

# Example 3: Use a pre-configured city
# Uncomment to run with actual client:
# client = Client()
# config = CITIES["Seoul"]
# weather_bot = WeatherBot(client, **config)
# weather_bot.run()

# Example 4: Create a custom configuration based on a template
custom_config = CITIES["Seoul"].copy()
custom_config["station"] = "RKPC"
custom_config["lat"] = 35.179
custom_config["lon"] = 129.075
custom_config["tz"] = "Asia/Seoul"

print("Custom configuration based on Seoul:")
print(f'  Station: {custom_config["station"]}')
print(f'  Lat/Lon: {custom_config["lat"]}, {custom_config["lon"]}')
print(f'  Timezone: {custom_config["tz"]}')