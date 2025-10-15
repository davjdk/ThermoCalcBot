"""
Unit tests for DatabaseConnector.

This module tests the database connection and query execution functionality
of the DatabaseConnector class.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.thermo_agents.search.database_connector import DatabaseConnector, get_db_connection


class TestDatabaseConnector:
    """Test cases for DatabaseConnector class."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Create a temporary database file
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)

        # Create a test database
        self._create_test_database()

        # Initialize connector
        self.connector = DatabaseConnector(self.db_path)

    def teardown_method(self):
        """Clean up after each test method."""
        # Disconnect if connected
        if self.connector.is_connected():
            self.connector.disconnect()

        # Remove temporary database file
        if self.db_path.exists():
            self.db_path.unlink()

    def _create_test_database(self):
        """Create a test database with sample data."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            # Create test table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS compounds (
                    ID INTEGER PRIMARY KEY,
                    Formula TEXT,
                    Phase TEXT,
                    Tmin REAL,
                    Tmax REAL,
                    H298 REAL,
                    S298 REAL,
                    ReliabilityClass INTEGER
                )
            """)

            # Insert test data
            test_data = [
                (1, 'H2O', 'l', 273.15, 373.15, -285.83, 69.91, 1),
                (2, 'H2O', 'g', 373.15, 673.15, -241.82, 188.72, 1),
                (3, 'HCl', 'g', 100.0, 1000.0, -92.30, 186.69, 1),
                (4, 'CO2', 'g', 100.0, 2000.0, -393.51, 213.74, 1),
                (5, 'NH3', 'g', 100.0, 700.0, -45.94, 192.77, 2),
            ]

            cursor.executemany("""
                INSERT INTO compounds (ID, Formula, Phase, Tmin, Tmax, H298, S298, ReliabilityClass)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, test_data)

            conn.commit()

    def test_init_with_valid_path(self):
        """Test connector initialization with valid path."""
        connector = DatabaseConnector(self.db_path)
        assert connector.db_path == self.db_path
        assert not connector.is_connected()

    def test_init_with_empty_path(self):
        """Test connector initialization with empty path raises ValueError."""
        with pytest.raises(ValueError, match="Database path cannot be empty"):
            DatabaseConnector("")

        with pytest.raises(ValueError, match="Database path cannot be empty"):
            DatabaseConnector(None)

    def test_connect_success(self):
        """Test successful database connection."""
        assert not self.connector.is_connected()
        self.connector.connect()
        assert self.connector.is_connected()

    def test_connect_nonexistent_file(self):
        """Test connection to nonexistent file raises FileNotFoundError."""
        nonexistent_path = Path("/nonexistent/path/database.db")
        connector = DatabaseConnector(nonexistent_path)

        with pytest.raises(FileNotFoundError, match="Database file not found"):
            connector.connect()

    def test_connect_already_connected(self):
        """Test connecting when already connected doesn't create new connection."""
        self.connector.connect()
        original_connection = self.connector._connection

        # Connect again
        self.connector.connect()

        # Should be the same connection
        assert self.connector._connection is original_connection

    def test_disconnect_success(self):
        """Test successful database disconnection."""
        self.connector.connect()
        assert self.connector.is_connected()

        self.connector.disconnect()
        assert not self.connector.is_connected()
        assert self.connector._connection is None

    def test_disconnect_not_connected(self):
        """Test disconnecting when not connected doesn't raise error."""
        # Should not raise any exception
        self.connector.disconnect()
        assert not self.connector.is_connected()

    def test_is_connected_status(self):
        """Test is_connected status tracking."""
        assert not self.connector.is_connected()

        self.connector.connect()
        assert self.connector.is_connected()

        self.connector.disconnect()
        assert not self.connector.is_connected()

    def test_execute_query_success(self):
        """Test successful query execution."""
        self.connector.connect()

        results = self.connector.execute_query("SELECT * FROM compounds")

        assert len(results) == 5
        assert results[0]['Formula'] == 'H2O'
        assert results[0]['Phase'] == 'l'

    def test_execute_query_with_params(self):
        """Test query execution with parameters."""
        self.connector.connect()

        results = self.connector.execute_query(
            "SELECT * FROM compounds WHERE Formula = ?",
            ['H2O']
        )

        assert len(results) == 2
        assert all(r['Formula'] == 'H2O' for r in results)

    def test_execute_query_auto_connect(self):
        """Test that execute_query automatically connects if not connected."""
        assert not self.connector.is_connected()

        results = self.connector.execute_query("SELECT COUNT(*) as count FROM compounds")

        assert self.connector.is_connected()
        assert len(results) == 1
        assert results[0]['count'] == 5

    def test_execute_query_error(self):
        """Test query execution with invalid SQL raises error."""
        self.connector.connect()

        with pytest.raises(sqlite3.Error):
            self.connector.execute_query("INVALID SQL QUERY")

    def test_execute_query_with_params_empty_list(self):
        """Test query execution with empty params list."""
        self.connector.connect()

        results = self.connector.execute_query("SELECT * FROM compounds LIMIT 1", [])

        assert len(results) == 1

    def test_execute_query_with_params_none(self):
        """Test query execution with None params."""
        self.connector.connect()

        results = self.connector.execute_query("SELECT * FROM compounds LIMIT 1", None)

        assert len(results) == 1

    def test_execute_query_with_params_method(self):
        """Test execute_query_with_params method."""
        self.connector.connect()

        results = self.connector.execute_query_with_params(
            "SELECT * FROM compounds WHERE ReliabilityClass = ?",
            [1]
        )

        assert len(results) == 4
        assert all(r['ReliabilityClass'] == 1 for r in results)

    def test_execute_single_row_success(self):
        """Test executing query that returns single row."""
        self.connector.connect()

        result = self.connector.execute_single_row(
            "SELECT * FROM compounds WHERE ID = ?",
            [1]
        )

        assert result is not None
        assert result['Formula'] == 'H2O'
        assert result['Phase'] == 'l'

    def test_execute_single_row_no_results(self):
        """Test executing query that returns no results."""
        self.connector.connect()

        result = self.connector.execute_single_row(
            "SELECT * FROM compounds WHERE ID = ?",
            [999]
        )

        assert result is None

    def test_execute_scalar_success(self):
        """Test executing scalar query."""
        self.connector.connect()

        result = self.connector.execute_scalar("SELECT COUNT(*) FROM compounds")

        assert result == 5

    def test_execute_scalar_no_results(self):
        """Test executing scalar query with no results."""
        self.connector.connect()

        result = self.connector.execute_scalar(
            "SELECT Formula FROM compounds WHERE ID = ?",
            [999]
        )

        assert result is None

    def test_get_table_info(self):
        """Test getting table schema information."""
        self.connector.connect()

        table_info = self.connector.get_table_info('compounds')

        assert len(table_info) > 0
        column_names = [col['name'] for col in table_info]
        assert 'ID' in column_names
        assert 'Formula' in column_names
        assert 'Phase' in column_names

    def test_get_table_count(self):
        """Test getting table row count."""
        self.connector.connect()

        count = self.connector.get_table_count('compounds')

        assert count == 5

    def test_check_connection_success(self):
        """Test connection check when connected."""
        self.connector.connect()

        assert self.connector.check_connection() is True

    def test_check_connection_not_connected(self):
        """Test connection check when not connected."""
        assert self.connector.check_connection() is False

    def test_check_connection_with_error(self):
        """Test connection check when connection is broken."""
        self.connector.connect()

        # Simulate broken connection
        self.connector._connection.close()
        self.connector._connection = None

        assert self.connector.check_connection() is False

    def test_context_manager_success(self):
        """Test using connector as context manager."""
        with DatabaseConnector(self.db_path) as connector:
            assert connector.is_connected()

            results = connector.execute_query("SELECT COUNT(*) as count FROM compounds")
            assert results[0]['count'] == 5

        # Should be disconnected after context
        assert not connector.is_connected()

    def test_context_manager_with_exception(self):
        """Test context manager handles exceptions properly."""
        try:
            with DatabaseConnector(self.db_path) as connector:
                assert connector.is_connected()
                raise ValueError("Test exception")
        except ValueError:
            pass  # Expected

        # Should still be disconnected after exception
        assert not connector.is_connected()

    def test_repr(self):
        """Test string representation."""
        # Not connected
        assert "disconnected" in repr(self.connector)

        # Connected
        self.connector.connect()
        assert "connected" in repr(self.connector)
        assert str(self.db_path) in repr(self.connector)

    @patch('src.thermo_agents.search.database_connector.logger')
    def test_logging_connect(self, mock_logger):
        """Test that connection attempts are logged."""
        self.connector.connect()

        mock_logger.info.assert_called_with(
            f"Successfully connected to database: {self.db_path}"
        )

    @patch('src.thermo_agents.search.database_connector.logger')
    def test_logging_disconnect(self, mock_logger):
        """Test that disconnection is logged."""
        self.connector.connect()
        self.connector.disconnect()

        mock_logger.info.assert_called_with("Database connection closed")

    @patch('src.thermo_agents.search.database_connector.logger')
    def test_logging_query_execution(self, mock_logger):
        """Test that query execution is logged."""
        self.connector.connect()

        self.connector.execute_query("SELECT * FROM compounds LIMIT 1")

        # Check that debug logging was called
        mock_logger.debug.assert_called()

    def test_database_connection_function(self):
        """Test get_db_connection context manager function."""
        with get_db_connection(self.db_path) as connector:
            assert isinstance(connector, DatabaseConnector)
            assert connector.is_connected()

            results = connector.execute_query("SELECT COUNT(*) as count FROM compounds")
            assert results[0]['count'] == 5

    def test_database_connection_function_with_error(self):
        """Test get_db_connection handles errors properly."""
        with pytest.raises(Exception):
            with get_db_connection(self.db_path) as connector:
                assert connector.is_connected()
                raise Exception("Test exception")

    def test_connection_timeout(self):
        """Test that connection timeout is set correctly."""
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            connector = DatabaseConnector(self.db_path)
            connector.connect()

            # Verify that connect was called with timeout parameter
            mock_connect.assert_called_once_with(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False
            )

    def test_row_factory_configuration(self):
        """Test that row factory is configured for dict-like access."""
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            connector = DatabaseConnector(self.db_path)
            connector.connect()

            # Verify that row_factory was set
            assert mock_conn.row_factory == sqlite3.Row

    def test_multiple_concurrent_queries(self):
        """Test executing multiple queries in sequence."""
        self.connector.connect()

        for i in range(5):
            results = self.connector.execute_query(f"SELECT * FROM compounds WHERE ID = {i+1}")
            assert len(results) == 1
            assert results[0]['ID'] == i+1

    def test_large_result_set(self):
        """Test handling of larger result sets."""
        # Insert more test data
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            for i in range(100, 200):
                cursor.execute(
                    "INSERT INTO compounds (ID, Formula, Phase, ReliabilityClass) VALUES (?, ?, ?, ?)",
                    (i, f'TEST{i}', 'g', 1)
                )
            conn.commit()

        self.connector.connect()

        results = self.connector.execute_query("SELECT * FROM compounds WHERE Formula LIKE 'TEST%'")
        assert len(results) == 100

        # Test that all results are properly formatted as dictionaries
        for result in results:
            assert isinstance(result, dict)
            assert 'ID' in result
            assert 'Formula' in result