# pylint: disable=missing-module-docstring
from dotenv import dotenv_values

# Pulling keys & values from .env file
config :dict = dotenv_values(".env")

print(config["VERSION"])
