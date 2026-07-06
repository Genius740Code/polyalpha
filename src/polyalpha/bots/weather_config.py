"""
Weather station configuration templates for weather bots.

This module provides pre-configured weather station settings that can be easily
copied and customized for different weather trading strategies. Similar to how
polymarker weather bots use city configurations.

Usage
-----
    from polyalpha.bots.weather_config import CITIES, print_config

    # Use a pre-configured city
    config = CITIES["Seoul"]
    weather_bot = WeatherBot(client, **config)

    # Print a configuration for copy-paste
    print_config("Seoul")

    # List all available configurations
    print(list(CITIES.keys()))
"""

from typing import Optional

# ── City Configurations ───────────────────────────────────────────────────────

CITIES = {
    "Seoul": {
        "station": "RKSI",
        "source": "iem",
        "lat": 37.469,
        "lon": 126.451,
        "tz": "Asia/Seoul",
        "bucket_mode": "round",
    },
    "Shanghai": {
        "station": "ZSPD",
        "source": "iem",
        "lat": 31.143,
        "lon": 121.805,
        "tz": "Asia/Shanghai",
        "bucket_mode": "round",
    },
    "Chengdu": {
        "station": "ZUUU",
        "source": "iem",
        "lat": 30.578,
        "lon": 103.947,
        "tz": "Asia/Shanghai",
        "bucket_mode": "round",
    },
    "Shenzhen": {
        "station": "ZGSZ",
        "source": "iem",
        "lat": 22.639,
        "lon": 113.811,
        "tz": "Asia/Shanghai",
        "bucket_mode": "round",
    },
    "Hong Kong": {
        "station": "HKO",
        "source": "hko",
        "lat": 22.302,
        "lon": 114.174,
        "tz": "Asia/Hong_Kong",
        "bucket_mode": "floor",
    },
    "Tokyo": {
        "station": "RJTT",
        "source": "iem",
        "lat": 35.549,
        "lon": 139.779,
        "tz": "Asia/Tokyo",
        "bucket_mode": "round",
    },
    "Singapore": {
        "station": "WSSS",
        "source": "iem",
        "lat": 1.364,
        "lon": 103.991,
        "tz": "Asia/Singapore",
        "bucket_mode": "round",
    },
    "Bangkok": {
        "station": "VTBS",
        "source": "iem",
        "lat": 13.690,
        "lon": 100.751,
        "tz": "Asia/Bangkok",
        "bucket_mode": "round",
    },
    "Manila": {
        "station": "RPLL",
        "source": "iem",
        "lat": 14.509,
        "lon": 121.020,
        "tz": "Asia/Manila",
        "bucket_mode": "round",
    },
    "Jakarta": {
        "station": "WIII",
        "source": "iem",
        "lat": -6.125,
        "lon": 106.656,
        "tz": "Asia/Jakarta",
        "bucket_mode": "round",
    },
}


# ── Configuration Helpers ─────────────────────────────────────────────────────

def print_config(name: str) -> None:
    """
    Print a city configuration in a copy-paste friendly format.

    Parameters
    ----------
    name : str
        The name of the configuration to print (key from CITIES dict).
    """
    if name not in CITIES:
        available = ", ".join(CITIES.keys())
        raise ValueError(f"Unknown config '{name}'. Available: {available}")

    config = CITIES[name]
    
    print(f'"{name}": {{')
    for key, value in config.items():
        if isinstance(value, str):
            print(f'    "{key}": "{value}",')
        elif value is None:
            print(f'    "{key}": None,')
        else:
            print(f'    "{key}": {value},')
    print("},")


def list_configs() -> list[str]:
    """Return a list of all available configuration names."""
    return list(CITIES.keys())


def get_config(name: str) -> dict:
    """
    Get a configuration dictionary by name.

    Parameters
    ----------
    name : str
        The name of the configuration to retrieve.

    Returns
    -------
    dict
        The configuration dictionary.
    """
    if name not in CITIES:
        available = ", ".join(CITIES.keys())
        raise ValueError(f"Unknown config '{name}'. Available: {available}")
    
    return CITIES[name].copy()


def add_config(name: str, config: dict) -> None:
    """
    Add a new configuration to the CITIES dictionary.

    Parameters
    ----------
    name : str
        The name/key for the new configuration.
    config : dict
        The configuration dictionary to add.
    """
    CITIES[name] = config


# ── Example Usage (commented out) ─────────────────────────────────────────────

# Example of how to use these configurations:
#
# from polyalpha.bots.weather_config import CITIES
#
# # Use a pre-configured city
# config = CITIES["Seoul"]
# weather_bot = WeatherBot(client, **config)
# weather_bot.run()
#
# # Or print it for copy-paste
# from polyalpha.bots.weather_config import print_config
# print_config("Seoul")
