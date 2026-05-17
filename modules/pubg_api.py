"""PUBG 官方 API 客户端 — 生涯/赛季/最近战绩。"""

import logging
from dataclasses import dataclass, field
import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.pubg.com"


@dataclass
class MatchSummary:
    map_name: str = ""
    game_mode: str = ""
    kills: int = 0
    damage: float = 0.0
    placement: int = 0
    time_survived: int = 0  # 秒

    def format(self) -> str:
        minutes = self.time_survived // 60
        return (
            f"{self.map_name}({self.game_mode}) "
            f"排名#{self.placement} 击杀{self.kills} 伤害{int(self.damage)} 存活{minutes}分钟"
        )


@dataclass
class PubgStats:
    game_id: str = ""
    # 生涯
    kd: float = 0.0
    kills: int = 0
    wins: int = 0
    rounds_played: int = 0
    top10s: int = 0
    damage_dealt: float = 0.0
    # 本赛季
    season_kd: float = 0.0
    season_kills: int = 0
    season_wins: int = 0
    season_rounds: int = 0
    season_top10s: int = 0
    # 最近比赛
    recent_matches: list = field(default_factory=list)

    def format(self) -> str:
        if not self.game_id:
            return "无 PUBG 数据"

        lines = [
            f"游戏ID：{self.game_id}",
            "",
            "【生涯总数据】",
            f"  KD：{self.kd:.2f}  总击杀：{self.kills}  吃鸡：{self.wins}次",
            f"  对战场次：{self.rounds_played}  TOP10：{self.top10s}次  总伤害：{int(self.damage_dealt)}",
        ]

        if self.season_rounds > 0:
            lines.extend([
                "",
                "【本赛季数据】",
                f"  KD：{self.season_kd:.2f}  击杀：{self.season_kills}  吃鸡：{self.season_wins}次",
                f"  场次：{self.season_rounds}  TOP10：{self.season_top10s}次",
            ])

        if self.recent_matches:
            lines.extend(["", "【最近比赛】"])
            for i, m in enumerate(self.recent_matches[:5], 1):
                lines.append(f"  {i}.{m.format()}")

        return "\n".join(lines)


