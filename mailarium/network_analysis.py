"""Communication network analysis using NetworkX."""
# pylint: disable=too-many-branches,too-many-locals

from __future__ import annotations

import collections
import logging
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .email_db import EmailDatabase

from .repo_paths import validate_new_output_path

logger = logging.getLogger(__name__)

# Maximum entries in per-instance analysis caches.  The graph is static
# once built, so distinct cache keys only vary by ``top_n`` - 16 slots
# is generous while preventing unbounded growth.
_ANALYSIS_CACHE_MAX = 16
_BETWEENNESS_CACHE_MAX = 8
_DatedSenderEvent = tuple[datetime, str]


class CommunicationNetwork:
    """Graph-based analysis of email communication patterns."""

    def __init__(self, email_db: EmailDatabase) -> None:
        self._db = email_db
        self._graph = None
        # Bounded LRU caches - evict oldest entry when full.
        self._analysis_cache: collections.OrderedDict[tuple, dict[str, Any]] = collections.OrderedDict()
        self._betweenness_cache: collections.OrderedDict[tuple, dict[str, float]] = collections.OrderedDict()

    def top_contacts(self, email_address: str, limit: int = 20) -> list[dict[str, Any]]:
        """Top communication partners (bidirectional frequency)."""
        return self._db.top_contacts(email_address, limit=limit)

    def communication_between(self, email_a: str, email_b: str) -> dict[str, Any]:
        """Bidirectional communication stats between two addresses."""
        return self._db.communication_between(email_a, email_b)

    def network_analysis(self, top_n: int = 20) -> dict[str, Any]:
        """Summarize centrality, communities, and bridges, caching results by graph shape."""
        nx = self._ensure_graph()
        if nx is None:
            return {"error": "networkx not installed. Run: pip install networkx"}

        if self._graph.number_of_nodes() == 0:
            return {
                "total_nodes": 0,
                "total_edges": 0,
                "most_connected": [],
                "communities": [],
                "bridge_nodes": [],
            }

        # Check result cache (keyed by node count + edge count + top_n), with LRU eviction
        cache_key = (self._graph.number_of_nodes(), self._graph.number_of_edges(), top_n)
        if cache_key in self._analysis_cache:
            self._analysis_cache.move_to_end(cache_key)
            return self._analysis_cache[cache_key]

        # Degree centrality (most connected)
        degree = nx.degree_centrality(self._graph)
        most_connected = sorted(degree.items(), key=lambda x: x[1], reverse=True)[:top_n]

        # Betweenness centrality (bridge nodes) - approximate for large graphs
        bridge_nodes = self._get_bridge_nodes(nx, top_n)

        # Community detection
        communities: list[list[str]] = []
        try:
            undirected = self._to_undirected_summed(nx)
            if hasattr(nx.community, "louvain_communities"):
                comms = nx.community.louvain_communities(undirected, seed=42)
            else:
                comms = nx.community.label_propagation_communities(undirected)
            communities = [sorted(c) for c in comms]
            communities.sort(key=len, reverse=True)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Community detection failed", exc_info=True)

        result = {
            "total_nodes": self._graph.number_of_nodes(),
            "total_edges": self._graph.number_of_edges(),
            "most_connected": [{"email": email, "centrality": round(score, 4)} for email, score in most_connected],
            "communities": [{"members": c} for c in communities[:top_n]],
            "bridge_nodes": [{"email": email, "betweenness": round(score, 4)} for email, score in bridge_nodes],
        }
        self._analysis_cache[cache_key] = result
        if len(self._analysis_cache) > _ANALYSIS_CACHE_MAX:
            self._analysis_cache.popitem(last=False)  # evict oldest
        return result

    def _get_betweenness(self, nx) -> dict[str, float]:
        """Cache bridge scores that treat frequent correspondence as lower path cost."""
        cache_key = (self._graph.number_of_nodes(), self._graph.number_of_edges())
        if cache_key in self._betweenness_cache:
            self._betweenness_cache.move_to_end(cache_key)
            return self._betweenness_cache[cache_key]

        # Build a copy of the graph with inverted weights for path cost
        cost_graph = self._graph.copy()
        for _u, _v, data in cost_graph.edges(data=True):
            w = data.get("weight", 1)
            data["cost"] = 1.0 / max(w, 1)

        try:
            n_nodes = cost_graph.number_of_nodes()
            if n_nodes > 100:
                betweenness = nx.betweenness_centrality(cost_graph, weight="cost", k=min(n_nodes, 100))
            else:
                betweenness = nx.betweenness_centrality(cost_graph, weight="cost")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("betweenness_centrality failed", exc_info=True)
            betweenness = {}
        self._betweenness_cache[cache_key] = betweenness
        if len(self._betweenness_cache) > _BETWEENNESS_CACHE_MAX:
            self._betweenness_cache.popitem(last=False)  # evict oldest
        return betweenness

    def _get_bridge_nodes(self, nx, top_n: int) -> list[tuple[str, float]]:
        """Get top bridge nodes by betweenness centrality."""
        betweenness = self._get_betweenness(nx)
        return sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:top_n]

    def _to_undirected_summed(self, nx) -> Any:
        """Combine reciprocal message counts so undirected weights reflect total exchange."""
        undirected = nx.Graph()
        for u, v, data in self._graph.edges(data=True):
            w = data.get("weight", 1)
            if undirected.has_edge(u, v):
                undirected[u][v]["weight"] += w
            else:
                undirected.add_edge(u, v, weight=w)
        return undirected

    def _ensure_graph(self):
        """Import NetworkX lazily and materialize the directed graph from database edges."""
        try:
            import networkx as nx
        except ImportError:
            return None

        if self._graph is None:
            self._graph = nx.DiGraph()
            for sender, recipient, count in self._db.all_edges():
                self._graph.add_edge(sender, recipient, weight=count)
        return nx

    def find_paths(self, source: str, target: str, max_hops: int = 3, top_k: int = 5) -> list[dict[str, Any]]:
        """Find shortest communication paths between two email addresses.

        Returns:
            List of {"nodes": [str], "edges": [{"from": str, "to": str, "weight": int}], "hops": int}
        """
        if max_hops < 1:
            max_hops = 1
        if top_k < 1:
            top_k = 1

        nx = self._ensure_graph()
        if nx is None:
            return [{"error": "networkx not installed"}]

        if self._graph.number_of_nodes() == 0:
            return []

        # Build undirected graph with inverted weights (1/count) for
        # shortest-path computation: stronger connections = shorter paths.
        undirected = self._weighted_undirected_graph(nx)

        if source not in undirected or target not in undirected:
            return []

        if source == target:
            return [{"error": "source and target are the same address"}]

        return self._shortest_paths(nx, undirected, source, target, max_hops, top_k)

    def _weighted_undirected_graph(self, nx):
        """Attach inverse-frequency traversal costs to combined communication edges."""
        undirected = self._to_undirected_summed(nx)
        for _u, _v, data in undirected.edges(data=True):
            data["cost"] = 1.0 / max(data.get("weight", 1), 1)
        return undirected

    def _shortest_paths(self, nx, graph, source, target, max_hops, top_k):
        """Collect the best simple paths while enforcing hop and result limits."""
        paths = []
        try:
            for path_nodes in nx.shortest_simple_paths(graph, source, target, weight="cost"):
                if len(path_nodes) - 1 > max_hops:
                    break
                edges = self._path_edges(path_nodes)

                paths.append(
                    {
                        "nodes": list(path_nodes),
                        "edges": edges,
                        "hops": len(path_nodes) - 1,
                    }
                )
                if len(paths) >= top_k:
                    break
        except nx.NetworkXNoPath:
            pass  # no path exists between the two nodes - return empty list

        return paths

    def _path_edges(self, nodes):
        """Serialize path edges with communication counts from both directions."""
        edges = []
        for a, b in pairwise(nodes):
            weight = self._graph[a][b].get("weight", 0) if self._graph.has_edge(a, b) else 0
            weight += self._graph[b][a].get("weight", 0) if self._graph.has_edge(b, a) else 0
            edges.append({"from": a, "to": b, "weight": weight})
        return edges

    def shared_recipients(self, email_addresses: list[str], min_shared: int = 2) -> list[dict[str, Any]]:
        """Find recipients who received emails from ALL specified senders.

        Delegates to EmailDatabase SQL query for accuracy.

        Returns:
            List of {"recipient": str, "senders": [str], "total_emails": int}
        """
        return self._db.shared_recipients_query(email_addresses, min_shared=min_shared)

    def coordinated_timing(
        self,
        email_addresses: list[str],
        window_hours: int = 24,
        min_events: int = 3,
    ) -> list[dict[str, Any]]:
        """Detect time windows where multiple senders were active simultaneously.

        Returns:
            List of {"window_start": str, "window_end": str, "senders": [str], "email_count": int}
        """
        if len(email_addresses) < 2:
            return []

        if window_hours < 1:
            window_hours = 1

        timeline = self._db.sender_activity_timeline(email_addresses)
        if not timeline:
            return []

        # Parse dates
        dated_events = _dated_sender_events(timeline)

        if not dated_events:
            return []

        dated_events.sort(key=lambda x: x[0])
        window_delta = timedelta(hours=window_hours)

        return _coordinated_timing_windows(dated_events, window_delta, min_events)

    def relationship_summary(self, email_address: str, limit: int = 20) -> dict[str, Any]:
        """Full profile for a single email address.

        Returns:
            {"email": str, "top_contacts": [...], "community": [str],
             "bridge_score": float, "send_count": int, "receive_count": int}
        """
        top_contacts = self.top_contacts(email_address, limit=limit)

        nx = self._ensure_graph()
        bridge_score = 0.0
        community: list[str] = []
        send_count = 0
        receive_count = 0

        if nx and self._graph.number_of_nodes() > 0 and email_address in self._graph:
            # Bridge score - reuse cached betweenness
            try:
                betweenness = self._get_betweenness(nx)
                bridge_score = round(betweenness.get(email_address, 0.0), 4)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug("bridge_score failed for %r", email_address, exc_info=True)

            # Community - reuse cached analysis for consistency
            try:
                analysis = self.network_analysis(top_n=20)
                for comm_entry in analysis.get("communities", []):
                    members = comm_entry.get("members", [])
                    if email_address in members:
                        community = members
                        break
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug("community detection failed for %r", email_address, exc_info=True)

            # Send/receive counts from graph edges
            send_count = sum(data.get("weight", 0) for _, _, data in self._graph.out_edges(email_address, data=True))
            receive_count = sum(data.get("weight", 0) for _, _, data in self._graph.in_edges(email_address, data=True))

        return {
            "email": email_address,
            "top_contacts": top_contacts,
            "community": community,
            "bridge_score": bridge_score,
            "send_count": send_count,
            "receive_count": receive_count,
        }

    def export_graphml(self, output_path: str) -> dict[str, Any]:
        """Export the communication graph as GraphML for external tools.

        The GraphML format is supported by Gephi, Cytoscape, and other
        network visualization tools.

        Args:
            output_path: File path to write the .graphml file.

        Returns:
            Dict with node/edge counts and the output path.
        """
        nx = self._ensure_graph()
        if nx is None:
            return {"error": "networkx not installed. Run: pip install networkx"}

        output = validate_new_output_path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(self._graph, str(output))

        return {
            "output_path": output_path,
            "total_nodes": self._graph.number_of_nodes(),
            "total_edges": self._graph.number_of_edges(),
        }


