# Copyright (c) Microsoft. All rights reserved.

"""Weather forecasting tool using Open-Meteo API."""

from typing import Annotated

import httpx
from agent_framework import ai_function
from pydantic import Field


@ai_function  # type: ignore[arg-type]
async def get_weather_forecast(
    location: Annotated[
        str, Field(description="City name or 'latitude,longitude' (e.g., 'Seattle' or '47.6062,-122.3321')")
    ],
    days: Annotated[int, Field(description="Number of forecast days (1-7)", ge=1, le=7)] = 3,
) -> str:
    """
    Get weather forecast for a location using Open-Meteo API (free, no API key required).

    Parameters
    ----------
    location : str
        City name or coordinates in 'latitude,longitude' format
    days : int, optional
        Number of forecast days (1-7), default is 3

    Returns
    -------
    str
        Formatted weather forecast including date, conditions, temperature range,
        and precipitation probability

    Notes
    -----
    Uses Open-Meteo API which is free and requires no API key.
    For city names, geocoding is performed automatically.
    Weather codes follow WMO standard.
    """
    async with httpx.AsyncClient() as client:
        try:
            # If location contains comma, treat as lat,lon coordinates
            if "," in location:
                try:
                    lat, lon = map(float, location.split(","))
                    location_name = f"{lat:.4f}°, {lon:.4f}°"
                except ValueError:
                    return "Error: Invalid coordinates format. Use 'latitude,longitude' (e.g., '47.6062,-122.3321')"
            else:
                # Geocode city name using Open-Meteo's geocoding API
                geocode_url = "https://geocoding-api.open-meteo.com/v1/search"
                geocode_params: dict[str, str | int] = {
                    "name": location,
                    "count": 1,
                    "language": "en",
                    "format": "json",
                }
                geocode_response = await client.get(geocode_url, params=geocode_params)
                geocode_response.raise_for_status()
                geocode_data = geocode_response.json()

                if not geocode_data.get("results"):
                    return f"Error: Location '{location}' not found. Try using coordinates like '47.6062,-122.3321'"

                result = geocode_data["results"][0]
                lat = result["latitude"]
                lon = result["longitude"]
                location_name = f"{result['name']}, {result.get('country', 'Unknown')}"

            # Get weather forecast from Open-Meteo
            weather_url = "https://api.open-meteo.com/v1/forecast"
            weather_params: dict[str, str | float | int] = {
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": days,
            }

            weather_response = await client.get(weather_url, params=weather_params)
            weather_response.raise_for_status()
            weather_data = weather_response.json()

            # Weather code mapping (WMO codes)
            weather_codes = {
                0: "clear sky",
                1: "mainly clear",
                2: "partly cloudy",
                3: "overcast",
                45: "foggy",
                48: "depositing rime fog",
                51: "light drizzle",
                53: "moderate drizzle",
                55: "dense drizzle",
                61: "slight rain",
                63: "moderate rain",
                65: "heavy rain",
                71: "slight snow",
                73: "moderate snow",
                75: "heavy snow",
                77: "snow grains",
                80: "slight rain showers",
                81: "moderate rain showers",
                82: "violent rain showers",
                85: "slight snow showers",
                86: "heavy snow showers",
                95: "thunderstorm",
                96: "thunderstorm with slight hail",
                99: "thunderstorm with heavy hail",
            }

            # Format forecast
            daily = weather_data["daily"]
            forecasts = []
            for i in range(len(daily["time"])):
                date = daily["time"][i]
                temp_max = daily["temperature_2m_max"][i]
                temp_min = daily["temperature_2m_min"][i]
                weather_code = daily["weathercode"][i]
                precip_prob = daily["precipitation_probability_max"][i]
                condition = weather_codes.get(weather_code, "unknown")

                forecasts.append(  # type: ignore
                    f"{date}: {condition}, {temp_min:.1f}°C to {temp_max:.1f}°C, {precip_prob}% chance of precipitation"
                )

            return f"Weather forecast for {location_name}:\n" + "\n".join(forecasts)  # type: ignore

        except httpx.HTTPStatusError as e:
            return f"Error fetching weather: {e.response.status_code} - {e.response.text}"
        except Exception as e:
            return f"Error: {e!s}"


__all__ = ["get_weather_forecast"]
