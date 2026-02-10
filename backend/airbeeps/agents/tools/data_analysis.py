"""
Data Analysis Tool for Agents.

Provides capabilities to analyze tabular data (CSV/Excel) from documents
in knowledge bases. Supports operations like describe, filter, aggregate,
and basic statistics.
"""

import io
import logging
import uuid
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import AgentTool, AgentToolConfig, ToolSecurityLevel
from .registry import tool_registry

logger = logging.getLogger(__name__)


class DataAnalysisOperation:
    """Supported data analysis operations."""

    DESCRIBE = "describe"  # Get statistics for all columns
    FILTER = "filter"  # Filter rows by condition
    AGGREGATE = "aggregate"  # Group by and aggregate
    HEAD = "head"  # Get first N rows
    COLUMNS = "columns"  # List column names and types
    VALUE_COUNTS = "value_counts"  # Count values in a column
    QUERY = "query"  # Execute a pandas query


@tool_registry.register
class DataAnalysisTool(AgentTool):
    """
    Tool for analyzing tabular data from knowledge base documents.

    Supports CSV and Excel files that have been ingested into the knowledge base.
    Provides operations for data exploration and basic analysis.
    """

    def __init__(
        self,
        config: AgentToolConfig | None = None,
        session: AsyncSession | None = None,
    ):
        super().__init__(config)
        self.session = session
        self.knowledge_base_ids = (
            config.parameters.get("knowledge_base_ids", []) if config else []
        )
        # Cache for loaded dataframes
        self._df_cache: dict[str, pd.DataFrame] = {}

    @property
    def name(self) -> str:
        return "analyze_data"

    @property
    def description(self) -> str:
        return (
            "Analyze tabular data (CSV/Excel) from documents in the knowledge base. "
            "Operations: 'describe' (statistics), 'filter' (filter rows), "
            "'aggregate' (group and aggregate), 'head' (first N rows), "
            "'columns' (list columns), 'value_counts' (count values), "
            "'query' (pandas query expression)."
        )

    @property
    def security_level(self) -> ToolSecurityLevel:
        return ToolSecurityLevel.SAFE

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "UUID of the document to analyze (must be CSV or Excel)",
                },
                "operation": {
                    "type": "string",
                    "description": "Analysis operation to perform",
                    "enum": [
                        "describe",
                        "filter",
                        "aggregate",
                        "head",
                        "columns",
                        "value_counts",
                        "query",
                    ],
                    "default": "describe",
                },
                "params": {
                    "type": "object",
                    "description": "Operation-specific parameters",
                    "properties": {
                        "column": {
                            "type": "string",
                            "description": "Column name for column-specific operations",
                        },
                        "condition": {
                            "type": "string",
                            "description": "Filter condition (e.g., 'age > 30')",
                        },
                        "group_by": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Columns to group by",
                        },
                        "agg_func": {
                            "type": "string",
                            "description": "Aggregation function (sum, mean, count, min, max)",
                            "default": "sum",
                        },
                        "agg_column": {
                            "type": "string",
                            "description": "Column to aggregate",
                        },
                        "n": {
                            "type": "integer",
                            "description": "Number of rows for head operation",
                            "default": 10,
                        },
                        "query_expr": {
                            "type": "string",
                            "description": "Pandas query expression",
                        },
                    },
                },
            },
            "required": ["document_id", "operation"],
        }

    async def execute(
        self,
        document_id: str,
        operation: str = "describe",
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute data analysis operation."""
        params = params or {}

        try:
            if not self.session:
                return {"error": "Database session not available"}

            # Load the dataframe
            df = await self._load_dataframe(document_id)
            if df is None:
                return {"error": f"Could not load document {document_id}"}

            # Execute operation
            if operation == "describe":
                return await self._describe(df)

            if operation == "filter":
                condition = params.get("condition")
                if not condition:
                    return {"error": "Filter operation requires 'condition' parameter"}
                return await self._filter(df, condition)

            if operation == "aggregate":
                group_by = params.get("group_by", [])
                agg_func = params.get("agg_func", "sum")
                agg_column = params.get("agg_column")
                return await self._aggregate(df, group_by, agg_func, agg_column)

            if operation == "head":
                n = params.get("n", 10)
                return await self._head(df, n)

            if operation == "columns":
                return await self._columns(df)

            if operation == "value_counts":
                column = params.get("column")
                if not column:
                    return {
                        "error": "value_counts operation requires 'column' parameter"
                    }
                return await self._value_counts(df, column)

            if operation == "query":
                query_expr = params.get("query_expr")
                if not query_expr:
                    return {"error": "Query operation requires 'query_expr' parameter"}
                return await self._query(df, query_expr)

            return {"error": f"Unknown operation: {operation}"}

        except Exception as e:
            logger.exception(f"Data analysis failed: {e}")
            return {"error": str(e)}

    async def _load_dataframe(self, document_id: str) -> pd.DataFrame | None:
        """Load a document as a pandas DataFrame."""
        # Check cache
        if document_id in self._df_cache:
            return self._df_cache[document_id]

        try:
            from airbeeps.files.service import FileService
            from airbeeps.rag.models import Document

            # Get document
            doc_uuid = uuid.UUID(document_id)
            result = await self.session.execute(
                select(Document).where(Document.id == doc_uuid)
            )
            document = result.scalar_one_or_none()

            if not document:
                logger.warning(f"Document not found: {document_id}")
                return None

            # Check if it's a tabular file
            file_type = document.file_type
            if file_type not in {"csv", "xls", "xlsx"}:
                logger.warning(f"Document is not tabular: {file_type}")
                return None

            # Load file content
            file_service = FileService(self.session)
            file_bytes = await file_service.download_file(document.file_path)

            if file_bytes is None:
                logger.warning(f"Could not download file: {document.file_path}")
                return None

            # Read into DataFrame
            if isinstance(file_bytes, bytes):
                file_io = io.BytesIO(file_bytes)
            else:
                file_io = file_bytes

            if file_type == "csv":
                df = pd.read_csv(file_io)
            else:
                df = pd.read_excel(file_io)

            # Cache and return
            self._df_cache[document_id] = df
            logger.info(f"Loaded DataFrame for {document_id}: {df.shape}")
            return df

        except Exception as e:
            logger.exception(f"Failed to load dataframe: {e}")
            return None

    async def _describe(self, df: pd.DataFrame) -> dict[str, Any]:
        """Get descriptive statistics."""
        # Get basic info
        info = {
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": df.columns.tolist(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        }

        # Get numeric statistics
        try:
            numeric_stats = df.describe().to_dict()
            # Convert numpy types to Python types
            for col in numeric_stats:
                for stat in numeric_stats[col]:
                    val = numeric_stats[col][stat]
                    if pd.isna(val):
                        numeric_stats[col][stat] = None
                    elif hasattr(val, "item"):
                        numeric_stats[col][stat] = val.item()
            info["statistics"] = numeric_stats
        except Exception:
            info["statistics"] = {}

        # Get null counts
        null_counts = df.isnull().sum().to_dict()
        info["null_counts"] = {k: int(v) for k, v in null_counts.items()}

        return {
            "operation": "describe",
            "result": info,
        }

    async def _filter(self, df: pd.DataFrame, condition: str) -> dict[str, Any]:
        """Filter rows by condition."""
        try:
            # Sanitize condition to prevent code injection
            if not self._is_safe_condition(condition):
                return {"error": "Unsafe filter condition"}

            filtered = df.query(condition)
            return {
                "operation": "filter",
                "condition": condition,
                "original_rows": len(df),
                "filtered_rows": len(filtered),
                "result": filtered.head(50).to_dict(orient="records"),
            }
        except Exception as e:
            return {"error": f"Filter failed: {e}"}

    async def _aggregate(
        self,
        df: pd.DataFrame,
        group_by: list[str],
        agg_func: str,
        agg_column: str | None,
    ) -> dict[str, Any]:
        """Group by and aggregate."""
        try:
            if not group_by:
                return {"error": "group_by columns required"}

            # Validate columns exist
            for col in group_by:
                if col not in df.columns:
                    return {"error": f"Column not found: {col}"}

            # Validate aggregation function
            valid_agg_funcs = ["sum", "mean", "count", "min", "max", "std", "median"]
            if agg_func not in valid_agg_funcs:
                return {"error": f"Invalid agg_func. Use one of: {valid_agg_funcs}"}

            if agg_column:
                if agg_column not in df.columns:
                    return {"error": f"Column not found: {agg_column}"}
                grouped = df.groupby(group_by)[agg_column].agg(agg_func)
            else:
                grouped = df.groupby(group_by).agg(agg_func)

            result_df = grouped.reset_index()
            return {
                "operation": "aggregate",
                "group_by": group_by,
                "agg_func": agg_func,
                "agg_column": agg_column,
                "result": result_df.head(100).to_dict(orient="records"),
            }
        except Exception as e:
            return {"error": f"Aggregation failed: {e}"}

    async def _head(self, df: pd.DataFrame, n: int = 10) -> dict[str, Any]:
        """Get first N rows."""
        n = min(n, 100)  # Limit to 100 rows
        return {
            "operation": "head",
            "n": n,
            "total_rows": len(df),
            "result": df.head(n).to_dict(orient="records"),
        }

    async def _columns(self, df: pd.DataFrame) -> dict[str, Any]:
        """List column names and types."""
        columns = []
        for col in df.columns:
            col_info = {
                "name": col,
                "dtype": str(df[col].dtype),
                "null_count": int(df[col].isnull().sum()),
                "unique_count": int(df[col].nunique()),
            }

            # Add sample values
            non_null = df[col].dropna()
            if len(non_null) > 0:
                col_info["sample_values"] = non_null.head(3).tolist()

            columns.append(col_info)

        return {
            "operation": "columns",
            "total_columns": len(columns),
            "result": columns,
        }

    async def _value_counts(self, df: pd.DataFrame, column: str) -> dict[str, Any]:
        """Count values in a column."""
        if column not in df.columns:
            return {"error": f"Column not found: {column}"}

        value_counts = df[column].value_counts().head(50)
        return {
            "operation": "value_counts",
            "column": column,
            "total_unique": int(df[column].nunique()),
            "result": value_counts.to_dict(),
        }

    async def _query(self, df: pd.DataFrame, query_expr: str) -> dict[str, Any]:
        """Execute a pandas query expression."""
        try:
            # Sanitize query to prevent code injection
            if not self._is_safe_condition(query_expr):
                return {"error": "Unsafe query expression"}

            result = df.query(query_expr)
            return {
                "operation": "query",
                "query_expr": query_expr,
                "original_rows": len(df),
                "result_rows": len(result),
                "result": result.head(50).to_dict(orient="records"),
            }
        except Exception as e:
            return {"error": f"Query failed: {e}"}

    def _is_safe_condition(self, condition: str) -> bool:
        """Check if a condition/query is safe to execute."""
        # Block potentially dangerous patterns
        dangerous_patterns = [
            "__",  # Dunder methods
            "import",
            "exec(",
            "eval(",
            "compile(",
            "open(",
            "os.",
            "sys.",
            "subprocess",
            "lambda",
            "def ",
            "class ",
            ";",  # Statement separator
        ]

        condition_lower = condition.lower()
        for pattern in dangerous_patterns:
            if pattern in condition_lower:
                logger.warning(f"Blocked dangerous pattern in condition: {pattern}")
                return False

        return True


@tool_registry.register
class ListTabularDocumentsTool(AgentTool):
    """
    List tabular documents available for analysis in the knowledge base.
    """

    def __init__(
        self,
        config: AgentToolConfig | None = None,
        session: AsyncSession | None = None,
    ):
        super().__init__(config)
        self.session = session
        self.knowledge_base_ids = (
            config.parameters.get("knowledge_base_ids", []) if config else []
        )

    @property
    def name(self) -> str:
        return "list_tabular_documents"

    @property
    def description(self) -> str:
        return (
            "List CSV and Excel documents available for analysis in the knowledge base."
        )

    @property
    def security_level(self) -> ToolSecurityLevel:
        return ToolSecurityLevel.SAFE

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self) -> dict[str, Any]:
        """List available tabular documents."""
        try:
            if not self.session:
                return {"error": "Database session not available"}

            if not self.knowledge_base_ids:
                return {"error": "No knowledge base configured"}

            from sqlalchemy import and_

            from airbeeps.rag.models import Document

            documents = []
            for kb_id_str in self.knowledge_base_ids:
                try:
                    kb_id = uuid.UUID(kb_id_str)
                    result = await self.session.execute(
                        select(Document).where(
                            and_(
                                Document.knowledge_base_id == kb_id,
                                Document.file_type.in_(["csv", "xls", "xlsx"]),
                                Document.status == "ACTIVE",
                            )
                        )
                    )
                    for doc in result.scalars():
                        documents.append(
                            {
                                "id": str(doc.id),
                                "title": doc.title,
                                "file_type": doc.file_type,
                                "knowledge_base_id": str(kb_id),
                            }
                        )
                except Exception:
                    continue

            return {
                "total": len(documents),
                "documents": documents,
            }

        except Exception as e:
            return {"error": str(e)}
