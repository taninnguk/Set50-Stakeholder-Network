from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Any, Iterable

import networkx as nx
import pandas as pd
from pyvis.network import Network

from set_scraper import ShareholderRecord


SHAREHOLDER_COLUMNS = [
    "symbol",
    "company_name",
    "shareholder",
    "rank",
    "shares",
    "percent",
    "as_of",
    "ca_type",
    "source_url",
]


def records_to_dataframe(
    records: Iterable[ShareholderRecord | dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record, ShareholderRecord):
            rows.append(record.to_dict())
        else:
            rows.append(dict(record))

    df = pd.DataFrame(rows, columns=SHAREHOLDER_COLUMNS)
    if df.empty:
        return df

    df["rank"] = pd.to_numeric(df["rank"], errors="coerce").astype("Int64")
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce").astype("Int64")
    df["percent"] = pd.to_numeric(df["percent"], errors="coerce")
    df["company_label"] = df.apply(
        lambda row: f"{row['symbol']} - {row['company_name']}"
        if row.get("company_name")
        else row["symbol"],
        axis=1,
    )
    return df


def filter_shared_holders(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    company_counts = df.groupby("shareholder")["symbol"].nunique()
    shared_names = company_counts[company_counts > 1].index
    return df[df["shareholder"].isin(shared_names)].copy()


def build_shareholder_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    summary = (
        df.groupby("shareholder", dropna=False)
        .agg(
            company_count=("symbol", "nunique"),
            total_percent=("percent", "sum"),
            avg_percent=("percent", "mean"),
            max_percent=("percent", "max"),
            total_shares=("shares", "sum"),
            companies=("symbol", lambda values: ", ".join(sorted(set(values)))),
        )
        .reset_index()
        .sort_values(["company_count", "total_percent"], ascending=[False, False])
    )
    return summary


def build_company_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    return (
        df.groupby(["symbol", "company_name"], dropna=False)
        .agg(
            top_holder_count=("shareholder", "nunique"),
            top_holder_percent=("percent", "sum"),
            largest_holder_percent=("percent", "max"),
            as_of=("as_of", "first"),
        )
        .reset_index()
        .sort_values("top_holder_percent", ascending=False)
    )


def build_company_projection(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=["company_a", "company_b", "shared_count", "shareholders", "combined_percent"]
        )

    edges: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"shared_count": 0, "shareholders": [], "combined_percent": 0.0}
    )
    for shareholder, group in df.groupby("shareholder"):
        companies = sorted(group["symbol"].dropna().unique())
        if len(companies) < 2:
            continue

        percent_by_company = group.groupby("symbol")["percent"].max().to_dict()
        for company_a, company_b in combinations(companies, 2):
            key = (company_a, company_b)
            edges[key]["shared_count"] += 1
            edges[key]["shareholders"].append(shareholder)
            edges[key]["combined_percent"] += float(percent_by_company.get(company_a) or 0)
            edges[key]["combined_percent"] += float(percent_by_company.get(company_b) or 0)

    rows = [
        {
            "company_a": company_a,
            "company_b": company_b,
            "shared_count": data["shared_count"],
            "shareholders": ", ".join(data["shareholders"]),
            "combined_percent": data["combined_percent"],
        }
        for (company_a, company_b), data in edges.items()
    ]
    return pd.DataFrame(rows).sort_values(
        ["shared_count", "combined_percent"],
        ascending=[False, False],
    )


def build_bipartite_graph(df: pd.DataFrame) -> nx.Graph:
    graph = nx.Graph()
    if df.empty:
        return graph

    for row in df.itertuples(index=False):
        company_id = f"company::{row.symbol}"
        holder_id = f"holder::{row.shareholder}"
        graph.add_node(
            company_id,
            label=row.symbol,
            node_type="company",
            title=row.company_label,
        )
        graph.add_node(
            holder_id,
            label=row.shareholder,
            node_type="shareholder",
            title=row.shareholder,
        )
        graph.add_edge(
            company_id,
            holder_id,
            weight=float(row.percent or 0.0),
            shares=int(row.shares) if pd.notna(row.shares) else None,
            rank=int(row.rank) if pd.notna(row.rank) else None,
        )
    return graph


