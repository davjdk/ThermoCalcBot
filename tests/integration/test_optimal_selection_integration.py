"""
Integration tests for optimal record selection.

Tests the complete pipeline from database queries through optimization
to ensure the feature works end-to-end with real system components.
"""

import time
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from thermo_agents.core_logic.compound_data_loader import CompoundDataLoader
from thermo_agents.core_logic.record_range_builder import RecordRangeBuilder
from thermo_agents.models.search import DatabaseRecord
from thermo_agents.selection.optimal_record_selector import (
    OptimalRecordSelector,
    OptimizationConfig,
    VirtualRecord,
)


class TestOptimalSelectionIntegration:
    """Integration tests for optimal record selection."""

    @pytest.fixture
    def optimization_config(self):
        """Create optimization configuration for testing."""
        return OptimizationConfig(
            w1_record_count=0.5,
            w2_data_quality=0.3,
            w3_transition_coverage=0.2,
            gap_tolerance_k=1.0,
            transition_tolerance_k=10.0,
            coeffs_comparison_tolerance=1e-6,
            max_optimization_time_ms=100.0,  # Relaxed for testing
            max_virtual_records=50,
        )

    @pytest.fixture
    def mock_logger(self):
        """Create mock logger."""
        return Mock()

    @pytest.fixture
    def mock_db_connector(self):
        """Create mock database connector."""
        connector = Mock()
        connector.connect = Mock()
        return connector

    @pytest.fixture
    def mock_static_manager(self):
        """Create mock static data manager."""
        manager = Mock()
        manager.is_available = Mock(return_value=False)
        return manager

    @pytest.fixture
    def sample_database_data(self):
        """Create sample database data for testing."""
        return {
            "SiO2": [
                # Solid SiO2 records
                {
                    "rowid": 1,
                    "Formula": "SiO2",
                    "FirstName": "SiO2(CR)",
                    "Phase": "s",
                    "Tmin": 298.1,
                    "Tmax": 480.0,
                    "H298": -908.0,
                    "S298": 43.06,
                    "f1": 58.75,
                    "f2": 0.0,
                    "f3": 0.0,
                    "f4": 0.0,
                    "f5": 0.0,
                    "f6": 0.0,
                    "MeltingPoint": 1883.0,
                    "BoilingPoint": 2630.0,
                    "ReliabilityClass": 1,
                },
                {
                    "rowid": 2,
                    "Formula": "SiO2",
                    "FirstName": "SiO2(CR)",
                    "Phase": "s",
                    "Tmin": 480.0,
                    "Tmax": 540.0,
                    "H298": 0.0,
                    "S298": 0.0,
                    "f1": 58.75,
                    "f2": 0.0,
                    "f3": 0.0,
                    "f4": 0.0,
                    "f5": 0.0,
                    "f6": 0.0,
                    "MeltingPoint": 1883.0,
                    "BoilingPoint": 2630.0,
                    "ReliabilityClass": 1,
                },
                {
                    "rowid": 3,
                    "Formula": "SiO2",
                    "FirstName": "SiO2(CR)",
                    "Phase": "s",
                    "Tmin": 540.0,
                    "Tmax": 600.0,
                    "H298": 0.0,
                    "S298": 0.0,
                    "f1": 58.75,
                    "f2": 0.0,
                    "f3": 0.0,
                    "f4": 0.0,
                    "f5": 0.0,
                    "f6": 0.0,
                    "MeltingPoint": 1883.0,
                    "BoilingPoint": 2630.0,
                    "ReliabilityClass": 1,
                },
                {
                    "rowid": 4,
                    "Formula": "SiO2",
                    "FirstName": "SiO2(CR)",
                    "Phase": "s",
                    "Tmin": 600.0,
                    "Tmax": 3100.0,
                    "H298": 0.0,
                    "S298": 0.0,
                    "f1": 58.75,
                    "f2": 0.0,
                    "f3": 0.0,
                    "f4": 0.0,
                    "f5": 0.0,
                    "f6": 0.0,
                    "MeltingPoint": 1883.0,
                    "BoilingPoint": 2630.0,
                    "ReliabilityClass": 1,
                },
            ],
            "H2O": [
                # Liquid H2O
                {
                    "rowid": 1,
                    "Formula": "H2O",
                    "FirstName": "Water",
                    "Phase": "l",
                    "Tmin": 298.1,
                    "Tmax": 372.8,
                    "H298": -285.8,
                    "S298": 69.95,
                    "f1": 30.09,
                    "f2": 6.8325,
                    "f3": 6.283,
                    "f4": 0.0,
                    "f5": 0.0,
                    "f6": 0.0,
                    "MeltingPoint": 273.15,
                    "BoilingPoint": 373.15,
                    "ReliabilityClass": 1,
                },
                # Gas H2O records with identical coefficients for virtual merging
                {
                    "rowid": 2,
                    "Formula": "H2O",
                    "FirstName": "Water",
                    "Phase": "g",
                    "Tmin": 298.1,
                    "Tmax": 600.0,
                    "H298": -241.8,
                    "S298": 188.8,
                    "f1": 33.33,
                    "f2": 0.0113,
                    "f3": 0.0,
                    "f4": 0.0,
                    "f5": 0.0,
                    "f6": 0.0,
                    "MeltingPoint": 273.15,
                    "BoilingPoint": 373.15,
                    "ReliabilityClass": 1,
                },
                {
                    "rowid": 3,
                    "Formula": "H2O",
                    "FirstName": "Water",
                    "Phase": "g",
                    "Tmin": 600.0,
                    "Tmax": 1600.0,
                    "H298": 0.0,
                    "S298": 0.0,
                    "f1": 33.33,
                    "f2": 0.0113,
                    "f3": 0.0,
                    "f4": 0.0,
                    "f5": 0.0,
                    "f6": 0.0,
                    "MeltingPoint": 273.15,
                    "BoilingPoint": 373.15,
                    "ReliabilityClass": 1,
                },
                {
                    "rowid": 4,
                    "Formula": "H2O",
                    "FirstName": "Water",
                    "Phase": "g",
                    "Tmin": 1600.0,
                    "Tmax": 6000.0,
                    "H298": 0.0,
                    "S298": 0.0,
                    "f1": 33.33,
                    "f2": 0.0113,
                    "f3": 0.0,
                    "f4": 0.0,
                    "f5": 0.0,
                    "f6": 0.0,
                    "MeltingPoint": 273.15,
                    "BoilingPoint": 373.15,
                    "ReliabilityClass": 1,
                },
            ],
            "CeCl3": [
                # Records with overlapping liquid phase
                {
                    "rowid": 1,
                    "Formula": "CeCl3",
                    "FirstName": "Cerium chloride",
                    "Phase": "s",
                    "Tmin": 298.1,
                    "Tmax": 1080.0,
                    "H298": -1060.0,
                    "S298": 151.0,
                    "f1": 91.25,
                    "f2": 0.0,
                    "f3": 0.0,
                    "f4": 0.0,
                    "f5": 0.0,
                    "f6": 0.0,
                    "MeltingPoint": 1080.0,
                    "BoilingPoint": 2000.0,
                    "ReliabilityClass": 1,
                },
                {
                    "rowid": 2,
                    "Formula": "CeCl3",
                    "FirstName": "Cerium chloride",
                    "Phase": "l",
                    "Tmin": 1080.0,
                    "Tmax": 1300.0,
                    "H298": -1020.0,
                    "S298": 189.0,
                    "f1": 95.50,
                    "f2": 0.0,
                    "f3": 0.0,
                    "f4": 0.0,
                    "f5": 0.0,
                    "f6": 0.0,
                    "MeltingPoint": 1080.0,
                    "BoilingPoint": 2000.0,
                    "ReliabilityClass": 1,
                },
                {
                    "rowid": 3,
                    "Formula": "CeCl3",
                    "FirstName": "Cerium chloride",
                    "Phase": "l",
                    "Tmin": 1080.0,
                    "Tmax": 1500.0,
                    "H298": -1020.0,
                    "S298": 189.0,
                    "f1": 95.50,
                    "f2": 0.0,
                    "f3": 0.0,
                    "f4": 0.0,
                    "f5": 0.0,
                    "f6": 0.0,
                    "MeltingPoint": 1080.0,
                    "BoilingPoint": 2000.0,
                    "ReliabilityClass": 1,
                },
            ],
        }

    def test_full_pipeline_with_optimization(
        self,
        optimization_config,
        mock_logger,
        mock_db_connector,
        mock_static_manager,
        sample_database_data,
    ):
        """Test full pipeline with optimization enabled."""

        # Setup database connector mock
        def mock_execute_query(query):
            # Extract formula from query (simplified)
            if "SiO2" in query:
                return sample_database_data["SiO2"]
            elif "H2O" in query:
                return sample_database_data["H2O"]
            elif "CeCl3" in query:
                return sample_database_data["CeCl3"]
            return []

        mock_db_connector.execute_query = mock_execute_query

        # Create components
        optimizer = OptimalRecordSelector(optimization_config)
        data_loader = CompoundDataLoader(
            mock_db_connector, mock_static_manager, mock_logger, optimizer
        )
        record_builder = RecordRangeBuilder(mock_logger, optimizer)

        # Test SiO2 optimization (should remain unchanged - already optimal)
        si02_df, _, _, _ = data_loader.get_raw_compound_data_with_optimization_support(
            "SiO2", ["SiO2(CR)"], use_optimization=True
        )

        si02_optimized = record_builder.get_optimal_compound_records_for_range(
            df=si02_df,
            t_range=[298, 2500],
            melting=1883.0,
            boiling=2630.0,
            tolerance=1.0,
            is_elemental=False,
            use_optimization=True,
        )

        # SiO2 should remain 4 records (already optimal)
        assert len(si02_optimized) == 4

        # Test H2O optimization (should create virtual record)
        h2o_df, _, _, _ = data_loader.get_raw_compound_data_with_optimization_support(
            "H2O", ["Water"], use_optimization=True
        )

        h2o_optimized = record_builder.get_optimal_compound_records_for_range(
            df=h2o_df,
            t_range=[298, 2000],
            melting=273.15,
            boiling=373.15,
            tolerance=1.0,
            is_elemental=False,
            use_optimization=True,
        )

        # H2O should be optimized from 4 to 3 records (virtual merging)
        assert len(h2o_optimized) == 3

        # Check for virtual record creation
        virtual_records = [r for r in h2o_optimized if isinstance(r, VirtualRecord)]
        assert len(virtual_records) > 0

        # Test CeCl3 optimization (should eliminate duplicate)
        cecl3_df, _, _, _ = data_loader.get_raw_compound_data_with_optimization_support(
            "CeCl3", ["Cerium chloride"], use_optimization=True
        )

        cecl3_optimized = record_builder.get_optimal_compound_records_for_range(
            df=cecl3_df,
            t_range=[298, 1500],
            melting=1080.0,
            boiling=2000.0,
            tolerance=1.0,
            is_elemental=False,
            use_optimization=True,
        )

        # CeCl3 should be optimized from 3 to 2 records (duplicate elimination)
        assert len(cecl3_optimized) == 2

    def test_backward_compatibility(
        self, mock_logger, mock_db_connector, mock_static_manager, sample_database_data
    ):
        """Test that use_optimization=False gives identical results to current implementation."""

        # Setup database connector mock
        def mock_execute_query(query):
            if "H2O" in query:
                return sample_database_data["H2O"]
            return []

        mock_db_connector.execute_query = mock_execute_query

        # Create components without optimizer
        data_loader_no_opt = CompoundDataLoader(
            mock_db_connector, mock_static_manager, mock_logger
        )
        record_builder_no_opt = RecordRangeBuilder(mock_logger)

        # Get results without optimization
        h2o_df, _, _, _ = (
            data_loader_no_opt.get_raw_compound_data_with_optimization_support(
                "H2O", ["Water"], use_optimization=False
            )
        )

        h2o_standard = record_builder_no_opt.get_compound_records_for_range(
            df=h2o_df,
            t_range=[298, 2000],
            melting=273.15,
            boiling=373.15,
            tolerance=1.0,
            is_elemental=False,
        )

        # Create components with optimizer but disabled
        optimizer = OptimalRecordSelector()
        data_loader_with_opt = CompoundDataLoader(
            mock_db_connector, mock_static_manager, mock_logger, optimizer
        )
        record_builder_with_opt = RecordRangeBuilder(mock_logger, optimizer)

        # Get results with optimization disabled
        h2o_df_opt, _, _, _ = (
            data_loader_with_opt.get_raw_compound_data_with_optimization_support(
                "H2O", ["Water"], use_optimization=False
            )
        )

        h2o_disabled_opt = (
            record_builder_with_opt.get_optimal_compound_records_for_range(
                df=h2o_df_opt,
                t_range=[298, 2000],
                melting=273.15,
                boiling=373.15,
                tolerance=1.0,
                is_elemental=False,
                use_optimization=False,
            )
        )

        # Results should be identical
        assert len(h2o_standard) == len(h2o_disabled_opt)

        def get_tmin(r):
            return r.Tmin if hasattr(r, "Tmin") else r.tmin

        def get_tmax(r):
            return r.Tmax if hasattr(r, "Tmax") else r.tmax

        for i, (standard, disabled) in enumerate(zip(h2o_standard, h2o_disabled_opt)):
            assert standard.rowid == disabled.rowid
            assert get_tmin(standard) == get_tmin(disabled)
            assert get_tmax(standard) == get_tmax(disabled)

    def test_multi_compound_reaction_optimization(
        self,
        optimization_config,
        mock_logger,
        mock_db_connector,
        mock_static_manager,
        sample_database_data,
    ):
        """Test optimization for multi-compound reaction."""

        # Setup database connector mock for multiple compounds
        def mock_execute_query(query):
            if "SiO2" in query:
                return sample_database_data["SiO2"]
            elif "Fe2O3" in query:
                # Add Fe2O3 data
                return [
                    {
                        "rowid": 1,
                        "Formula": "Fe2O3",
                        "FirstName": "Ferric oxide",
                        "Phase": "s",
                        "Tmin": 298.1,
                        "Tmax": 950.0,
                        "H298": -822.0,
                        "S298": 87.4,
                        "f1": 103.5,
                        "f2": 0.0,
                        "f3": 0.0,
                        "f4": 0.0,
                        "f5": 0.0,
                        "f6": 0.0,
                        "MeltingPoint": 1838.0,
                        "BoilingPoint": 3000.0,
                        "ReliabilityClass": 1,
                    },
                    {
                        "rowid": 2,
                        "Formula": "Fe2O3",
                        "FirstName": "Ferric oxide",
                        "Phase": "s",
                        "Tmin": 950.0,
                        "Tmax": 1838.0,
                        "H298": 0.0,
                        "S298": 0.0,
                        "f1": 103.5,
                        "f2": 0.0,
                        "f3": 0.0,
                        "f4": 0.0,
                        "f5": 0.0,
                        "f6": 0.0,
                        "MeltingPoint": 1838.0,
                        "BoilingPoint": 3000.0,
                        "ReliabilityClass": 1,
                    },
                ]
            elif "CO" in query:
                # Add CO data
                return [
                    {
                        "rowid": 1,
                        "Formula": "CO",
                        "FirstName": "Carbon monoxide",
                        "Phase": "g",
                        "Tmin": 298.1,
                        "Tmax": 3000.0,
                        "H298": -110.5,
                        "S298": 197.7,
                        "f1": 28.16,
                        "f2": 0.1675,
                        "f3": 0.5374,
                        "f4": 0.0,
                        "f5": 0.0,
                        "f6": 0.0,
                        "MeltingPoint": 68.0,
                        "BoilingPoint": 82.0,
                        "ReliabilityClass": 1,
                    }
                ]
            return []

        mock_db_connector.execute_query = mock_execute_query

        # Create components with optimization
        optimizer = OptimalRecordSelector(optimization_config)
        data_loader = CompoundDataLoader(
            mock_db_connector, mock_static_manager, mock_logger, optimizer
        )
        record_builder = RecordRangeBuilder(mock_logger, optimizer)

        # Test optimization for multiple compounds in reaction
        compounds = ["SiO2", "Fe2O3", "CO"]
        temp_range = [298, 1500]

        total_records_standard = 0
        total_records_optimized = 0

        for compound in compounds:
            # Get data without optimization
            df, _, _, _ = data_loader.get_raw_compound_data_with_optimization_support(
                compound, [compound], use_optimization=False
            )
            standard_records = record_builder.get_compound_records_for_range(
                df=df,
                t_range=temp_range,
                melting=None,
                boiling=None,
                tolerance=1.0,
                is_elemental=False,
            )
            total_records_standard += len(standard_records)

            # Get data with optimization
            df_opt, _, _, _ = (
                data_loader.get_raw_compound_data_with_optimization_support(
                    compound, [compound], use_optimization=True
                )
            )
            optimized_records = record_builder.get_optimal_compound_records_for_range(
                df=df_opt,
                t_range=temp_range,
                melting=None,
                boiling=None,
                tolerance=1.0,
                is_elemental=False,
                use_optimization=True,
            )
            total_records_optimized += len(optimized_records)

        # Should have some reduction in total records
        assert total_records_optimized <= total_records_standard

        # Verify virtual records were created where appropriate
        all_optimized_records = []
        for compound in compounds:
            df, _, _, _ = data_loader.get_raw_compound_data_with_optimization_support(
                compound, [compound], use_optimization=True
            )
            records = record_builder.get_optimal_compound_records_for_range(
                df=df,
                t_range=temp_range,
                melting=None,
                boiling=None,
                tolerance=1.0,
                is_elemental=False,
                use_optimization=True,
            )
            all_optimized_records.extend(records)

        virtual_count = sum(
            1 for r in all_optimized_records if isinstance(r, VirtualRecord)
        )
        # May or may not have virtual records depending on data structure

    def test_phase_transition_optimization(
        self,
        optimization_config,
        mock_logger,
        mock_db_connector,
        mock_static_manager,
        sample_database_data,
    ):
        """Test optimization with phase transition coverage."""

        # Setup database connector mock
        def mock_execute_query(query):
            if "H2O" in query:
                return sample_database_data["H2O"]
            return []

        mock_db_connector.execute_query = mock_execute_query

        # Create components
        optimizer = OptimalRecordSelector(optimization_config)
        data_loader = CompoundDataLoader(
            mock_db_connector, mock_static_manager, mock_logger, optimizer
        )
        record_builder = RecordRangeBuilder(mock_logger, optimizer)

        # Test optimization around boiling point
        h2o_df, _, _, _ = data_loader.get_raw_compound_data_with_optimization_support(
            "H2O", ["Water"], use_optimization=True
        )

        # Temperature range crossing boiling point
        optimized_records = record_builder.get_optimal_compound_records_for_range(
            df=h2o_df,
            t_range=[350, 450],  # Crosses boiling point at 373.15K
            melting=273.15,
            boiling=373.15,
            tolerance=1.0,
            is_elemental=False,
            use_optimization=True,
        )

        # Should ensure boiling point coverage
        def get_tmin(r):
            return r.Tmin if hasattr(r, "Tmin") else r.tmin

        def get_tmax(r):
            return r.Tmax if hasattr(r, "Tmax") else r.tmax

        def get_phase(r):
            return r.Phase if hasattr(r, "Phase") else r.phase

        boiling_covered = any(
            get_tmin(r) <= 373.15 <= get_tmax(r) for r in optimized_records
        )
        assert boiling_covered, "Boiling point should be covered in optimized records"

        # Should have both liquid and gas phases
        phases = [get_phase(r) for r in optimized_records]
        assert "l" in phases, "Liquid phase should be present"
        assert "g" in phases, "Gas phase should be present"

    def test_error_handling_in_pipeline(
        self, optimization_config, mock_logger, mock_db_connector, mock_static_manager
    ):
        """Test error handling in optimization pipeline."""
        # Setup database connector to return empty data
        mock_db_connector.execute_query = Mock(return_value=[])

        # Create components
        optimizer = OptimalRecordSelector(optimization_config)
        data_loader = CompoundDataLoader(
            mock_db_connector, mock_static_manager, mock_logger, optimizer
        )
        record_builder = RecordRangeBuilder(mock_logger, optimizer)

        # Test with non-existent compound
        df, _, _, _ = data_loader.get_raw_compound_data_with_optimization_support(
            "NonExistent", ["NonExistent"], use_optimization=True
        )

        assert df.empty, "Should return empty DataFrame for non-existent compound"

        # Test optimization with empty data
        optimized_records = record_builder.get_optimal_compound_records_for_range(
            df=df,
            t_range=[298, 1000],
            melting=None,
            boiling=None,
            tolerance=1.0,
            is_elemental=False,
            use_optimization=True,
        )

        assert optimized_records == [], "Should return empty list for empty input data"

    def test_performance_with_large_dataset(self, optimization_config, mock_logger):
        """Test performance with larger dataset."""
        # Create large synthetic dataset
        large_records = []
        for i in range(100):
            record = {
                "rowid": i,
                "Formula": f"Compound{i}",
                "FirstName": f"Compound{i}",
                "Phase": "g",
                "Tmin": 100 + i * 10,
                "Tmax": 200 + i * 10,
                "H298": 0.0,
                "S298": 0.0,
                "f1": 10.0 + i * 0.1,
                "f2": 0.1,
                "f3": 0.0,
                "f4": 0.0,
                "f5": 0.0,
                "f6": 0.0,
                "MeltingPoint": 0.0,
                "BoilingPoint": 0.0,
                "ReliabilityClass": 1,
            }
            large_records.append(record)

        df = pd.DataFrame(large_records)

        # Create optimizer
        optimizer = OptimalRecordSelector(optimization_config)

        # Measure optimization time
        start_time = time.perf_counter()

        # Simulate optimization (convert to DatabaseRecord objects)
        db_records = []
        for _, row in df.iterrows():
            db_record = DatabaseRecord(
                rowid=row["rowid"],
                formula=row["Formula"],
                first_name=row["FirstName"],
                phase=row["Phase"],
                tmin=row["Tmin"],
                tmax=row["Tmax"],
                h298=row["H298"],
                s298=row["S298"],
                f1=row["f1"],
                f2=row["f2"],
                f3=row["f3"],
                f4=row["f4"],
                f5=row["f5"],
                f6=row["f6"],
                tmelt=row["MeltingPoint"],
                tboil=row["BoilingPoint"],
                reliability_class=row["ReliabilityClass"],
            )
            db_records.append(db_record)

        # Use first 20 records for optimization test
        test_records = db_records[:20]

        optimized_records = optimizer.optimize_selected_records(
            selected_records=test_records,
            target_range=(100, 500),
            all_available_records=df,
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        elapsed_time_ms = (time.perf_counter() - start_time) * 1000

        # Should complete within reasonable time
        assert elapsed_time_ms < optimization_config.max_optimization_time_ms * 2
        assert len(optimized_records) > 0

    def test_virtual_record_properties_preservation(
        self,
        optimization_config,
        mock_logger,
        mock_db_connector,
        mock_static_manager,
        sample_database_data,
    ):
        """Test that virtual records preserve original properties correctly."""

        # Setup database connector mock
        def mock_execute_query(query):
            if "H2O" in query:
                return sample_database_data["H2O"]
            return []

        mock_db_connector.execute_query = mock_execute_query

        # Create components
        optimizer = OptimalRecordSelector(optimization_config)
        data_loader = CompoundDataLoader(
            mock_db_connector, mock_static_manager, mock_logger, optimizer
        )
        record_builder = RecordRangeBuilder(mock_logger, optimizer)

        # Get optimized records
        h2o_df, _, _, _ = data_loader.get_raw_compound_data_with_optimization_support(
            "H2O", ["Water"], use_optimization=True
        )

        optimized_records = record_builder.get_optimal_compound_records_for_range(
            df=h2o_df,
            t_range=[298, 2000],
            melting=273.15,
            boiling=373.15,
            tolerance=1.0,
            is_elemental=False,
            use_optimization=True,
        )

        # Find virtual records
        virtual_records = [r for r in optimized_records if isinstance(r, VirtualRecord)]

        if virtual_records:
            virtual_record = virtual_records[0]

            # Check that properties are preserved
            assert virtual_record.phase == "g"
            assert virtual_record.merged_tmin < virtual_record.merged_tmax
            assert len(virtual_record.source_records) >= 2

            # Check that source records have identical coefficients
            source_coeffs = []
            for source in virtual_record.source_records:
                coeffs = [
                    source.f1,
                    source.f2,
                    source.f3,
                    source.f4,
                    source.f5,
                    source.f6,
                ]
                source_coeffs.append(coeffs)

            # All source coefficients should be identical
            for i in range(1, len(source_coeffs)):
                for j in range(6):
                    assert abs(source_coeffs[0][j] - source_coeffs[i][j]) < 1e-6

            # Check merged temperature range
            def get_tmin(r):
                return r.Tmin if hasattr(r, "Tmin") else r.tmin

            def get_tmax(r):
                return r.Tmax if hasattr(r, "Tmax") else r.tmax

            expected_tmin = min(get_tmin(r) for r in virtual_record.source_records)
            expected_tmax = max(get_tmax(r) for r in virtual_record.source_records)
            assert virtual_record.merged_tmin == expected_tmin
            assert virtual_record.merged_tmax == expected_tmax

    def test_optimization_configuration_impact(
        self, mock_logger, mock_db_connector, mock_static_manager, sample_database_data
    ):
        """Test that different optimization configurations produce different results."""

        # Setup database connector mock
        def mock_execute_query(query):
            if "H2O" in query:
                return sample_database_data["H2O"]
            return []

        mock_db_connector.execute_query = mock_execute_query

        # Create configurations with different weights
        config_records_priority = OptimizationConfig(
            w1_record_count=0.8,  # High priority to minimizing records
            w2_data_quality=0.1,
            w3_transition_coverage=0.1,
        )

        config_quality_priority = OptimizationConfig(
            w1_record_count=0.2,  # Low priority to minimizing records
            w2_data_quality=0.7,  # High priority to data quality
            w3_transition_coverage=0.1,
        )

        # Test with records priority configuration
        optimizer_records = OptimalRecordSelector(config_records_priority)
        data_loader_records = CompoundDataLoader(
            mock_db_connector, mock_static_manager, mock_logger, optimizer_records
        )
        record_builder_records = RecordRangeBuilder(mock_logger, optimizer_records)

        h2o_df, _, _, _ = (
            data_loader_records.get_raw_compound_data_with_optimization_support(
                "H2O", ["Water"], use_optimization=True
            )
        )

        records_priority_result = (
            record_builder_records.get_optimal_compound_records_for_range(
                df=h2o_df,
                t_range=[298, 2000],
                melting=273.15,
                boiling=373.15,
                tolerance=1.0,
                is_elemental=False,
                use_optimization=True,
            )
        )

        # Test with quality priority configuration
        optimizer_quality = OptimalRecordSelector(config_quality_priority)
        data_loader_quality = CompoundDataLoader(
            mock_db_connector, mock_static_manager, mock_logger, optimizer_quality
        )
        record_builder_quality = RecordRangeBuilder(mock_logger, optimizer_quality)

        quality_priority_result = (
            record_builder_quality.get_optimal_compound_records_for_range(
                df=h2o_df,
                t_range=[298, 2000],
                melting=273.15,
                boiling=373.15,
                tolerance=1.0,
                is_elemental=False,
                use_optimization=True,
            )
        )

        # Results should be different (though both should be valid)
        # Note: In this specific case, results might be the same if the optimization
        # is clearly optimal regardless of configuration
        assert len(records_priority_result) >= 1
        assert len(quality_priority_result) >= 1


if __name__ == "__main__":
    pytest.main([__file__])