class PubgApiClient:
    def __init__(self, api_key: str, shard: str = "steam"):
        self.api_key = api_key
        self.shard = shard
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/vnd.api+json",
                },
                timeout=10.0,
            )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _aggregate_mode_stats(self, game_modes: dict) -> dict:
        """聚合各模式统计数据。"""
        result = {"kills": 0, "wins": 0, "rounds": 0, "top10s": 0, "damage": 0.0}
        for stats in game_modes.values():
            result["kills"] += int(stats.get("kills", 0))
            result["wins"] += int(stats.get("wins", 0))
            result["rounds"] += int(stats.get("roundsPlayed", 0))
            result["top10s"] += int(stats.get("top10s", 0))
            result["damage"] += float(stats.get("damageDealt", 0))
        return result

    async def _lookup_player(self, player_name: str) -> tuple[str, str, list[str]] | None:
        """查找玩家，返回 (player_id, game_id, match_ids) 或 None。"""
        resp = await self._client.get(
            f"/shards/{self.shard}/players",
            params={"filter[playerNames]": player_name},
        )
        resp.raise_for_status()
        players = resp.json().get("data", [])
        if not players:
            return None
        player = players[0]
        player_id = player["id"]
        game_id = player["attributes"]["name"]
        # match ID 来自 player 的 relationships.matches
        match_ids = [
            m["id"]
            for m in player.get("relationships", {}).get("matches", {}).get("data", [])
            if m.get("type") == "match"
        ]
        return player_id, game_id, match_ids

    async def _get_season_stats(self, player_id: str, season_id: str) -> dict:
        """获取指定赛季的聚合统计数据。"""
        resp = await self._client.get(
            f"/shards/{self.shard}/players/{player_id}/seasons/{season_id}",
        )
        resp.raise_for_status()
        game_modes = (
            resp.json()
            .get("data", {})
            .get("attributes", {})
            .get("gameModeStats", {})
        )
        return await self._aggregate_mode_stats(game_modes)

    async def _get_current_season_id(self) -> str | None:
        """获取当前赛季 ID。"""
        resp = await self._client.get(f"/shards/{self.shard}/seasons")
        resp.raise_for_status()
        seasons = resp.json().get("data", [])
        for s in seasons:
            if s.get("attributes", {}).get("isCurrentSeason"):
                return s["id"]
        # 兜底：返回最后一个
        return seasons[-1]["id"] if seasons else None

    async def _get_match_summary(self, match_id: str, player_name: str) -> MatchSummary | None:
        """获取单场比赛摘要。"""
        try:
            resp = await self._client.get(
                f"/shards/{self.shard}/matches/{match_id}",
            )
            resp.raise_for_status()
            data = resp.json()

            match_attrs = data.get("data", {}).get("attributes", {})
            map_name = match_attrs.get("mapName", "?")
            game_mode = match_attrs.get("gameMode", "?")

            # 在 included 中找对应玩家的 participant
            included = data.get("included", [])
            for item in included:
                if item.get("type") != "participant":
                    continue
                attrs = item.get("attributes", {})
                stats = attrs.get("stats", {})
                if stats.get("name", "") == player_name:
                    return MatchSummary(
                        map_name=map_name,
                        game_mode=game_mode,
                        kills=int(stats.get("kills", 0)),
                        damage=float(stats.get("damageDealt", 0)),
                        placement=int(stats.get("winPlace", 0)),
                        time_survived=int(stats.get("timeSurvived", 0)),
                    )
        except Exception:
            logger.debug("获取比赛 %s 详情失败", match_id)
        return None

    async def get_player_stats(self, player_name: str) -> PubgStats | None:
        """获取完整 PUBG 数据（生涯 + 本赛季 + 最近比赛）。失败返回 None。"""
        try:
            await self._ensure_client()

            # 1. 查找玩家（同时获取最近 match ID 列表）
            player = await self._lookup_player(player_name)
            if player is None:
                logger.warning("PUBG 玩家未找到: %s", player_name)
                return None
            player_id, game_id, match_ids = player

            # 2. 生涯数据
            lifetime = await self._get_season_stats(player_id, "lifetime")
            kd = round(lifetime["kills"] / lifetime["rounds"], 2) if lifetime["rounds"] > 0 else 0.0

            stats = PubgStats(
                game_id=game_id,
                kd=kd,
                kills=lifetime["kills"],
                wins=lifetime["wins"],
                rounds_played=lifetime["rounds"],
                top10s=lifetime["top10s"],
                damage_dealt=lifetime["damage"],
            )

            # 3. 当前赛季数据（失败不影响主流程）
            try:
                season_id = await self._get_current_season_id()
                if season_id:
                    season = await self._get_season_stats(player_id, season_id)
                    stats.season_kills = season["kills"]
                    stats.season_wins = season["wins"]
                    stats.season_rounds = season["rounds"]
                    stats.season_top10s = season["top10s"]
                    if season["rounds"] > 0:
                        stats.season_kd = round(season["kills"] / season["rounds"], 2)
            except Exception:
                logger.debug("获取赛季数据失败")

            # 4. 最近比赛（取前 5 个，和赛季并发放置）
            try:
                for mid in match_ids[:5]:
                    summary = await self._get_match_summary(mid, player_name)
                    if summary:
                        stats.recent_matches.append(summary)
            except Exception:
                logger.debug("获取比赛详情失败")

            return stats

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("PUBG API 限流")
            elif e.response.status_code == 404:
                logger.warning("PUBG 玩家未找到: %s", player_name)
            else:
                logger.warning("PUBG API HTTP %d: %s", e.response.status_code, e)
            return None
        except httpx.TimeoutException:
            logger.warning("PUBG API 超时")
            return None
        except Exception:
            logger.exception("PUBG API 异常")
            return None
