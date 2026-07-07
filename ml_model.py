import math
import json
import re
from pathlib import Path

# Common stopwords to ignore in Natural Language Processing
STOPWORDS = {
    "i",
    "me",
    "my",
    "myself",
    "we",
    "our",
    "ours",
    "ourselves",
    "you",
    "your",
    "yours",
    "him",
    "his",
    "himself",
    "she",
    "her",
    "hers",
    "herself",
    "it",
    "its",
    "itself",
    "they",
    "them",
    "their",
    "theirs",
    "themselves",
    "what",
    "which",
    "who",
    "whom",
    "this",
    "that",
    "these",
    "those",
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "having",
    "do",
    "does",
    "did",
    "doing",
    "a",
    "an",
    "the",
    "and",
    "but",
    "if",
    "or",
    "because",
    "as",
    "until",
    "while",
    "of",
    "at",
    "by",
    "for",
    "with",
    "about",
    "against",
    "between",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "to",
    "from",
    "up",
    "down",
    "in",
    "out",
    "on",
    "off",
    "over",
    "under",
    "again",
    "further",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "any",
    "both",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "s",
    "t",
    "can",
    "will",
    "just",
    "don",
    "should",
    "now",
    "d",
    "ll",
    "m",
    "o",
    "re",
    "ve",
    "y",
    "please",
    "thanks",
    "incident",
    "issue",
    "ticket",
    "problem",
    "failure",
    "occurred",
    "experienced",
}


def tokenize(text):
    """Normalize, clean, and tokenize text."""
    if not text:
        return []
    # Lowercase & remove punctuation
    text = text.lower()
    text = re.sub(r"[^\w\s-]", " ", text)
    # Split on whitespace
    words = text.split()
    # Filter stopwords and numeric values (unless they look like error codes or codes)
    filtered = []
    for w in words:
        if w not in STOPWORDS and (len(w) > 2 or w.isupper()):
            filtered.append(w)
    return filtered


class MLModel:
    def __init__(self, data_path=None):
        self.data_path = (
            data_path
            or Path(__file__).parent / "knowledge_base" / "historical_incidents.json"
        )
        self.training_data = []
        self.idf = {}
        self.vocabulary = set()
        self.vectors = []
        self.load_training_data()
        self.train()

    def load_training_data(self):
        """Load training dataset from JSON."""
        if Path(self.data_path).exists():
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    self.training_data = json.load(f)
            except Exception as e:
                print(f"Error loading training data: {e}")
                self.training_data = []
        else:
            self.training_data = []

    def save_training_data(self):
        """Save updated training dataset to JSON."""
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.training_data, f, indent=4)
        except Exception as e:
            print(f"Error saving training data: {e}")

    def train(self):
        """Calculate IDF weights and document vectors for all training items."""
        if not self.training_data:
            return

        # 1. Build vocabulary and count document frequencies
        doc_counts = {}
        doc_tokens = []

        for item in self.training_data:
            text = f"{item.get('title', '')} {item.get('description', '')}"
            tokens = tokenize(text)
            doc_tokens.append(tokens)
            unique_tokens = set(tokens)
            for token in unique_tokens:
                doc_counts[token] = doc_counts.get(token, 0) + 1
                self.vocabulary.add(token)

        # 2. Calculate IDF
        num_docs = len(self.training_data)
        self.idf = {}
        for token, count in doc_counts.items():
            # Standard IDF formula with smoothing
            self.idf[token] = math.log((num_docs + 1) / (count + 0.5)) + 1.0

        # 3. Calculate TF-IDF vectors for each training document
        self.vectors = []
        for tokens in doc_tokens:
            vector = self._vectorize(tokens)
            self.vectors.append(vector)

    def _vectorize(self, tokens):
        """Helper to compute TF-IDF vector of list of tokens."""
        # Calculate Term Frequencies (TF)
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1

        vector = {}
        # Normalize and apply TF-IDF weight
        total_tokens = len(tokens) if tokens else 1
        for token, count in tf.items():
            if token in self.vocabulary:
                vector[token] = (count / total_tokens) * self.idf.get(token, 1.0)

        # Normalize vector length (L2 norm) to simplify cosine similarity
        norm = math.sqrt(sum(val**2 for val in vector.values()))
        if norm > 0:
            for token in vector:
                vector[token] /= norm

        return vector

    def add_new_incident(
        self, category, title, description, root_cause, resolution, script
    ):
        """Add new incident to training dataset and retrain model online."""
        new_item = {
            "category": category,
            "title": title,
            "description": description,
            "root_cause": root_cause,
            "resolution": resolution,
            "script": script,
        }
        self.training_data.append(new_item)
        self.save_training_data()
        self.train()

    def predict_category(self, title, description):
        """Predict the category of an incoming alert based on similarity."""
        match = self.find_best_match(title, description)
        if match and match["score"] > 0.15:
            return match["item"]["category"], match["score"]

        # Heuristics fallback if similarity is extremely low
        text = f"{title} {description}".lower()
        if any(
            w in text
            for w in ["cpu", "memory", "disk", "hardware", "host", "vm", "server"]
        ):
            return "Infrastructure", 0.3
        if any(w in text for w in ["database", "db", "sql", "pool", "connection"]):
            return "Database", 0.3
        if any(w in text for w in ["network", "latency", "dns", "packet"]):
            return "Network", 0.3
        if any(w in text for w in ["security", "ssh", "login", "brute", "attack"]):
            return "Security", 0.3

        return "Application", 0.2

    def find_best_match(self, title, description):
        """Find the most similar historical incident using cosine similarity."""
        if not self.training_data:
            return None

        query_tokens = tokenize(f"{title} {description}")
        if not query_tokens:
            return None

        query_vector = self._vectorize(query_tokens)

        best_score = -1.0
        best_index = -1

        for idx, tr_vector in enumerate(self.vectors):
            # Since vectors are L2 normalized, Cosine Similarity is simply the dot product!
            score = 0.0
            for token, weight in query_vector.items():
                if token in tr_vector:
                    score += weight * tr_vector[token]

            if score > best_score:
                best_score = score
                best_index = idx

        if best_index != -1:
            return {"item": self.training_data[best_index], "score": best_score}
        return None


# Global model instance
ml_model = MLModel()
