"""
Database connector for thermodynamic compounds search.

This module provides database connection management and SQL execution
functionality for the search module.
"""

import sqlite3
from typing import List, Dict, Any, Optional, Union, Tuple
from pathlib import Path
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseConnector:
    """
    Database connector for SQLite thermodynamic database.

    Provides connection management, query execution, and error handling
    for searching thermodynamic compound data.
    """

    def __init__(self, db_path: Union[str, Path]):
        """
        Initialize database connector.

        Args:
            db_path: Path to SQLite database file

        Raises:
            ValueError: If db_path is empty or None
        """
        if not db_path:
            raise ValueError("Database path cannot be empty")

        self.db_path = Path(db_path)
        self._connection: Optional[sqlite3.Connection] = None

        logger.info(f"DatabaseConnector initialized with path: {self.db_path}")

    def connect(self) -> None:
        """
        Establish connection to the database.

        Raises:
            FileNotFoundError: If database file doesn't exist
            sqlite3.Error: If connection fails
        """
        if self._connection:
            logger.debug("Database already connected")
            return

        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {self.db_path}")

        try:
            self._connection = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,  # 30 second timeout
                check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row  # Enable dict-like access
            logger.info(f"Successfully connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database {self.db_path}: {e}")
            raise

    def disconnect(self) -> None:
        """Close database connection."""
        if self._connection:
            try:
                self._connection.close()
                logger.info("Database connection closed")
            except sqlite3.Error as e:
                logger.warning(f"Error closing database connection: {e}")
            finally:
                self._connection = None

    def is_connected(self) -> bool:
        """
        Check if database connection is active.

        Returns:
            True if connected, False otherwise
        """
        return self._connection is not None

    def execute_query(
        self,
        query: str,
        params: Optional[List[Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute SQL query and return results.

        Args:
            query: SQL query string
            params: Optional query parameters

        Returns:
            List of dictionaries representing rows

        Raises:
            sqlite3.Error: If query execution fails
        """
        if not self._connection:
            self.connect()

        if params is None:
            params = []

        try:
            cursor = self._connection.cursor()
            logger.debug(f"Executing query: {query[:100]}... with params: {params}")

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # Convert Row objects to dictionaries
            results = [dict(row) for row in rows]

            logger.debug(f"Query returned {len(results)} rows")
            return results

        except sqlite3.Error as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            raise

    def execute_query_with_params(
        self,
        query: str,
        params: List[Any]
    ) -> List[Dict[str, Any]]:
        """
        Execute SQL query with parameters.

        This is an alternative method that explicitly separates the query
        and parameters, useful when the query contains ? placeholders.

        Args:
            query: SQL query string with ? placeholders
            params: List of parameter values

        Returns:
            List of dictionaries representing rows
        """
        return self.execute_query(query, params)

    def execute_single_row(
        self,
        query: str,
        params: Optional[List[Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute query and return first row only.

        Args:
            query: SQL query string
            params: Optional query parameters

        Returns:
            Dictionary representing first row, or None if no results
        """
        results = self.execute_query(query, params)
        return results[0] if results else None

    def execute_scalar(
        self,
        query: str,
        params: Optional[List[Any]] = None
    ) -> Any:
        """
        Execute query and return single value from first column of first row.

        Args:
            query: SQL query string
            params: Optional query parameters

        Returns:
            Single scalar value, or None if no results
        """
        row = self.execute_single_row(query, params)
        if row:
            # Return first column value
            return next(iter(row.values()))
        return None

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get table schema information.

        Args:
            table_name: Name of the table

        Returns:
            List of column information dictionaries
        """
        query = f"PRAGMA table_info({table_name})"
        return self.execute_query(query)

    def get_table_count(self, table_name: str) -> int:
        """
        Get total row count for a table.

        Args:
            table_name: Name of the table

        Returns:
            Total number of rows in the table
        """
        query = f"SELECT COUNT(*) as count FROM {table_name}"
        result = self.execute_scalar(query)
        return int(result) if result is not None else 0

    def check_connection(self) -> bool:
        """
        Test database connection with simple query.

        Returns:
            True if connection is working, False otherwise
        """
        try:
            self.execute_scalar("SELECT 1")
            return True
        except Exception as e:
            logger.warning(f"Connection check failed: {e}")
            return False

    def __enter__(self):
        """
        Context manager entry.

        Returns:
            Self for use in 'with' statement
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit.

        Args:
            exc_type: Exception type if any
            exc_val: Exception value if any
            exc_tb: Exception traceback if any
        """
        self.disconnect()

    def __repr__(self) -> str:
        """String representation of DatabaseConnector."""
        status = "connected" if self.is_connected() else "disconnected"
        return f"DatabaseConnector(path='{self.db_path}', status={status})"


@contextmanager
def get_db_connection(db_path: Union[str, Path]):
    """
    Context manager for database connections.

    Args:
        db_path: Path to SQLite database file

    Yields:
        DatabaseConnector instance
    """
    connector = DatabaseConnector(db_path)
    try:
        with connector:
            yield connector
    except Exception as e:
        logger.error(f"Database operation failed: {e}")
        raise