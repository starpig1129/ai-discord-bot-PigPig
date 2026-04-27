"""輕量加權推薦器

取代 PyTorch LSTM 模型，使用基於用戶評分歷史的即時加權算法。
無需訓練，直接從 DB 計算偏好向量並對候選餐廳排名。
"""
import datetime
import random
from collections import Counter

from cogs.eat.db.db import DB
from addons.logging import get_logger

logger = get_logger(server_id="Bot", source="eat.recommender")

RECENTLY_VISITED_DAYS = 7   # 幾天內訪問過算「最近」
RECENTLY_VISITED_PENALTY = -1.5  # 最近訪問過的懲罰分
TAG_BOOST_MAX = 2.0          # 喜歡標籤的最大加分
TAG_BOOST_PER_LIKE = 0.5     # 每次喜歡增加的分數


class WeightedRecommender:
    """基於用戶評分歷史的加權推薦器。"""

    def __init__(self, db: DB):
        self.db = db

    def suggest_keyword(self, discord_id: str, available_keywords: list[str]) -> str:
        """根據用戶偏好建議下一個搜尋關鍵字。

        優先選擇用戶喜歡過的標籤/關鍵字；若無歷史，隨機選擇。

        Args:
            discord_id: 伺服器或用戶 ID
            available_keywords: 資料庫中現有的關鍵字列表

        Returns:
            建議的搜尋關鍵字字串
        """
        if not available_keywords:
            return "餐廳"

        try:
            liked = self.db.getLikedRecords(discord_id)
            if not liked:
                return random.choice(available_keywords)

            # 統計喜歡記錄中的 keyword 出現次數
            liked_keywords = Counter()
            for row in liked:
                record = row[0]
                if record.keyword:
                    liked_keywords[record.keyword] += 1
                if record.tag:
                    liked_keywords[record.tag] += 1

            # 找出在 available_keywords 中且偏好分最高的
            best = max(
                available_keywords,
                key=lambda kw: liked_keywords.get(kw, 0),
            )
            # 若最佳關鍵字偏好分為 0，表示沒有交集，隨機選擇
            if liked_keywords.get(best, 0) == 0:
                return random.choice(available_keywords)
            return best

        except Exception as e:
            logger.warning(f"suggest_keyword 失敗，隨機選擇：{e}")
            return random.choice(available_keywords)

    def rank_candidates(self, discord_id: str, candidates: list[dict]) -> list[dict]:
        """對候選餐廳排名，排除不喜歡的餐廳並加權喜歡的類別。

        Args:
            discord_id: 伺服器或用戶 ID
            candidates: PlaceResult 字典列表（來自 Provider）

        Returns:
            排序後的 PlaceResult 列表（分數高優先）
        """
        if not candidates:
            return []

        try:
            liked_records = self.db.getLikedRecords(discord_id)
            disliked_records = self.db.getDislikedRecords(discord_id)
            recent_records = self.db.getRecentRecords(discord_id, days=RECENTLY_VISITED_DAYS)

            # 建立喜歡標籤計數器
            liked_tags: Counter = Counter()
            for row in liked_records:
                record = row[0]
                if record.tag:
                    liked_tags[record.tag] += record.self_rate

            # 建立不喜歡餐廳名稱集合（排除用）
            disliked_titles = {row[0].title.lower() for row in disliked_records if row[0].title}

            # 建立最近訪問餐廳名稱集合（懲罰用）
            recently_visited = {row[0].title.lower() for row in recent_records if row[0].title}

            def score(place: dict) -> float:
                name_lower = place.get("name", "").lower()
                # 完全排除不喜歡的餐廳
                if name_lower in disliked_titles:
                    return float("-inf")

                base = place.get("rating", 3.0) or 3.0  # 0 評分視為 3.0

                # 標籤喜好加成
                category = place.get("category", "")
                tag_boost = min(liked_tags.get(category, 0) * TAG_BOOST_PER_LIKE, TAG_BOOST_MAX)

                # 最近訪問懲罰
                visit_penalty = RECENTLY_VISITED_PENALTY if name_lower in recently_visited else 0.0

                return base + tag_boost + visit_penalty

            scored = [(place, score(place)) for place in candidates]
            # 排除分數為 -inf（不喜歡的），然後按分數降序
            filtered = [(p, s) for p, s in scored if s != float("-inf")]
            filtered.sort(key=lambda x: x[1], reverse=True)

            return [p for p, _ in filtered]

        except Exception as e:
            logger.warning(f"rank_candidates 失敗，返回原始順序：{e}")
            return candidates
