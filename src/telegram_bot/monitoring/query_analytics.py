"""
Query analytics and pattern analysis for Telegram bot.

This module provides detailed analysis of user queries, compound usage,
reaction patterns, and performance trends.
"""

import re
import json
from typing import Dict, List, Any, Tuple, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict
import threading

from ..models.security import QueryStatistics
from ...thermo_agents.models.extraction import ExtractedReactionParameters


@dataclass
class QueryPattern:
    """Pattern information for a query category"""
    pattern: str
    count: int
    avg_processing_time: float
    success_rate: float
    examples: List[str]


@dataclass
class CompoundAnalytics:
    """Analytics for chemical compounds"""
    compound_name: str
    total_mentions: int
    unique_users: Set[int]
    avg_temperature: float
    temperature_range: Tuple[float, float]
    common_phases: List[str]
    success_rate: float
    first_mentioned: datetime
    last_mentioned: datetime


@dataclass
class ReactionAnalytics:
    """Analytics for chemical reactions"""
    reaction_hash: str
    reaction_type: str  # "oxidation", "reduction", "synthesis", etc.
    count: int
    unique_users: Set[int]
    avg_temperature_range: Tuple[float, float]
    common_compounds: List[str]
    success_rate: float
    avg_processing_time: float


class QueryAnalytics:
    """
    Advanced analytics for Telegram bot queries and usage patterns.

    Provides insights into:
    - Query patterns and trends
    - Compound usage statistics
    - Reaction analysis
    - User behavior patterns
    - Performance bottlenecks
    """

    def __init__(self):
        self.query_patterns: Dict[str, QueryPattern] = {}
        self.compound_analytics: Dict[str, CompoundAnalytics] = {}
        self.reaction_analytics: Dict[str, ReactionAnalytics] = {}

        # Raw data storage
        self.query_history: List[Dict[str, Any]] = []
        self.compound_mentions: List[Dict[str, Any]] = []
        self.reaction_history: List[Dict[str, Any]] = []

        # Pattern matching
        self._init_patterns()

        # Thread safety
        self._lock = threading.Lock()

    def _init_patterns(self) -> None:
        """Initialize regex patterns for query classification."""
        self.patterns = {
            "compound_properties": [
                r"(?:свойства|properties?)\s+(?:для|of)\s+([A-Za-z0-9]+)",
                r"([A-Za-z0-9]+)\s+(?:свойства|properties?)",
                r"дай\s+(?:таблицу|table)\s+(?:для|of)\s+([A-Za-z0-9]+)",
                r"([A-Za-z0-9]+)\s+(?:температура|temperature)"
            ],
            "reaction_calculation": [
                r"([A-Za-z0-9\s\+\-\=→]+)\s+(?:при|at)\s+",
                r"реакция|reaction",
                r"рассчитай|calculate",
                r"термодинамика|thermodynamics"
            ],
            "temperature_range": [
                r"(\d+)\s*[-–]\s*(\d+)\s*K",
                r"от\s+(\d+)\s+до\s+(\d+)\s*K",
                r"between\s+(\d+)\s+and\s+(\d+)\s*K"
            ],
            "single_temperature": [
                r"(\d+)\s*K",
                r"при\s+(\d+)\s*K",
                r"at\s+(\d+)\s*K"
            ],
            "equilibrium": [
                r"равновесие|equilibrium",
                r"константа|constant",
                r"K\s*=|Kp|Kc"
            ],
            "phase_transition": [
                r"плавление|melting",
                r"кипение|boiling",
                r"сублимация|sublimation",
                r"фазовый|phase"
            ]
        }

    def record_query(
        self,
        user_id: int,
        query: str,
        extracted_params: Optional[ExtractedReactionParameters],
        processing_time: float,
        success: bool,
        timestamp: Optional[datetime] = None
    ) -> None:
        """
        Record a query for analytics.

        Args:
            user_id: Telegram user ID
            query: Original user query
            extracted_params: Parameters extracted by LLM
            processing_time: Processing time in seconds
            success: Whether the query was successful
            timestamp: Query timestamp (default: now)
        """
        if timestamp is None:
            timestamp = datetime.now()

        with self._lock:
            # Store raw query data
            query_data = {
                "user_id": user_id,
                "query": query,
                "timestamp": timestamp,
                "processing_time": processing_time,
                "success": success,
                "query_type": extracted_params.query_type.value if extracted_params else "unknown"
            }
            self.query_history.append(query_data)

            # Analyze query patterns
            self._analyze_query_patterns(query_data)

            # Analyze compounds if present
            if extracted_params and extracted_params.all_compounds:
                self._analyze_compound_mentions(user_id, extracted_params, timestamp, success)

            # Analyze reactions if present
            if (extracted_params and
                extracted_params.query_type.value == "reaction_calculation" and
                extracted_params.balanced_equation):
                self._analyze_reaction_mentions(user_id, extracted_params, processing_time, success, timestamp)

    def _analyze_query_patterns(self, query_data: Dict[str, Any]) -> None:
        """Analyze and categorize query patterns."""
        query = query_data["query"].lower()

        for pattern_name, regex_list in self.patterns.items():
            for regex in regex_list:
                if re.search(regex, query, re.IGNORECASE):
                    if pattern_name not in self.query_patterns:
                        self.query_patterns[pattern_name] = QueryPattern(
                            pattern=pattern_name,
                            count=0,
                            avg_processing_time=0.0,
                            success_rate=1.0,
                            examples=[]
                        )

                    pattern = self.query_patterns[pattern_name]
                    pattern.count += 1

                    # Update average processing time
                    pattern.avg_processing_time = (
                        (pattern.avg_processing_time * (pattern.count - 1) + query_data["processing_time"]) / pattern.count
                    )

                    # Update success rate
                    if query_data["success"]:
                        pattern.success_rate = (pattern.success_rate * (pattern.count - 1) + 1.0) / pattern.count
                    else:
                        pattern.success_rate = (pattern.success_rate * (pattern.count - 1)) / pattern.count

                    # Add example if not already present
                    if len(pattern.examples) < 5 and query_data["query"] not in pattern.examples:
                        pattern.examples.append(query_data["query"])

                    break  # Only match one pattern per query

    def _analyze_compound_mentions(
        self,
        user_id: int,
        extracted_params: ExtractedReactionParameters,
        timestamp: datetime,
        success: bool
    ) -> None:
        """Analyze compound mentions in queries."""
        for compound in extracted_params.all_compounds:
            compound_name = compound.compound_name

            # Extract temperature information
            temp_range = extracted_params.temperature_range_k or (298.15, 298.15)
            avg_temp = sum(temp_range) / 2

            # Store mention data
            mention_data = {
                "user_id": user_id,
                "compound_name": compound_name,
                "timestamp": timestamp,
                "temperature_range": temp_range,
                "avg_temperature": avg_temp,
                "success": success,
                "phase": compound.phase
            }
            self.compound_mentions.append(mention_data)

            # Update compound analytics
            if compound_name not in self.compound_analytics:
                self.compound_analytics[compound_name] = CompoundAnalytics(
                    compound_name=compound_name,
                    total_mentions=0,
                    unique_users=set(),
                    avg_temperature=avg_temp,
                    temperature_range=temp_range,
                    common_phases=[],
                    success_rate=1.0,
                    first_mentioned=timestamp,
                    last_mentioned=timestamp
                )

            analytics = self.compound_analytics[compound_name]
            analytics.total_mentions += 1
            analytics.unique_users.add(user_id)
            analytics.last_mentioned = timestamp

            # Update temperature statistics
            total_mentions = analytics.total_mentions
            analytics.avg_temperature = (
                (analytics.avg_temperature * (total_mentions - 1) + avg_temp) / total_mentions
            )

            # Update temperature range
            current_min, current_max = analytics.temperature_range
            analytics.temperature_range = (
                min(current_min, temp_range[0]),
                max(current_max, temp_range[1])
            )

            # Update phase information
            if compound.phase and compound.phase not in analytics.common_phases:
                analytics.common_phases.append(compound.phase)

            # Update success rate
            if success:
                analytics.success_rate = (analytics.success_rate * (total_mentions - 1) + 1.0) / total_mentions
            else:
                analytics.success_rate = (analytics.success_rate * (total_mentions - 1)) / total_mentions

    def _analyze_reaction_mentions(
        self,
        user_id: int,
        extracted_params: ExtractedReactionParameters,
        processing_time: float,
        success: bool,
        timestamp: datetime
    ) -> None:
        """Analyze reaction mentions in queries."""
        equation = extracted_params.balanced_equation
        reaction_hash = self._hash_reaction(equation)

        # Determine reaction type
        reaction_type = self._classify_reaction_type(equation)

        # Store reaction data
        reaction_data = {
            "user_id": user_id,
            "reaction_hash": reaction_hash,
            "equation": equation,
            "reaction_type": reaction_type,
            "timestamp": timestamp,
            "processing_time": processing_time,
            "success": success,
            "compounds": [c.compound_name for c in extracted_params.all_compounds],
            "temperature_range": extracted_params.temperature_range_k or (298.15, 298.15)
        }
        self.reaction_history.append(reaction_data)

        # Update reaction analytics
        if reaction_hash not in self.reaction_analytics:
            self.reaction_analytics[reaction_hash] = ReactionAnalytics(
                reaction_hash=reaction_hash,
                reaction_type=reaction_type,
                count=0,
                unique_users=set(),
                avg_temperature_range=(298.15, 298.15),
                common_compounds=[],
                success_rate=1.0,
                avg_processing_time=0.0
            )

        analytics = self.reaction_analytics[reaction_hash]
        analytics.count += 1
        analytics.unique_users.add(user_id)

        # Update average processing time
        analytics.avg_processing_time = (
            (analytics.avg_processing_time * (analytics.count - 1) + processing_time) / analytics.count
        )

        # Update temperature range
        current_min, current_max = analytics.avg_temperature_range
        temp_range = reaction_data["temperature_range"]
        analytics.avg_temperature_range = (
            min(current_min, temp_range[0]),
            max(current_max, temp_range[1])
        )

        # Update common compounds
        for compound in reaction_data["compounds"]:
            if compound not in analytics.common_compounds:
                analytics.common_compounds.append(compound)

        # Update success rate
        if success:
            analytics.success_rate = (analytics.success_rate * (analytics.count - 1) + 1.0) / analytics.count
        else:
            analytics.success_rate = (analytics.success_rate * (analytics.count - 1)) / analytics.count

    def _hash_reaction(self, equation: str) -> str:
        """Create a hash for reaction normalization."""
        # Simple normalization - can be improved
        normalized = re.sub(r'\s+', '', equation.lower())
        return str(hash(normalized))

    def _classify_reaction_type(self, equation: str) -> str:
        """Classify the type of chemical reaction."""
        equation_lower = equation.lower()

        if any(keyword in equation_lower for keyword in ['+', '→', '=', 'reaction']):
            if 'o2' in equation_lower or any(oxide in equation_lower for oxide in ['o', ' oxide']):
                return "oxidation"
            elif 'h2' in equation_lower and ('o2' in equation_lower or 'o' in equation_lower):
                return "combustion"
            elif 'h2' in equation_lower:
                return "reduction"
            elif 'h2o' in equation_lower:
                return "hydration"
            elif 'co2' in equation_lower:
                return "carbonation"
            else:
                return "synthesis"
        else:
            return "properties"

    def get_top_queries(self, limit: int = 10, time_window: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get top queries by frequency.

        Args:
            limit: Maximum number of queries to return
            time_window: Time window in hours (default: all time)

        Returns:
            List of top queries with statistics
        """
        with self._lock:
            # Filter by time window if specified
            if time_window:
                cutoff_time = datetime.now() - timedelta(hours=time_window)
                filtered_queries = [
                    q for q in self.query_history
                    if q["timestamp"] >= cutoff_time
                ]
            else:
                filtered_queries = self.query_history

            # Count query frequencies
            query_counts = Counter(q["query"] for q in filtered_queries)
            query_stats = defaultdict(lambda: {"count": 0, "total_time": 0, "successes": 0})

            for query_data in filtered_queries:
                query = query_data["query"]
                query_stats[query]["count"] += 1
                query_stats[query]["total_time"] += query_data["processing_time"]
                if query_data["success"]:
                    query_stats[query]["successes"] += 1

            # Sort and format results
            top_queries = []
            for query, stats in sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:limit]:
                query_stat = query_stats[query]
                top_queries.append({
                    "query": query,
                    "count": query_stat["count"],
                    "avg_processing_time": query_stat["total_time"] / query_stat["count"],
                    "success_rate": query_stat["successes"] / query_stat["count"],
                    "success_count": query_stat["successes"],
                    "error_count": query_stat["count"] - query_stat["successes"]
                })

            return top_queries

    def get_compound_analytics(
        self,
        limit: int = 20,
        sort_by: str = "mentions"
    ) -> List[Dict[str, Any]]:
        """
        Get compound analytics.

        Args:
            limit: Maximum number of compounds to return
            sort_by: Sort criteria ("mentions", "users", "success_rate")

        Returns:
            List of compound analytics
        """
        with self._lock:
            compounds_data = []
            for compound_name, analytics in self.compound_analytics.items():
                compounds_data.append({
                    "compound_name": compound_name,
                    "total_mentions": analytics.total_mentions,
                    "unique_users": len(analytics.unique_users),
                    "avg_temperature": analytics.avg_temperature,
                    "temperature_range": analytics.temperature_range,
                    "common_phases": analytics.common_phases,
                    "success_rate": analytics.success_rate,
                    "first_mentioned": analytics.first_mentioned.isoformat(),
                    "last_mentioned": analytics.last_mentioned.isoformat()
                })

            # Sort based on criteria
            if sort_by == "mentions":
                compounds_data.sort(key=lambda x: x["total_mentions"], reverse=True)
            elif sort_by == "users":
                compounds_data.sort(key=lambda x: x["unique_users"], reverse=True)
            elif sort_by == "success_rate":
                compounds_data.sort(key=lambda x: x["success_rate"], reverse=True)

            return compounds_data[:limit]

    def get_reaction_analytics(self, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Get reaction analytics.

        Args:
            limit: Maximum number of reactions to return

        Returns:
            List of reaction analytics
        """
        with self._lock:
            # Find equations for reaction hashes
            hash_to_equation = {}
            for reaction_data in self.reaction_history:
                if reaction_data["reaction_hash"] not in hash_to_equation:
                    hash_to_equation[reaction_data["reaction_hash"]] = reaction_data["equation"]

            reactions_data = []
            for reaction_hash, analytics in self.reaction_analytics.items():
                reactions_data.append({
                    "equation": hash_to_equation.get(reaction_hash, "Unknown"),
                    "reaction_type": analytics.reaction_type,
                    "count": analytics.count,
                    "unique_users": len(analytics.unique_users),
                    "avg_temperature_range": analytics.avg_temperature_range,
                    "common_compounds": analytics.common_compounds,
                    "success_rate": analytics.success_rate,
                    "avg_processing_time": analytics.avg_processing_time
                })

            # Sort by count
            reactions_data.sort(key=lambda x: x["count"], reverse=True)

            return reactions_data[:limit]

    def get_pattern_analytics(self) -> Dict[str, Any]:
        """Get query pattern analytics."""
        with self._lock:
            patterns_data = {}
            for pattern_name, pattern in self.query_patterns.items():
                patterns_data[pattern_name] = {
                    "pattern": pattern.pattern,
                    "count": pattern.count,
                    "avg_processing_time": pattern.avg_processing_time,
                    "success_rate": pattern.success_rate,
                    "examples": pattern.examples
                }

            return {
                "patterns": patterns_data,
                "total_patterns": len(patterns_data),
                "most_common": max(patterns_data.items(), key=lambda x: x[1]["count"])[0] if patterns_data else None
            }

    def get_usage_trends(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get usage trends over time.

        Args:
            hours: Time window in hours

        Returns:
            Usage trend data
        """
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_queries = [
                q for q in self.query_history
                if q["timestamp"] >= cutoff_time
            ]

            if not recent_queries:
                return {"error": "No data in specified time window"}

            # Hourly aggregation
            hourly_data = defaultdict(lambda: {"count": 0, "successes": 0, "total_time": 0})
            user_activity = defaultdict(lambda: {"queries": 0, "successes": 0})

            for query in recent_queries:
                hour_key = query["timestamp"].strftime("%Y-%m-%d %H:00")
                hourly_data[hour_key]["count"] += 1
                hourly_data[hour_key]["total_time"] += query["processing_time"]
                if query["success"]:
                    hourly_data[hour_key]["successes"] += 1

                user_id = query["user_id"]
                user_activity[user_id]["queries"] += 1
                if query["success"]:
                    user_activity[user_id]["successes"] += 1

            # Format hourly data
            hourly_trends = []
            for hour, stats in sorted(hourly_data.items()):
                hourly_trends.append({
                    "hour": hour,
                    "query_count": stats["count"],
                    "success_count": stats["successes"],
                    "error_count": stats["count"] - stats["successes"],
                    "success_rate": stats["successes"] / stats["count"] if stats["count"] > 0 else 0,
                    "avg_processing_time": stats["total_time"] / stats["count"] if stats["count"] > 0 else 0
                })

            # User activity statistics
            active_users = len(user_activity)
            total_user_queries = sum(stats["queries"] for stats in user_activity.values())

            return {
                "hourly_trends": hourly_trends,
                "active_users": active_users,
                "total_queries": len(recent_queries),
                "total_user_queries": total_user_queries,
                "avg_queries_per_user": total_user_queries / active_users if active_users > 0 else 0,
                "time_window_hours": hours
            }

    def export_analytics(self, filepath: str) -> None:
        """Export analytics data to JSON file."""
        with self._lock:
            export_data = {
                "export_timestamp": datetime.now().isoformat(),
                "query_patterns": {k: asdict(v) for k, v in self.query_patterns.items()},
                "compound_analytics": {k: asdict(v) for k, v in self.compound_analytics.items()},
                "reaction_analytics": {k: asdict(v) for k, v in self.reaction_analytics.items()},
                "top_queries": self.get_top_queries(50),
                "compound_stats": self.get_compound_analytics(50),
                "reaction_stats": self.get_reaction_analytics(30),
                "pattern_stats": self.get_pattern_analytics(),
                "usage_trends_24h": self.get_usage_trends(24)
            }

            # Convert sets to lists for JSON serialization
            for compound_data in export_data["compound_analytics"].values():
                compound_data["unique_users"] = list(compound_data["unique_users"])

            for reaction_data in export_data["reaction_analytics"].values():
                reaction_data["unique_users"] = list(reaction_data["unique_users"])

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

    def clear_old_data(self, days: int = 30) -> None:
        """Clear data older than specified number of days."""
        with self._lock:
            cutoff_time = datetime.now() - timedelta(days=days)

            # Clear old query history
            self.query_history = [
                q for q in self.query_history
                if q["timestamp"] >= cutoff_time
            ]

            # Clear old compound mentions
            self.compound_mentions = [
                m for m in self.compound_mentions
                if m["timestamp"] >= cutoff_time
            ]

            # Clear old reaction history
            self.reaction_history = [
                r for r in self.reaction_history
                if r["timestamp"] >= cutoff_time
            ]