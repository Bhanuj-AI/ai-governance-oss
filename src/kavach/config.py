from dotenv import load_dotenv  # type: ignore
import os

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_DEFAULT_JUDGE_MODEL = os.getenv("OPENAI_DEFAULT_JUDGE_MODEL")

KAVACH_RUN_NEO4J_TESTS = os.getenv("KAVACH_RUN_NEO4J_TESTS", "false")
KAVACH_GRAPH_URI = os.getenv("KAVACH_GRAPH_URI", "bolt://localhost:7687")
KAVACH_GRAPH_USER = os.getenv("KAVACH_GRAPH_USER", "neo4j")
KAVACH_GRAPH_PASSWORD = os.getenv(
    "KAVACH_GRAPH_PASSWORD",
    "kavach-local-password",
)
KAVACH_GRAPH_DATABASE = os.getenv("KAVACH_GRAPH_DATABASE", "neo4j")

KAVACH_POLICY_REPOSITORY = os.getenv("KAVACH_POLICY_REPOSITORY", "inmemory").lower()
KAVACH_POLICY_SQLITE_PATH = os.getenv("KAVACH_POLICY_SQLITE_PATH")
KAVACH_POLICY_POSTGRES_DSN = os.getenv("KAVACH_POLICY_POSTGRES_DSN")