def build_graph_metrics(df: pd.DataFrame) -> pd.DataFrame:
    graph = build_bipartite_graph(df)
    if not graph:
        return pd.DataFrame()

    degree_centrality = nx.degree_centrality(graph)
    betweenness = nx.betweenness_centrality(graph, weight=None)
    rows = []
    for node_id, attrs in graph.nodes(data=True):
        weighted_degree = sum(
            edge_data.get("weight", 0.0)
            for _, _, edge_data in graph.edges(node_id, data=True)
        )
        rows.append(
            {
                "node": attrs.get("label"),
                "type": attrs.get("node_type"),
                "degree": graph.degree(node_id),
                "weighted_degree": weighted_degree,
                "degree_centrality": degree_centrality.get(node_id, 0.0),
                "betweenness": betweenness.get(node_id, 0.0),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["degree", "weighted_degree"],
        ascending=[False, False],
    )


def make_pyvis_network(df: pd.DataFrame, height: str = "720px") -> str:
    network = Network(
        height=height,
        width="100%",
        bgcolor="#ffffff",
        font_color="#0f172a",
        directed=False,
        cdn_resources="in_line",
    )
    if df.empty:
        return network.generate_html(notebook=False)

    shareholder_summary = build_shareholder_summary(df)
    holder_degree = shareholder_summary.set_index("shareholder")["company_count"].to_dict()
    company_percent = df.groupby("symbol")["percent"].sum().to_dict()

    for symbol, group in df.groupby("symbol", sort=True):
        label = symbol
        title = group["company_label"].iloc[0]
        size = 18 + min(float(company_percent.get(symbol, 0.0)), 80.0) * 0.25
        network.add_node(
            f"company::{symbol}",
            label=label,
            title=title,
            group="company",
            color="#006B54",
            shape="dot",
            size=size,
        )

    for shareholder, group in df.groupby("shareholder", sort=True):
        companies = holder_degree.get(shareholder, 1)
        total_percent = float(group["percent"].sum() or 0.0)
        size = 10 + min(companies * 6 + total_percent * 0.12, 34)
        color = "#F59E0B" if companies > 1 else "#94A3B8"
        label = shareholder if len(shareholder) <= 34 else f"{shareholder[:31]}..."
        title = (
            f"{shareholder}<br>"
            f"Companies: {companies}<br>"
            f"Total top-holder %: {total_percent:.2f}"
        )
        network.add_node(
            f"holder::{shareholder}",
            label=label,
            title=title,
            group="shareholder",
            color=color,
            shape="dot",
            size=size,
        )

    for row in df.itertuples(index=False):
        percent = float(row.percent or 0.0)
        width = 1 + min(percent / 4.0, 8)
        network.add_edge(
            f"company::{row.symbol}",
            f"holder::{row.shareholder}",
            value=max(percent, 0.1),
            width=width,
            title=f"{row.symbol} - {row.shareholder}: {percent:.2f}%",
        )

    network.set_options(
        """
        {
          "interaction": {"hover": true, "tooltipDelay": 80},
          "physics": {
            "solver": "forceAtlas2Based",
            "forceAtlas2Based": {
              "gravitationalConstant": -80,
              "centralGravity": 0.01,
              "springLength": 135,
              "springConstant": 0.08
            },
            "stabilization": {"enabled": true, "iterations": 180}
          },
          "nodes": {
            "font": {"size": 16, "face": "Arial"}
          },
          "edges": {
            "color": {"color": "#CBD5E1", "highlight": "#0F766E"},
            "smooth": {"type": "dynamic"}
          }
        }
        """
    )
    return network.generate_html(notebook=False)
