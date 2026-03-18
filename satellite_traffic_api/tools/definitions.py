"""
OpenAI-compatible tool/function schemas for satellite agent use.
These can be passed directly to any LLM that supports function calling
(OpenAI, Anthropic tool_use, NVIDIA NIM, LangChain, etc.)
"""

SATELLITE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_satellite_context",
            "description": (
                "Retrieve full situational context for a satellite by NORAD catalog ID. "
                "Returns current orbital state (position, velocity, altitude), conjunction threats "
                "(close approaches with other objects), space weather conditions, atmospheric drag, "
                "and upcoming ground station contact windows. "
                "Use this as the primary tool for collision avoidance and traffic negotiation decisions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "norad_id": {
                        "type": "integer",
                        "description": "NORAD catalog number (e.g., 25544 for ISS)",
                    },
                },
                "required": ["norad_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_conjunction_events",
            "description": (
                "Get all predicted close approaches (conjunctions) for a satellite over the next N days. "
                "Each event includes time of closest approach (TCA), miss distance in km, "
                "collision probability, and details on the secondary object."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "norad_id": {
                        "type": "integer",
                        "description": "NORAD catalog number of the primary satellite",
                    },
                },
                "required": ["norad_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_orbital_state",
            "description": (
                "Get the current propagated state vector for a satellite: "
                "ECI position (x, y, z km), ECI velocity (vx, vy, vz km/s), "
                "geodetic latitude/longitude/altitude, and speed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "norad_id": {
                        "type": "integer",
                        "description": "NORAD catalog number",
                    },
                },
                "required": ["norad_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_space_weather",
            "description": (
                "Get current space weather: planetary Kp index, geomagnetic storm level (NONE/G1-G5), "
                "solar wind speed/density/magnetic field, solar radio flux (F10.7), "
                "and atmospheric drag enhancement factor. "
                "High Kp values increase atmospheric drag and degrade GPS accuracy."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ground_contacts",
            "description": (
                "Get upcoming ground station visibility windows for a satellite: "
                "acquisition of signal (AOS), loss of signal (LOS), max elevation, duration. "
                "Useful for planning when maneuver commands can be uplinked."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "norad_id": {
                        "type": "integer",
                        "description": "NORAD catalog number",
                    },
                },
                "required": ["norad_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tle",
            "description": (
                "Get the current Two-Line Element set (TLE) for a satellite. "
                "Contains the Keplerian orbital elements needed for propagation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "norad_id": {
                        "type": "integer",
                        "description": "NORAD catalog number",
                    },
                },
                "required": ["norad_id"],
            },
        },
    },
]
