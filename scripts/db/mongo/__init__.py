import certifi
import os

try:
	from pymongo import MongoClient
	from pymongo.server_api import ServerApi
except ImportError as exc:
	if "cannot import name 'SON'" in str(exc):
		raise ImportError(
			"PyMongo requires its bundled 'bson' package, but a standalone 'bson' distribution "
			"is shadowing it. Please run 'pip uninstall bson' and reinstall PyMongo."
		) from exc
	raise


def _build_client(uri: str) -> MongoClient:
	kwargs = {"server_api": ServerApi("1"), "serverSelectionTimeoutMS": 3000}
	if uri.startswith("mongodb+srv://"):
		kwargs["tlsCAFile"] = certifi.where()
	return MongoClient(uri, **kwargs)


# MongoDB connection - require MONGO_URI at runtime
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = _build_client(MONGO_URI)

_mongo_available = False
try:
	client.admin.command("ping")
	print("✅ MongoDB ping succeeded")
	_mongo_available = True
except Exception as exc:
	print(f"⚠️ MongoDB unavailable: {exc}")
	print("   Running without database - using local file storage only")

db = client["webnovel"]

def is_mongo_available() -> bool:
	"""Check if MongoDB is available."""
	return _mongo_available