def _dated_sender_events(timeline: list[dict[str, Any]]) -> list[_DatedSenderEvent]:
    """Normalize dated sender activity into sortable events for timing analysis."""
    events: list[_DatedSenderEvent] = []
    for entry in timeline:
        try:
            parsed = datetime.fromisoformat(entry["date"].replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(UTC).replace(tzinfo=None)
            events.append((parsed, entry["sender_email"]))
        except ValueError, TypeError:
            continue
    return events


def _coordinated_timing_windows(
    dated_events: list[_DatedSenderEvent],
    window_delta: timedelta,
    min_events: int,
) -> list[dict[str, Any]]:
    """Return qualifying non-overlapping sender activity windows."""
    results: list[dict[str, Any]] = []
    last_window_end: datetime | None = None
    for start_index, (window_start, _) in enumerate(dated_events):
        # Anchors at the prior inclusive endpoint are part of that result.
        if last_window_end is not None and window_start <= last_window_end:
            continue

        window_end = window_start + window_delta
        senders, count = _sender_window_summary(dated_events, start_index, window_end)
        if len(senders) < 2 or count < min_events:
            continue

        results.append(
            {
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "senders": sorted(senders),
                "email_count": count,
            }
        )
        last_window_end = window_end

    return results


def _sender_window_summary(
    dated_events: list[_DatedSenderEvent],
    start_index: int,
    window_end: datetime,
) -> tuple[set[str], int]:
    """Count events and senders from an anchor through its inclusive endpoint."""
    senders: set[str] = set()
    end_index = start_index
    while end_index < len(dated_events) and dated_events[end_index][0] <= window_end:
        senders.add(dated_events[end_index][1])
        end_index += 1
    return senders, end_index - start_index
