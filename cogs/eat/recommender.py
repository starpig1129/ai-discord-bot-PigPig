"""Lightweight Weighted Recommender.

Replaces the PyTorch LSTM model with a real-time weighted algorithm based on user rating history.
Calculates preference vectors directly from the DB and ranks candidate restaurants without training.
"""
import datetime
import random
from collections import Counter

from cogs.eat.db.db import DB
from addons.logging import get_logger

logger = get_logger(server_id="Bot", source="eat.recommender")

RECENTLY_VISITED_DAYS = 7   # "Recent" if visited within this many days
RECENTLY_VISITED_PENALTY = -1.5  # Penalty for recently visited restaurants
TAG_BOOST_MAX = 2.0          # Maximum bonus for liked tags
TAG_BOOST_PER_LIKE = 0.5     # Bonus increment per like


class WeightedRecommender:
    """Weighted recommender based on user rating history."""

    def __init__(self, db: DB):
        self.db = db

    def suggest_keyword(self, discord_id: str, available_keywords: list[str]) -> str:
        """Suggest the next search keyword based on user preferences.

        Prioritizes tags/keywords the user has liked; chooses randomly if no history exists.

        Args:
            discord_id: Server or user ID.
            available_keywords: List of existing keywords in the database.

        Returns:
            Suggested search keyword string.
        """
        if not available_keywords:
            return "餐廳"

        try:
            liked = self.db.getLikedRecords(discord_id)
            if not liked:
                return random.choice(available_keywords)

            # Count occurrences of keywords in liked records
            liked_keywords = Counter()
            for row in liked:
                record = row[0]
                if record.keyword:
                    liked_keywords[record.keyword] += 1
                if record.tag:
                    liked_keywords[record.tag] += 1

            # Find the keyword with the highest preference score among available_keywords
            best = max(
                available_keywords,
                key=lambda kw: liked_keywords.get(kw, 0),
            )
            # If the best keyword has a preference score of 0, choose randomly
            if liked_keywords.get(best, 0) == 0:
                return random.choice(available_keywords)
            return best

        except Exception as e:
            logger.warning(f"suggest_keyword failed, choosing randomly: {e}")
            return random.choice(available_keywords)

    def rank_candidates(self, discord_id: str, candidates: list[dict]) -> list[dict]:
        """Rank candidate restaurants, excluding disliked ones and weighting liked categories.

        Args:
            discord_id: Server or user ID.
            candidates: List of PlaceResult dictionaries (from Provider).

        Returns:
            Sorted list of PlaceResult dictionaries (higher score first).
        """
        if not candidates:
            return []

        try:
            liked_records = self.db.getLikedRecords(discord_id)
            disliked_records = self.db.getDislikedRecords(discord_id)
            recent_records = self.db.getRecentRecords(discord_id, days=RECENTLY_VISITED_DAYS)

            # Create liked tags counter
            liked_tags: Counter = Counter()
            for row in liked_records:
                record = row[0]
                if record.tag:
                    liked_tags[record.tag] += record.self_rate

            # Create set of disliked restaurant names (for exclusion)
            disliked_titles = {row[0].title.lower() for row in disliked_records if row[0].title}

            # Create set of recently visited restaurant names (for penalty)
            recently_visited = {row[0].title.lower() for row in recent_records if row[0].title}

            def score(place: dict) -> float:
                name_lower = place.get("name", "").lower()
                # Completely exclude disliked restaurants
                if name_lower in disliked_titles:
                    return float("-inf")

                base = place.get("rating", 3.0) or 3.0  # Treat 0 rating as 3.0

                # Tag preference boost
                category = place.get("category", "")
                tag_boost = min(liked_tags.get(category, 0) * TAG_BOOST_PER_LIKE, TAG_BOOST_MAX)

                # Recently visited penalty
                visit_penalty = RECENTLY_VISITED_PENALTY if name_lower in recently_visited else 0.0

                return base + tag_boost + visit_penalty

            scored = [(place, score(place)) for place in candidates]
            # Exclude -inf scores (disliked), then sort by score descending
            filtered = [(p, s) for p, s in scored if s != float("-inf")]
            filtered.sort(key=lambda x: x[1], reverse=True)

            return [p for p, _ in filtered]

        except Exception as e:
            logger.warning(f"rank_candidates failed, returning original order: {e}")
            return candidates
