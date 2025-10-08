from pymongo import MongoClient
from pymongo.server_api import ServerApi
import os
import certifi


def _build_client(uri: str) -> MongoClient:
	kwargs = {"server_api": ServerApi("1")}
	if uri.startswith("mongodb+srv://"):
		kwargs["tlsCAFile"] = certifi.where()
	return MongoClient(uri, **kwargs)


# MongoDB connection	require MONGO_URI at runtime
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = _build_client(MONGO_URI)

try:
	client.admin.command("ping")
	print("MongoDB ping succeeded")
except Exception as exc:
	print(f"MongoDB ping failed: {exc}")

db = client["webnovel"]
