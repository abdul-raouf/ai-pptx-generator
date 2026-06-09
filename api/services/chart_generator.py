import os
import uuid
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from io import StringIO

CHART_DIR = os.getenv("CHART_DIR", "chart_cache")

# def parse_data(raw: str) -> pd.DataFrame:
#     """Parse pasted CSV-style data into a DataFrame."""
#     return pd.read_csv(StringIO(raw.strip()))

def load_data_from_file(filepath: str) -> pd.DataFrame:
    path = filepath.strip()
    if path.endswith(".csv"):
        return pd.read_csv(path)
    elif path.endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file type: {path}")

def generate_chart(
    df: pd.DataFrame,
    chart_type: str,
    title: str,
    slide_index: int
) -> str:
    os.makedirs(CHART_DIR, exist_ok=True)
    output_path = os.path.join(CHART_DIR, f"chart_slide_{slide_index}.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    x_col = df.columns[0]
    y_cols = df.columns[1:]

    if chart_type == "bar":
        df.plot(kind="bar", x=x_col, y=list(y_cols), ax=ax, legend=len(y_cols) > 1)
        ax.set_xlabel("")

    elif chart_type == "line":
        df.plot(kind="line", x=x_col, y=list(y_cols), ax=ax,
                marker="o", legend=len(y_cols) > 1)
        ax.set_xlabel("")

    elif chart_type == "pie":
        y_col = y_cols[0]
        ax.pie(df[y_col], labels=df[x_col], autopct="%1.1f%%", startangle=90)
        ax.axis("equal")

    elif chart_type == "scatter":
        y_col = y_cols[0]
        ax.scatter(df[x_col], df[y_col], alpha=0.7)
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)

    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    plt.xticks(rotation=30, ha="right", fontsize=9)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    return output_path